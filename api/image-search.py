from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import base64

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
                raise ValueError("Google Search API not configured")

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            query = body.get("query", "").strip()
            if not query:
                raise ValueError("Part number is required")

            # Search Google Images for the part number
            params = urllib.parse.urlencode({
                "key": GOOGLE_API_KEY,
                "cx": GOOGLE_CSE_ID,
                "q": query,
                "searchType": "image",
                "num": 10,
                "imgSize": "large",
            })

            req = urllib.request.Request(
                f"https://www.googleapis.com/customsearch/v1?{params}",
                headers={"Accept": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            # Extract image results
            images = []
            for item in data.get("items", []):
                images.append({
                    "url": item.get("link", ""),
                    "thumbnail": item.get("image", {}).get("thumbnailLink", ""),
                    "title": item.get("title", ""),
                    "source": item.get("displayLink", ""),
                    "width": item.get("image", {}).get("width", 0),
                    "height": item.get("image", {}).get("height", 0),
                })

            response = json.dumps({"images": images, "query": query})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"Search API error {e.code}: {err_body}"})
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
