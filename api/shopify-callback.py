from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.parse

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE_URL", "")
SHOPIFY_CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Parse the authorization code from query string
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            code = params.get("code", [None])[0]

            if not code:
                raise ValueError("No authorization code received")

            # Exchange code for permanent access token
            data = json.dumps({
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET,
                "code": code,
            }).encode()

            req = urllib.request.Request(
                f"https://{SHOPIFY_STORE}/admin/oauth/access_token",
                data=data,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())

            access_token = result.get("access_token", "")

            # Store token as Vercel env var if VERCEL_TOKEN is available
            vercel_token = os.environ.get("VERCEL_TOKEN", "")
            vercel_project = os.environ.get("VERCEL_PROJECT_ID", "")
            stored = False

            if vercel_token and vercel_project:
                try:
                    env_data = json.dumps({
                        "key": "SHOPIFY_ACCESS_TOKEN",
                        "value": access_token,
                        "type": "encrypted",
                        "target": ["production"],
                    }).encode()
                    env_req = urllib.request.Request(
                        f"https://api.vercel.com/v10/projects/{vercel_project}/env",
                        data=env_data,
                        headers={
                            "Authorization": f"Bearer {vercel_token}",
                            "Content-Type": "application/json",
                        },
                    )
                    with urllib.request.urlopen(env_req, timeout=10) as env_resp:
                        env_resp.read()
                    stored = True
                except Exception:
                    pass

            # Show success page
            masked = access_token[:8] + "..." + access_token[-4:] if len(access_token) > 12 else access_token
            store_msg = "Token auto-saved to Vercel." if stored else f"Add this env var to Vercel:<br><br><strong>SHOPIFY_ACCESS_TOKEN</strong><br><code style='word-break:break-all;font-size:14px;background:#222;padding:8px 12px;border-radius:8px;display:block;margin-top:8px'>{access_token}</code>"

            html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shopify Connected</title>
<style>
body {{ background:#000; color:#fff; font-family:-apple-system,sans-serif; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; padding:20px; }}
.card {{ background:#111; border-radius:16px; padding:32px; max-width:500px; width:100%; text-align:center; border:1px solid rgba(255,255,255,0.06); }}
h1 {{ font-size:24px; margin:0 0 8px; }}
p {{ color:rgba(255,255,255,0.5); font-size:14px; line-height:1.6; }}
code {{ color:#4ade80; }}
.check {{ font-size:48px; margin-bottom:16px; }}
</style></head><body>
<div class="card">
<div class="check">&#10003;</div>
<h1>Shopify Connected</h1>
<p>{store_msg}</p>
<p style="margin-top:20px"><a href="/" style="color:#fff;text-decoration:underline">Back to app</a></p>
</div>
</body></html>"""

            response = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            msg = f"Shopify OAuth error {e.code}: {err_body}".encode()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

        except Exception as e:
            msg = str(e).encode()
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
