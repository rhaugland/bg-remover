from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error
import urllib.parse
import re

BRAVE_API_KEY = os.environ.get("BRAVE_API_KEY", "")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not BRAVE_API_KEY:
                raise ValueError("BRAVE_API_KEY not configured")

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            query = body.get("query", "").strip()
            if not query:
                raise ValueError("Part number is required")

            # Search Brave Images for the part number
            params = urllib.parse.urlencode({
                "q": query,
                "count": 10,
                "search_lang": "en",
                "safesearch": "off",
            })

            req = urllib.request.Request(
                f"https://api.search.brave.com/res/v1/images/search?{params}",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": BRAVE_API_KEY,
                },
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            # Extract image results
            images = []
            for item in data.get("results", []):
                thumb = item.get("thumbnail", {})
                images.append({
                    "url": item.get("properties", {}).get("url", item.get("url", "")),
                    "thumbnail": thumb.get("src", ""),
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "width": item.get("properties", {}).get("width", 0),
                    "height": item.get("properties", {}).get("height", 0),
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
