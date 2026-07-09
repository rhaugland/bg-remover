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

            # Ask Claude to find the watermark location
            api_body = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
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
                                "text": 'Look at this product image carefully. Is there a watermark, logo overlay, brand stamp, or semi-transparent text/graphic overlaid on the product? If yes, return JSON with ALL watermark regions as an array. Be GENEROUS with the bounding boxes - make them 20% larger than the visible watermark to ensure full coverage. Use percentages of image dimensions: {"found": true, "regions": [{"x": percent_from_left, "y": percent_from_top, "w": percent_width, "h": percent_height}]}. Include every part of the watermark (logo, text, wings, etc) as separate regions if they are spread apart. If no watermark found, return {"found": false}. Return ONLY JSON.',
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
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())

            text = result["content"][0]["text"].strip()
            # Extract JSON from response
            if "{" in text:
                json_str = text[text.index("{"):text.rindex("}") + 1]
                detection = json.loads(json_str)
            else:
                detection = {"found": False}

            response = json.dumps(detection)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode())

        except Exception as e:
            import traceback
            traceback.print_exc()
            error = json.dumps({"error": str(e)})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())
