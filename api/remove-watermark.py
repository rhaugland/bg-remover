from http.server import BaseHTTPRequestHandler
import json
import os
import base64
import urllib.request
import urllib.error
import time

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPLICATE_API_TOKEN = os.environ.get("REPLICATE_API_TOKEN", "")

LAMA_VERSION = "cdac78a1bec5b23c07fd29692fb70baa513ea403a39e643c48ec5edadb15fe72"


def detect_watermark(b64data, media_type, second_pass=False):
    """Use Claude Haiku to detect watermark regions."""
    api_body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 500,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64data,
                        },
                    },
                    {
                        "type": "text",
                        "text": 'Look at this product image carefully. Is there a faint watermark remnant, ghost image, logo trace, faint wing shape, or any semi-transparent artifact? Look for very subtle discoloration. If yes, return MULTIPLE tight bounding boxes for each trace. Use percentages: {"found": true, "regions": [{"x": pct_left, "y": pct_top, "w": pct_width, "h": pct_height}]}. Keep boxes tight to just the artifact. If clean, return {"found": false}. Return ONLY JSON.' if second_pass else 'Look at this product image carefully. Is there a watermark, logo overlay, brand stamp, eagle, wings, "AMI", or any semi-transparent graphic overlaid on the product? If yes, return MULTIPLE separate bounding boxes - one for each distinct part (e.g. left wing, right wing, center logo, text below). Each box should TIGHTLY fit just that part of the watermark with minimal extra space. Do NOT use one giant box. Do NOT include areas that are just the product surface. Use percentages of image dimensions: {"found": true, "regions": [{"x": pct_left, "y": pct_top, "w": pct_width, "h": pct_height}]}. If no watermark found, return {"found": false}. Return ONLY JSON.',
                    },
                ],
            }
        ],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=api_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())

    text = result["content"][0]["text"].strip()
    if "{" in text:
        json_str = text[text.index("{"):text.rindex("}") + 1]
        return json.loads(json_str)
    return {"found": False}


def create_mask_png(width, height, regions):
    """Create a black/white PNG mask using pure Python (no Pillow).
    White (255) = areas to inpaint, Black (0) = areas to keep."""
    import struct
    import zlib

    # Create pixel data - all black initially
    pixels = bytearray(width * height)

    for region in regions:
        rx = int(region["x"] / 100 * width)
        ry = int(region["y"] / 100 * height)
        rw = int(region["w"] / 100 * width)
        rh = int(region["h"] / 100 * height)

        # Small padding per region since we now use multiple tight boxes
        pad_w = int(rw * 0.1)
        pad_h = int(rh * 0.1)
        rx = rx - pad_w
        ry = ry - pad_h
        rw = rw + pad_w * 2
        rh = rh + pad_h * 2

        # Clamp
        rx = max(0, rx)
        ry = max(0, ry)
        rw = min(rw, width - rx)
        rh = min(rh, height - ry)

        for y in range(ry, ry + rh):
            for x in range(rx, rx + rw):
                pixels[y * width + x] = 255

    # Build PNG
    def make_chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    ihdr = make_chunk(b"IHDR", ihdr_data)

    # Build raw image data with filter bytes
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        raw.extend(pixels[y * width:(y + 1) * width])

    compressed = zlib.compress(bytes(raw), 9)
    idat = make_chunk(b"IDAT", compressed)
    iend = make_chunk(b"IEND", b"")

    return signature + ihdr + idat + iend


def run_lama(image_data_url, mask_b64):
    """Send image + mask to Replicate LAMA for inpainting."""
    mask_data_url = f"data:image/png;base64,{mask_b64}"

    # Create prediction
    body = json.dumps({
        "version": LAMA_VERSION,
        "input": {
            "image": image_data_url,
            "mask": mask_data_url,
        },
    }).encode()

    req = urllib.request.Request(
        "https://api.replicate.com/v1/predictions",
        data=body,
        headers={
            "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
            "Prefer": "wait",
        },
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())

    # If status is succeeded, output is the URL
    if result.get("status") == "succeeded":
        output_url = result.get("output")
        if isinstance(output_url, list):
            output_url = output_url[0]
        return output_url

    # If still processing, poll
    poll_url = result.get("urls", {}).get("get")
    if not poll_url:
        raise ValueError(f"No poll URL. Status: {result.get('status')}, Error: {result.get('error')}")

    for _ in range(30):
        time.sleep(2)
        poll_req = urllib.request.Request(
            poll_url,
            headers={
                "Authorization": f"Bearer {REPLICATE_API_TOKEN}",
            },
        )
        with urllib.request.urlopen(poll_req, timeout=10) as resp:
            result = json.loads(resp.read())

        if result["status"] == "succeeded":
            output_url = result.get("output")
            if isinstance(output_url, list):
                output_url = output_url[0]
            return output_url
        elif result["status"] == "failed":
            raise ValueError(f"LAMA failed: {result.get('error')}")

    raise ValueError("LAMA timed out")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not configured")
            if not REPLICATE_API_TOKEN:
                raise ValueError("REPLICATE_API_TOKEN not configured - get one at replicate.com/account/api-tokens")

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            image_data_url = body.get("image", "")
            if not image_data_url:
                raise ValueError("Image is required")

            # Extract media type and base64 data
            if "," in image_data_url:
                header = image_data_url.split(",")[0]
                b64data = image_data_url.split(",")[1]
                if "png" in header:
                    media_type = "image/png"
                elif "webp" in header:
                    media_type = "image/webp"
                else:
                    media_type = "image/jpeg"
            else:
                b64data = image_data_url
                media_type = "image/jpeg"

            # Step 1: Detect watermark with Claude Haiku
            detection = detect_watermark(b64data, media_type)

            if not detection.get("found"):
                # No watermark detected, return original
                response = json.dumps({"image": image_data_url, "detection": "none"})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response.encode())
                return

            # Step 2: Get image dimensions from the base64 data
            image_bytes = base64.b64decode(b64data)

            # Parse dimensions from image header
            width, height = 0, 0
            if media_type == "image/png":
                import struct
                width = struct.unpack(">I", image_bytes[16:20])[0]
                height = struct.unpack(">I", image_bytes[20:24])[0]
            elif media_type == "image/jpeg":
                # Parse JPEG for dimensions
                i = 2
                while i < len(image_bytes) - 1:
                    if image_bytes[i] != 0xFF:
                        break
                    marker = image_bytes[i + 1]
                    if marker in (0xC0, 0xC2):
                        height = (image_bytes[i + 5] << 8) | image_bytes[i + 6]
                        width = (image_bytes[i + 7] << 8) | image_bytes[i + 8]
                        break
                    elif marker == 0xD9:
                        break
                    else:
                        seg_len = (image_bytes[i + 2] << 8) | image_bytes[i + 3]
                        i += 2 + seg_len
                else:
                    width, height = 800, 600
            else:
                width, height = 800, 600

            if width == 0 or height == 0:
                width, height = 800, 600

            # Step 3: Create mask PNG
            regions = detection.get("regions", [])
            mask_png = create_mask_png(width, height, regions)
            mask_b64 = base64.b64encode(mask_png).decode()

            # Step 4: Run LAMA inpainting
            output_url = run_lama(image_data_url, mask_b64)

            # Step 5: Download the result and convert to data URL
            dl_req = urllib.request.Request(output_url)
            with urllib.request.urlopen(dl_req, timeout=15) as resp:
                result_bytes = resp.read()
                content_type = resp.headers.get("Content-Type", "image/png")

            result_b64 = base64.b64encode(result_bytes).decode()
            result_data_url = f"data:{content_type};base64,{result_b64}"

            # Step 6: Second pass - check if any watermark remnants remain
            detection2 = detect_watermark(result_b64, content_type, second_pass=True)
            if detection2.get("found"):
                regions2 = detection2.get("regions", [])
                mask_png2 = create_mask_png(width, height, regions2)
                mask_b64_2 = base64.b64encode(mask_png2).decode()
                output_url2 = run_lama(result_data_url, mask_b64_2)

                dl_req2 = urllib.request.Request(output_url2)
                with urllib.request.urlopen(dl_req2, timeout=15) as resp2:
                    result_bytes2 = resp2.read()
                    content_type2 = resp2.headers.get("Content-Type", "image/png")

                result_b64 = base64.b64encode(result_bytes2).decode()
                result_data_url = f"data:{content_type2};base64,{result_b64}"

            response = json.dumps({"image": result_data_url, "detection": "removed"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"API error {e.code}: {err_body}"})
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())

        except Exception as e:
            import traceback
            traceback.print_exc()
            error = json.dumps({"error": str(e)})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())
