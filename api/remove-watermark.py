from http.server import BaseHTTPRequestHandler
import json
import os
import base64
import io
import struct
import zlib
import urllib.request
import urllib.error
import uuid

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


def make_png_chunk(chunk_type, data):
    chunk = chunk_type + data
    crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
    return struct.pack(">I", len(data)) + chunk + crc


def create_ellipse_mask_png(width, height):
    """Create a PNG mask with a white ellipse in the center-bottom area (no Pillow needed)."""
    # Ellipse parameters — generous coverage of typical watermark region
    cx = width / 2
    cy = height * 0.55
    rx = width * 0.38
    ry = height * 0.28
    # Feather radius for smooth edges
    feather = min(width, height) * 0.05

    rows = []
    for y in range(height):
        row = bytearray(width)
        for x in range(width):
            dx = (x - cx) / rx
            dy = (y - cy) / ry
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= 1.0:
                row[x] = 255
            elif dist <= 1.0 + feather / min(rx, ry):
                # Feathered edge
                t = (dist - 1.0) / (feather / min(rx, ry))
                row[x] = int(255 * (1 - t))
            else:
                row[x] = 0
        # PNG filter byte (0 = None) + row data
        rows.append(b"\x00" + bytes(row))

    raw = b"".join(rows)
    compressed = zlib.compress(raw)

    # Build PNG file
    png = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, bit depth 8, color type 0 (grayscale)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png += make_png_chunk(b"IHDR", ihdr_data)
    png += make_png_chunk(b"IDAT", compressed)
    png += make_png_chunk(b"IEND", b"")
    return png


def get_image_dimensions(image_bytes):
    """Read width/height from PNG or JPEG header."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        w = struct.unpack(">I", image_bytes[16:20])[0]
        h = struct.unpack(">I", image_bytes[20:24])[0]
        return w, h
    # JPEG - scan for SOF marker
    i = 0
    while i < len(image_bytes) - 1:
        if image_bytes[i] == 0xFF:
            marker = image_bytes[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h = struct.unpack(">H", image_bytes[i + 5:i + 7])[0]
                w = struct.unpack(">H", image_bytes[i + 7:i + 9])[0]
                return w, h
            elif marker == 0xD8 or marker == 0xD9:
                i += 2
            elif marker == 0xFF:
                i += 1
            else:
                seg_len = struct.unpack(">H", image_bytes[i + 2:i + 4])[0]
                i += 2 + seg_len
        else:
            i += 1
    return 512, 512  # fallback


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

            # Get image dimensions and create mask
            w, h = get_image_dimensions(image_bytes)
            mask_bytes = create_ellipse_mask_png(w, h)

            # Use Stability AI erase endpoint with the mask
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
