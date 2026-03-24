from __future__ import annotations

import json
import mimetypes
import os
import uuid
from urllib import error, request


class WebApiPrinterClient:
    """
    Thin HTTP client for web-api print endpoints used by PrinterSequence.
    """

    def __init__(self, base_url: str, timeout_seconds: int = 15) -> None:
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds

    def upload_file(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            return {'ok': False, 'error': f'file not found: {file_path}'}

        boundary = f'----SequenceServiceBoundary{uuid.uuid4().hex}'
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        body = []
        body.append(f'--{boundary}\r\n'.encode('utf-8'))
        body.append(
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode('utf-8')
        )
        body.append(f'Content-Type: {content_type}\r\n\r\n'.encode('utf-8'))
        body.append(file_bytes)
        body.append(f'\r\n--{boundary}--\r\n'.encode('utf-8'))
        payload = b''.join(body)

        req = request.Request(
            url=f'{self.base_url}/api/v1/local/upload',
            data=payload,
            method='POST',
            headers={
                'Content-Type': f'multipart/form-data; boundary={boundary}',
                'Content-Length': str(len(payload)),
            },
        )
        return self._send(req)

    def start_print(
        self,
        stl_file: str,
        printer_serial: str,
        simul_mode: bool = False,
        preset_id: str | None = None,
        settings: dict | None = None,
    ) -> dict:
        payload = {
            'stl_file': stl_file,
            'printer_serial': printer_serial,
            'simul_mode': simul_mode,
        }
        if preset_id:
            payload['preset_id'] = preset_id
        if settings is not None:
            payload['settings'] = settings
        req_body = json.dumps(payload).encode('utf-8')
        req = request.Request(
            url=f'{self.base_url}/api/v1/local/print',
            data=req_body,
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        return self._send(req)

    def get_printer_summary(self, printer_serial: str) -> dict:
        req = request.Request(
            url=f'{self.base_url}/api/v1/printers/{printer_serial}',
            method='GET',
        )
        return self._send(req)

    def get_local_print_job(self, job_id: str) -> dict:
        req = request.Request(
            url=f'{self.base_url}/api/v1/local/print/{job_id}',
            method='GET',
        )
        return self._send(req)

    def _send(self, req: request.Request) -> dict:
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                status_code = getattr(resp, 'status', 200)
                raw = resp.read().decode('utf-8')
                data = json.loads(raw) if raw else {}
                return {'ok': True, 'status_code': status_code, 'data': data}
        except error.HTTPError as http_err:
            err_raw = ''
            try:
                err_raw = http_err.read().decode('utf-8')
            except Exception:
                err_raw = str(http_err)
            detail = ''
            if err_raw:
                try:
                    payload = json.loads(err_raw)
                    detail = str(payload.get('detail') or '')
                except Exception:
                    detail = ''

            if http_err.code == 404:
                # Keep status text readable even when server detail has encoding issues.
                msg = 'Printer not found'
            elif detail:
                msg = detail
            else:
                msg = f'HTTP {http_err.code}'

            return {'ok': False, 'status_code': http_err.code, 'error': msg}
        except Exception as exc:
            return {'ok': False, 'error': str(exc)}
