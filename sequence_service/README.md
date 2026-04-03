# Sequence Service

Standalone sequence runner service (separate from FastAPI web-api).

## Features
- Single controller thread (`SequenceThread`)
- Inheritance-based sequences (`SequenceBase`)
- Dataclass runtime context (`JobCtx`, `RuntimeCtx`)
- MySQL-backed job status transitions
- DB update on every step transition

## Structure
- `app/cell/runtime.py`: controller thread + sequence list
- `app/cell/sequences/print_dispatch.py`: print stage
- `app/cell/sequences/post_process.py`: cure/wash stage
- `app/cell/repository.py`: claim/update DB operations
- `app/main.py`: service entrypoint

## Run
```bash
cd sequence_service
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app/main.py
```

## Environment (.env)
```env
MYSQL_DSN=mysql+pymysql://user:password@127.0.0.1:3306/automation
SERVICE_ID=sequence-main
TICK_SECONDS=0.1
PRINT_SIM_SECONDS=30
CURE_SIM_SECONDS=120
DEFAULT_WASH_MINUTES=6
ENABLE_CELL_STATE=true
```
