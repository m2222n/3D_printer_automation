import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.cell.repository import PrintCommandRepository
from app.cell.runtime import SeqCommand, SequenceThread
from app.core.config import get_settings
from app.db.session import SessionLocal


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )


def _resolve_web_api_python(web_api_dir: Path) -> str:
    """
    Find usable python.exe for web-api in priority order:
      1) web-api/venv/Scripts/python.exe  (legacy layout)
      2) repo_root/.venv/Scripts/python.exe  (current layout)
      3) sys.executable  (last resort — may be global python without web-api deps)
    """
    repo_root = web_api_dir.parent
    candidates = [
        web_api_dir / 'venv' / 'Scripts' / 'python.exe',
        repo_root / '.venv' / 'Scripts' / 'python.exe',
    ]
    for py in candidates:
        if py.exists():
            return str(py)
    return sys.executable


def start_web_server(logger: logging.Logger) -> subprocess.Popen | None:
    """
    Start web-api server as a child process.
    Sequence thread runs in this process, web server runs in managed subprocess.
    """
    project_root = Path(__file__).resolve().parents[2]
    web_api_dir = project_root / 'web-api'

    if not web_api_dir.exists():
        logger.warning('web-api directory not found. skip web server start.')
        return None

    python_exec = _resolve_web_api_python(web_api_dir)

    cmd = [
        python_exec,
        '-m',
        'uvicorn',
        'app.main:app',
        '--host',
        os.getenv('WEB_HOST', '0.0.0.0'),
        '--port',
        os.getenv('WEB_PORT', '8085'),
    ]

    logger.info('Starting web server: %s (cwd=%s)', ' '.join(cmd), web_api_dir)
    return subprocess.Popen(cmd, cwd=str(web_api_dir))


def main() -> None:
    configure_logging()
    logger = logging.getLogger('sequence_service.main')
    settings = get_settings()

    repo = PrintCommandRepository(SessionLocal)
    repo.init_db()

    seq_thread = SequenceThread(repo=repo)
    seq_thread.start()
    logger.info('Sequence thread started')

    web_process = None
    if settings.START_WEB:
        web_process = start_web_server(logger)

    # Start in STOPPED state so newly created commands keep unassigned fields as NULL
    # until the operator presses START from UI.
    repo.set_cell_state(running=False, paused=False)
    logger.info('Cell state initialized to running=false, paused=false')

    stop_flag = {'value': False}

    def _stop_handler(signum, frame):
        stop_flag['value'] = True

    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    try:
        while not stop_flag['value']:
            if web_process and web_process.poll() is not None:
                logger.error('Web server process exited unexpectedly. stopping sequence service.')
                stop_flag['value'] = True
                break
            time.sleep(0.5)
    finally:
        logger.info('Stopping sequence thread...')
        seq_thread.push(SeqCommand.STOP)
        seq_thread.stop_thread()
        seq_thread.join(timeout=2.0)

        if web_process and web_process.poll() is None:
            logger.info('Stopping web server process...')
            web_process.terminate()
            try:
                web_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning('Web server did not stop in time. killing process...')
                web_process.kill()

        logger.info('Sequence service stopped')


if __name__ == '__main__':
    main()
