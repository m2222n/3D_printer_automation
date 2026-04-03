from __future__ import annotations

import socket


def encode_st_frame(payload: str) -> bytes:
    return f'ST/{payload}\n'.encode('utf-8')


def decode_st_frame(raw: bytes) -> str:
    txt = raw.decode('utf-8', errors='ignore').strip()
    if txt.startswith('ST/'):
        return txt[3:]
    return txt


class StFramedTcpClient:
    """
    TCP client for ST/<payload>\\n framed protocol.
    """

    def __init__(self, host: str, port: int, timeout_seconds: float = 5.0):
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def request(self, payload: str) -> tuple[bool, str]:
        frame = encode_st_frame(payload)
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds) as sock:
                sock.settimeout(self.timeout_seconds)
                sock.sendall(frame)
                response = self._recv_line(sock)
                return True, decode_st_frame(response)
        except Exception as exc:
            return False, str(exc)

    def _recv_line(self, sock: socket.socket) -> bytes:
        chunks: list[bytes] = []
        while True:
            b = sock.recv(1)
            if not b:
                break
            chunks.append(b)
            if b == b'\n':
                break
        return b''.join(chunks)
