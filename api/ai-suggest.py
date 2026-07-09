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

            # Anti-slop system prompt
            system = """You write like a human — short, direct, natural.

NEVER use these words or patterns:
- "elevate", "craft/crafted", "unlock", "seamless", "transform", "revolutionize", "game-changer", "next-level", "cutting-edge", "state-of-the-art"
- "whether you're...or...", "look no further", "say goodbye to", "take your X to the next level"
- "designed to", "built to", "perfect for the discerning", "redefine", "reimagine"
- Exclamation marks, em dashes for drama, rhetorical questions
- Starting with "Introducing" or "Meet the"

DO: Write like a knowledgeable friend describing the product. Be specific about materials, dimensions, colors, and features you can actually see. State facts. Keep it simple."""

            # Build prompt based on what we need
            if field == "description":
                prompt = f"""Look at these product images. The product is called "{title}".

Write 2-3 short sentences describing what this product actually is and what makes it good. Mention specific details you can see — material, color, size, texture, construction. No hype, no filler. Just describe it like you're telling a friend what it is.

Return ONLY the description text, no quotes or labels."""

            elif field == "seo":
                prompt = f"""Product: "{title}"
Description: {description}

Write a meta description and tags for this product.

Return a JSON object with exactly these two fields:
- "meta_description": Under 155 characters. Straightforward — what the product is, one key selling point. No hype words.
- "tags": Comma-separated string of 5-8 specific, searchable keywords a buyer would actually type. Include material, category, use case. No generic terms like "premium quality" or "best".

Return ONLY valid JSON, nothing else."""

            else:
                prompt = f"""Look at these product images. The product is called "{title}".

Return a JSON object with exactly these fields:
- "description": 2-3 short sentences. What is it, what's it made of, what makes it good. Specific details only.
- "meta_description": Under 155 characters. Straightforward product summary.
- "tags": Comma-separated string of 5-8 specific searchable keywords a buyer would actually type.

Return ONLY valid JSON, nothing else."""

            content.append({"type": "text", "text": prompt})

            api_body = json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 500,
                "system": system,
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

            # Strip markdown code fences if present
            if text.startswith("```"):
                lines = text.split("\n")
                # Remove first line (```json) and last line (```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines).strip()

            # Parse response based on field type
            if field == "description":
                # Try to parse as JSON in case model wrapped it
                try:
                    parsed = json.loads(text)
                    desc = parsed.get("description", text)
                except (json.JSONDecodeError, AttributeError):
                    desc = text
                response = json.dumps({"description": desc})
            else:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    # Extract JSON from surrounding text
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start >= 0 and end > start:
                        parsed = json.loads(text[start:end])
                    else:
                        parsed = {"meta_description": "", "tags": ""}
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
