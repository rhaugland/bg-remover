from http.server import BaseHTTPRequestHandler
import json
import os
import base64
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
                if "png" in header:
                    mime = "image/png"
                    ext = "image.png"
                else:
                    mime = "image/jpeg"
                    ext = "image.jpg"
            else:
                image_bytes = base64.b64decode(image_data_url)
                mime = "image/png"
                ext = "image.png"

            # Use Stability AI search-and-replace to remove watermarks
            fields = {
                "prompt": "clean product surface, no text, no watermark, matching surrounding texture and color",
                "search_prompt": "watermark, logo overlay, text overlay, brand stamp, semi-transparent text",
                "output_format": "png",
            }
            files = {
                "image": (ext, image_bytes, mime),
            }

            req_body, content_type = build_multipart(fields, files)

            req = urllib.request.Request(
                "https://api.stability.ai/v2beta/stable-image/edit/search-and-replace",
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
                result_ct = resp.headers.get("Content-Type", "image/png")

            result_b64 = base64.b64encode(result_bytes).decode()
            result_data_url = f"data:{result_ct};base64,{result_b64}"

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
