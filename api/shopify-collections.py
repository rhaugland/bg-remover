from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error
import urllib.parse

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE_URL", "")
SHOPIFY_CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
API_VERSION = "2024-01"


def get_access_token():
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request(
        f"https://{SHOPIFY_STORE}/admin/oauth/access_token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["access_token"]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if not SHOPIFY_STORE or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
                raise ValueError("Shopify credentials not configured")

            token = get_access_token()
            base = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}"
            headers = {
                "X-Shopify-Access-Token": token,
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

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"Shopify error {e.code}: {err_body}", "store": SHOPIFY_STORE[:10] + "..." if SHOPIFY_STORE else "NOT SET"})
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())

        except Exception as e:
            import traceback
            traceback.print_exc()
            error = json.dumps({"error": str(e), "store": SHOPIFY_STORE[:10] + "..." if SHOPIFY_STORE else "NOT SET"})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())
