from http.server import BaseHTTPRequestHandler
import json
import base64
import os
from io import BytesIO
import urllib.request
import urllib.error


REMOVE_BG_KEY = os.environ.get("REMOVE_BG_API_KEY", "")


def call_remove_bg(image_bytes):
    """Call remove.bg API and return result with black background."""
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image_file"; filename="photo.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + image_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="size"\r\n\r\nauto'
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="bg_color"\r\n\r\n000000'
        f"\r\n--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        "https://api.remove.bg/v1.0/removebg",
        data=body,
        headers={
            "X-Api-Key": REMOVE_BG_KEY,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not REMOVE_BG_KEY:
                raise ValueError("REMOVE_BG_API_KEY not configured")

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            image_b64 = body.get("image", "")
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]

            image_bytes = base64.b64decode(image_b64)
            result_bytes = call_remove_bg(image_bytes)
            result_b64 = base64.b64encode(result_bytes).decode()

            response = json.dumps({"image": f"data:image/png;base64,{result_b64}"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"remove.bg error {e.code}: {err_body}"})
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
