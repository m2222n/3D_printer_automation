"""
공장 PC 파일 수신 서버
======================
FastAPI 서버에서 STL 파일을 받아 로컬에 저장.
PreFormServer와 함께 공장 PC에서 실행.

사용법:
    python file_receiver.py

설정:
    - 포트: 8089
    - 저장 경로: C:\STL_Files
"""

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
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    os.makedirs(SAVE_DIR, exist_ok=True)
    server = HTTPServer(("0.0.0.0", PORT), FileReceiveHandler)
    print(f"File receiver running on port {PORT}")
    print(f"Save directory: {SAVE_DIR}")
    server.serve_forever()
