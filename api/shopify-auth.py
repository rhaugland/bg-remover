from http.server import BaseHTTPRequestHandler
import os
import urllib.parse

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE_URL", "")
SHOPIFY_CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
SCOPES = "read_products,write_products,read_product_listings"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if not SHOPIFY_STORE or not SHOPIFY_CLIENT_ID:
                raise ValueError("SHOPIFY_STORE_URL or SHOPIFY_CLIENT_ID not configured")

            # Build redirect URI from the request host
            host = self.headers.get("x-forwarded-host", self.headers.get("host", ""))
            proto = self.headers.get("x-forwarded-proto", "https")
            redirect_uri = f"{proto}://{host}/api/shopify-callback"

            params = urllib.parse.urlencode({
                "client_id": SHOPIFY_CLIENT_ID,
                "scope": SCOPES,
                "redirect_uri": redirect_uri,
            })

            auth_url = f"https://{SHOPIFY_STORE}/admin/oauth/authorize?{params}"

            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            msg = str(e).encode()
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
