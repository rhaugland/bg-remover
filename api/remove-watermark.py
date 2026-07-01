from http.server import BaseHTTPRequestHandler
import json
import os
import base64
import io
import urllib.request
import urllib.error
import uuid
from PIL import Image, ImageDraw, ImageFilter

STABILITY_API_KEY = os.environ.get("STABILITY_API_KEY", "")


def build_multipart(fields, files):
    boundary = uuid.uuid4().hex
    lines = []
    for key, value in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"'.encode())
        lines.append(b"")
        lines.append(value.encode() if isinstance(value, str) else value)
    for key, (filename, data, content_type) in files.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"'.encode())
        lines.append(f"Content-Type: {content_type}".encode())
        lines.append(b"")
        lines.append(data)
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    body = b"\r\n".join(lines)
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def detect_watermark_mask(image_bytes):
    """Detect semi-transparent watermark regions and create a mask for inpainting."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    gray = img.convert("L")

    # Create mask - start with all black (keep everything)
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    # Strategy: detect areas with subtle contrast variations typical of watermarks
    # Watermarks create a consistent semi-transparent overlay pattern
    # We look for areas where local contrast differs from neighbors in a watermark-like way

    pixels = gray.load()
    mask_pixels = mask.load()

    # Scan for watermark-like patterns: areas where pixel values
    # deviate slightly from their local neighborhood average
    # (watermarks create consistent low-amplitude patterns)
    block = 8
    threshold_low = 3   # minimum deviation to consider
    threshold_high = 40  # maximum deviation (real edges are higher)

    for by in range(block, h - block, block):
        for bx in range(block, w - block, block):
            # Get center block average
            center_sum = 0
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    center_sum += pixels[bx + dx, by + dy]
            center_avg = center_sum / 9

            # Get surrounding average (larger radius)
            surround_sum = 0
            count = 0
            for dy in range(-block, block + 1, 2):
                for dx in range(-block, block + 1, 2):
                    nx, ny = bx + dx, by + dy
                    if 0 <= nx < w and 0 <= ny < h:
                        surround_sum += pixels[nx, ny]
                        count += 1
            surround_avg = surround_sum / max(count, 1)

            diff = abs(center_avg - surround_avg)
            if threshold_low < diff < threshold_high:
                # Mark this block as potential watermark
                for dy in range(-block // 2, block // 2 + 1):
                    for dx in range(-block // 2, block // 2 + 1):
                        nx, ny = bx + dx, by + dy
                        if 0 <= nx < w and 0 <= ny < h:
                            mask_pixels[nx, ny] = 255

    # Also add a generous ellipse covering the typical watermark region
    # (center-bottom area where vendor watermarks usually sit)
    cx, cy = w // 2, int(h * 0.55)
    rx, ry = int(w * 0.35), int(h * 0.25)
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)

    # Dilate the mask to ensure full coverage
    mask = mask.filter(ImageFilter.MaxFilter(15))
    # Blur edges for smooth inpainting transitions
    mask = mask.filter(ImageFilter.GaussianBlur(radius=8))

    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return buf.getvalue()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not STABILITY_API_KEY:
                raise ValueError("STABILITY_API_KEY not configured")

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            image_data_url = body.get("image", "")
            if not image_data_url:
                raise ValueError("Image is required")

            # Extract binary image data from data URL
            if "," in image_data_url:
                header, b64data = image_data_url.split(",", 1)
                image_bytes = base64.b64decode(b64data)
            else:
                image_bytes = base64.b64decode(image_data_url)

            # Generate watermark mask
            mask_bytes = detect_watermark_mask(image_bytes)

            # Use Stability AI erase endpoint with the detected mask
            fields = {
                "output_format": "png",
            }
            files = {
                "image": ("image.png", image_bytes, "image/png"),
                "mask": ("mask.png", mask_bytes, "image/png"),
            }

            req_body, content_type = build_multipart(fields, files)

            req = urllib.request.Request(
                "https://api.stability.ai/v2beta/stable-image/edit/erase",
                data=req_body,
                headers={
                    "Authorization": f"Bearer {STABILITY_API_KEY}",
                    "Content-Type": content_type,
                    "Accept": "image/*",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                result_bytes = resp.read()

            result_b64 = base64.b64encode(result_bytes).decode()
            result_data_url = f"data:image/png;base64,{result_b64}"

            response = json.dumps({"image": result_data_url})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"Stability API error {e.code}: {err_body}"})
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
