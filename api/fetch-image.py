from http.server import BaseHTTPRequestHandler
import json
import base64
import urllib.request
import urllib.error


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            url = body.get("url", "").strip()
            if not url or not url.startswith("http"):
                raise ValueError("Valid image URL required")

            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ProductImageFetcher/1.0)",
                    "Accept": "image/*",
                },
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                image_data = resp.read()

            b64 = base64.b64encode(image_data).decode()
            data_url = f"data:{content_type};base64,{b64}"

            response = json.dumps({"image": data_url})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            error = json.dumps({"error": f"Fetch error {e.code}"})
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())

        except Exception as e:
            error = json.dumps({"error": str(e)})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())
