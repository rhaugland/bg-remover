from http.server import BaseHTTPRequestHandler
import json
import base64
import os
from io import BytesIO

os.environ["U2NET_HOME"] = "/tmp/.u2net"

from rembg import remove, new_session
from PIL import Image

session = None

def get_session():
    global session
    if session is None:
        session = new_session("u2netp")
    return session

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            image_b64 = body.get("image", "")
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]

            image_data = base64.b64decode(image_b64)
            input_image = Image.open(BytesIO(image_data)).convert("RGBA")

            sess = get_session()
            output_image = remove(input_image, session=sess)

            black_bg = Image.new("RGBA", output_image.size, (0, 0, 0, 255))
            black_bg.paste(output_image, mask=output_image.split()[3])
            result = black_bg.convert("RGB")

            buffer = BytesIO()
            result.save(buffer, format="PNG", optimize=True)
            result_b64 = base64.b64encode(buffer.getvalue()).decode()

            response = json.dumps({"image": f"data:image/png;base64,{result_b64}"})
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
