from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import json

PORT = 8089
SAVE_DIR = r"C:\STL_Files"


class FileReceiveHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/upload":
            content_length = int(self.headers.get("Content-Length", 0))
            filename = self.headers.get("X-Filename", "unknown.stl")

            os.makedirs(SAVE_DIR, exist_ok=True)

            file_path = os.path.join(SAVE_DIR, filename)
            body = self.rfile.read(content_length)

            with open(file_path, "wb") as f:
                f.write(body)

            response = {
                "success": True,
                "file_path": file_path,
                "size_bytes": len(body)
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            print(f"[OK] {filename} ({len(body)} bytes) -> {file_path}")

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/":
            response = {"status": "ok", "save_dir": SAVE_DIR}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())

        elif self.path.startswith("/screenshots/"):
            # 스크린샷 이미지 다운로드
            filename = self.path.split("/screenshots/", 1)[1]
            # URL 디코딩
            from urllib.parse import unquote
            filename = unquote(filename)
            screenshot_dir = os.path.join(SAVE_DIR, "screenshots")
            file_path = os.path.join(screenshot_dir, filename)

            if os.path.exists(file_path) and os.path.isfile(file_path):
                ext = os.path.splitext(filename)[1].lower()
                content_type = "image/png" if ext == ".png" else "image/webp"
                with open(file_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                print(f"[GET] Screenshot: {filename} ({len(data)} bytes)")
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "File not found"}).encode())

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    os.makedirs(SAVE_DIR, exist_ok=True)
    server = HTTPServer(("0.0.0.0", PORT), FileReceiveHandler)
    print(f"File receiver running on port {PORT}")
    print(f"Save directory: {SAVE_DIR}")
    server.serve_forever()
