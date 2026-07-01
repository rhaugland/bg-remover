from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.request
import urllib.error

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not configured")

            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            title = body.get("title", "")
            description = body.get("description", "")
            field = body.get("field", "description")  # "description", "seo", or "all"
            images = body.get("images", [])  # base64 data URLs

            # Build image content blocks
            content = []
            for img_data in images[:5]:
                if "," in img_data:
                    media_type_part, b64 = img_data.split(",", 1)
                    media_type = media_type_part.split(":")[1].split(";")[0] if ":" in media_type_part else "image/png"
                else:
                    b64 = img_data
                    media_type = "image/png"

                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                })

            # Build prompt based on what we need
            if field == "description":
                prompt = f"""You are a Shopify product copywriter. Based on the product images and title, write a compelling product description.

Product title: {title}

Write 2-3 sentences that highlight the product's key features, appeal, and value. Be specific about what you see in the images. Write in a professional e-commerce tone. Return ONLY the description text, no quotes or labels."""

            elif field == "seo":
                prompt = f"""You are an SEO specialist for e-commerce. Based on the product images, title, and description, generate:

Product title: {title}
Product description: {description}

Return a JSON object with exactly these two fields:
- "meta_description": A compelling meta description under 155 characters for Google search results
- "tags": A comma-separated string of 5-8 relevant SEO tags/keywords

Return ONLY valid JSON, nothing else."""

            else:
                prompt = f"""You are a Shopify product copywriter and SEO specialist. Based on the product images and title, generate all product copy.

Product title: {title}

Return a JSON object with exactly these fields:
- "description": 2-3 sentence compelling product description highlighting features and value
- "meta_description": Meta description under 155 characters for Google
- "tags": Comma-separated string of 5-8 SEO tags

Return ONLY valid JSON, nothing else."""

            content.append({"type": "text", "text": prompt})

            api_body = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "messages": [{"role": "user", "content": content}],
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=api_body,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())

            text = result["content"][0]["text"].strip()

            # Parse response based on field type
            if field == "description":
                response = json.dumps({"description": text})
            elif field == "seo":
                parsed = json.loads(text)
                response = json.dumps(parsed)
            else:
                parsed = json.loads(text)
                response = json.dumps(parsed)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"AI API error {e.code}: {err_body}"})
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
