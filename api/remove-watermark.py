from http.server import BaseHTTPRequestHandler
import json
import os
import base64
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

            image_data_url = body.get("image", "")
            if not image_data_url:
                raise ValueError("Image is required")

            # Extract media type and base64 data
            if "," in image_data_url:
                header = image_data_url.split(",")[0]
                b64data = image_data_url.split(",")[1]
                if "png" in header:
                    media_type = "image/png"
                elif "webp" in header:
                    media_type = "image/webp"
                else:
                    media_type = "image/jpeg"
            else:
                b64data = image_data_url
                media_type = "image/jpeg"

            api_body = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64data,
                                },
                            },
                            {
                                "type": "text",
                                "text": "This product image has a watermark/logo overlay on it. Please regenerate this exact same image but with the watermark completely removed. Keep the product exactly the same - same angle, same colors, same details. Only remove the watermark/logo overlay. Output just the cleaned image.",
                            },
                        ],
                    }
                ],
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=api_body,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": "image-generation-2025-04-14",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=55) as resp:
                result = json.loads(resp.read())

            # Find the image block in the response
            image_result = None
            for block in result.get("content", []):
                if block.get("type") == "image":
                    source = block.get("source", {})
                    img_b64 = source.get("data", "")
                    img_mime = source.get("media_type", "image/png")
                    image_result = f"data:{img_mime};base64,{img_b64}"
                    break

            if not image_result:
                raise ValueError("Claude did not return an image. Response: " + json.dumps(result.get("content", [])[:1]))

            response = json.dumps({"image": image_result})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            error = json.dumps({"error": f"Claude API error {e.code}: {err_body}"})
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
