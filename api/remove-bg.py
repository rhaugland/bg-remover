from http.server import BaseHTTPRequestHandler
import json
import base64
import os
from io import BytesIO

import numpy as np
import onnxruntime as ort
from PIL import Image
import requests

MODEL_PATH = "/tmp/u2netp.onnx"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"

session = None


def get_session():
    global session
    if session is not None:
        return session

    # Download model if not cached
    if not os.path.exists(MODEL_PATH):
        r = requests.get(MODEL_URL, timeout=30)
        r.raise_for_status()
        with open(MODEL_PATH, "wb") as f:
            f.write(r.content)

    session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    return session


def remove_background(input_image):
    """Remove background using U2NetP ONNX model."""
    sess = get_session()
    orig_w, orig_h = input_image.size

    # Preprocess: resize to 320x320, normalize
    img = input_image.convert("RGB").resize((320, 320), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0

    # Normalize with ImageNet mean/std
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std

    # NCHW format
    arr = np.transpose(arr, (2, 0, 1))
    arr = np.expand_dims(arr, axis=0).astype(np.float32)

    # Run inference
    input_name = sess.get_inputs()[0].name
    outputs = sess.run(None, {input_name: arr})

    # First output is the main prediction
    mask = outputs[0][0, 0]

    # Normalize mask to 0-1
    mask = mask - mask.min()
    if mask.max() > 0:
        mask = mask / mask.max()

    # Resize mask back to original size
    mask_img = Image.fromarray((mask * 255).astype(np.uint8), mode="L")
    mask_img = mask_img.resize((orig_w, orig_h), Image.BILINEAR)

    # Apply mask: product on black background
    rgba = input_image.convert("RGBA")
    mask_arr = np.array(mask_img, dtype=np.float32) / 255.0
    orig_arr = np.array(rgba, dtype=np.float32)

    # Blend: foreground * mask + black * (1 - mask)
    result = np.zeros_like(orig_arr)
    for c in range(3):
        result[:, :, c] = orig_arr[:, :, c] * mask_arr
    result[:, :, 3] = 255  # fully opaque

    return Image.fromarray(result.astype(np.uint8), mode="RGBA").convert("RGB")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_length))

            image_b64 = body.get("image", "")
            if "," in image_b64:
                image_b64 = image_b64.split(",", 1)[1]

            image_data = base64.b64decode(image_b64)
            input_image = Image.open(BytesIO(image_data))

            result = remove_background(input_image)

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
            import traceback
            traceback.print_exc()
            error = json.dumps({"error": str(e)})
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error)))
            self.end_headers()
            self.wfile.write(error.encode())
