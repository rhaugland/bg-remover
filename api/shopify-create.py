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


def shopify_request(token, path, method="GET", data=None):
    base = f"https://{SHOPIFY_STORE}/admin/api/{API_VERSION}"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{base}{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not SHOPIFY_STORE or not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
                raise ValueError("Shopify credentials not configured")

            token = get_access_token()

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            title = body.get("title", "")
            if not title:
                raise ValueError("Product title is required")

            # Build product payload
            images = [{"attachment": img} for img in body.get("images", [])]

            product_data = {
                "product": {
                    "title": title,
                    "body_html": body.get("description", ""),
                    "product_type": body.get("category", ""),
                    "tags": body.get("tags", ""),
                    "images": images,
                    "metafields_global_description_tag": body.get("meta_description", ""),
                    "metafields_global_title_tag": title,
                    "variants": [
                        {
                            "price": body.get("price", "0.00"),
                            "weight": float(body.get("weight", 0) or 0),
                            "weight_unit": "lb",
                            "requires_shipping": True,
                            "inventory_management": None,
                        }
                    ],
                }
            }

            # Create product
            result = shopify_request(token, "/products.json", method="POST", data=product_data)
            product_id = result["product"]["id"]

            # Add to collection if specified
            collection_id = body.get("collection_id")
            if collection_id:
                collect_data = {
                    "collect": {
                        "product_id": product_id,
                        "collection_id": int(collection_id),
                    }
                }
                try:
                    shopify_request(token, "/collects.json", method="POST", data=collect_data)
                except Exception:
                    pass  # Non-critical if collection add fails

            response = json.dumps({
                "product_id": product_id,
                "handle": result["product"].get("handle", ""),
                "url": f"https://{SHOPIFY_STORE}/products/{result['product'].get('handle', '')}",
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"Shopify error {e.code}: {err_body}"})
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
