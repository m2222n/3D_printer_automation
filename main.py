import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


IS_WINDOWS = os.name == "nt"


def configure_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("all-in-one")


def resolve_web_api_python(cwd: Path) -> str:
    """
    Prefer web-api venv python only when it is usable.
    If the venv base interpreter is missing, fall back to current Python.
    """
    py = cwd / "venv" / "Scripts" / "python.exe"
    cfg = cwd / "venv" / "pyvenv.cfg"
    if not py.exists():
        return sys.executable

    if cfg.exists():
        try:
            for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith("home"):
                    _, home = line.split("=", 1)
                    base_python = Path(home.strip()) / "python.exe"
                    if not base_python.exists():
                        return sys.executable
                    break
        except Exception:
            return sys.executable
    return str(py)


def build_web_api_cmd(root: Path) -> tuple[list[str], Path, dict[str, str]]:
    cwd = root / "web-api"
    python_exec = resolve_web_api_python(cwd)
    cmd = [
        python_exec,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        os.getenv("WEB_API_HOST", "0.0.0.0"),
        "--port",
        os.getenv("WEB_API_PORT", "8085"),
    ]
    env = os.environ.copy()
    env.setdefault("DEBUG", "true")
    return cmd, cwd, env


def build_sequence_cmd(root: Path) -> tuple[list[str], Path, dict[str, str]]:
    cwd = root / "sequence_service"
    cmd = [sys.executable, "-m", "app.main"]
    env = os.environ.copy()
    # prevent duplicate web-api startup from sequence process
    env["START_WEB"] = "false"
    return cmd, cwd, env


def build_frontend_cmd(root: Path) -> tuple[list[str], Path, dict[str, str]]:
    cwd = root / "frontend"
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is not installed or not found in PATH.")
    cmd = [npm, "run", "dev", "--", "--host", os.getenv("FRONTEND_HOST", "0.0.0.0"), "--port", os.getenv("FRONTEND_PORT", "5173")]
    env = os.environ.copy()
    return cmd, cwd, env


def wrap_cmd_for_console(name: str, cmd: list[str]) -> list[str]:
    if not IS_WINDOWS:
        return cmd
    quoted = subprocess.list2cmdline(cmd)
    return ["cmd.exe", "/k", f'title {name} && call {quoted}']


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def main() -> None:
    logger = configure_logging()
    root = Path(__file__).resolve().parent

    services: list[tuple[str, subprocess.Popen]] = []

    def start_service(name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
        launch_cmd = wrap_cmd_for_console(name, cmd)
        logger.info("Starting %s: %s (cwd=%s)", name, " ".join(cmd), str(cwd))
        popen_kwargs: dict[str, object] = {
            "args": launch_cmd,
            "cwd": str(cwd),
            "env": env,
        }
        if IS_WINDOWS:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        proc = subprocess.Popen(**popen_kwargs)
        services.append((name, proc))

    def is_port_open(host: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0

    try:
        web_cmd, web_cwd, web_env = build_web_api_cmd(root)
        seq_cmd, seq_cwd, seq_env = build_sequence_cmd(root)
        start_frontend = env_flag("START_FRONTEND", False)
        fe_cmd: list[str] | None = None
        fe_cwd: Path | None = None
        fe_env: dict[str, str] | None = None
        if start_frontend:
            fe_cmd, fe_cwd, fe_env = build_frontend_cmd(root)

        web_port = int(os.getenv("WEB_API_PORT", "8085"))
        if is_port_open("127.0.0.1", web_port):
            logger.warning("web-api port %s is already in use. skip web-api start and reuse existing service.", web_port)
        else:
            start_service("web-api", web_cmd, web_cwd, web_env)
            time.sleep(1.0)
        start_service("sequence_service", seq_cmd, seq_cwd, seq_env)
        if start_frontend and fe_cmd and fe_cwd and fe_env:
            time.sleep(1.0)
            start_service("frontend", fe_cmd, fe_cwd, fe_env)
        else:
            logger.info("Frontend start skipped. Set START_FRONTEND=true to launch it.")
    except Exception as exc:
        logger.error("Startup failed: %s", exc)
        for _, p in services:
            if p.poll() is None:
                p.terminate()
        raise SystemExit(1)

    stop = {"value": False}

    def _handle_stop(signum, frame) -> None:
        stop["value"] = True

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    logger.info("All services started. Press Ctrl+C to stop.")
    logger.info("web-api: http://127.0.0.1:%s", os.getenv("WEB_API_PORT", "8085"))
    if env_flag("START_FRONTEND", False):
        logger.info("frontend: http://127.0.0.1:%s", os.getenv("FRONTEND_PORT", "5173"))

    try:
        while not stop["value"]:
            for name, proc in services:
                code = proc.poll()
                if code is not None:
                    logger.error("%s exited unexpectedly (code=%s). stopping all.", name, code)
                    stop["value"] = True
                    break
            time.sleep(0.5)
    finally:
        logger.info("Stopping all services...")
        for name, proc in reversed(services):
            if proc.poll() is None:
                logger.info("Terminate %s (pid=%s)", name, proc.pid)
                proc.terminate()
        deadline = time.time() + 10
        for name, proc in reversed(services):
            if proc.poll() is None:
                remaining = max(0.5, deadline - time.time())
                try:
                    proc.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    logger.warning("Kill %s (pid=%s)", name, proc.pid)
                    proc.kill()
        logger.info("Stopped.")


if __name__ == "__main__":
    main()
