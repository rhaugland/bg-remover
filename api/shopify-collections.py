from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE_URL", "")
SHOPIFY_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
API_VERSION = "2024-01"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
                raise ValueError("Shopify credentials not configured")

            base = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}"
            headers = {
                "X-Shopify-Access-Token": SHOPIFY_TOKEN,
                "Content-Type": "application/json",
            }

            collections = []

            # Fetch custom collections
            req = urllib.request.Request(
                f"{base}/custom_collections.json?limit=250",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for c in data.get("custom_collections", []):
                    collections.append({"id": c["id"], "title": c["title"]})

            # Fetch smart collections
            req = urllib.request.Request(
                f"{base}/smart_collections.json?limit=250",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                for c in data.get("smart_collections", []):
                    collections.append({"id": c["id"], "title": c["title"]})

            collections.sort(key=lambda c: c["title"])

            response = json.dumps({"collections": collections})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except Exception as e:
            error = json.dumps({"error": str(e)})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())
