"""
Local API 라우터
================
프리셋 관리, 파일 업로드, 프린트 작업 API
"""

import os
import logging
import shutil
import csv
import importlib.util
from typing import Optional, List
from pathlib import Path
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from datetime import datetime, timezone, timedelta

from app.core.config import get_settings
from app.local.database import get_local_db
from app.local.services import PresetService, PrintJobService
from app.services.polling_service import get_polling_service
from app.local.preform_client import get_preform_client, PreFormServerClient
from app.local.schemas import (
    PresetCreate, PresetUpdate, PresetResponse, PresetListResponse,
    PrintJobCreate, PrintJobResponse, PrintJobStatus,
    DiscoveredPrinter, PrintSettings,
    SceneEstimate, ScenePrepareRequest, DuplicateModelRequest
)
from app.local.automation_db import (
    create_command as create_sequence_command,
    list_commands as list_sequence_commands,
    list_logs as list_sequence_logs,
    set_commands_use_yn as set_sequence_commands_use_yn,
    set_cell_state as set_sequence_cell_state,
    get_cell_state as get_sequence_cell_state,
    get_queue_state as get_sequence_queue_state,
    probe_tcp,
    send_st_framed,
    get_comm_targets,
    set_comm_targets,
)
from app.local.ajin_io import get_ajin_gateway

logger = logging.getLogger(__name__)

# 한국 표준시 (KST = UTC+9)
KST = timezone(timedelta(hours=9))

def to_kst_iso(dt: Optional[datetime]) -> Optional[str]:
    """datetime을 KST ISO 문자열로 변환. timezone-naive이면 UTC로 간주."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).isoformat()
router = APIRouter()
settings = get_settings()


@lru_cache(maxsize=1)
def _get_sequence_modbus_client_class():
    """
    Reuse sequence_service Modbus wrapper without duplicating protocol logic.
    """
    mod_file = (Path(__file__).resolve().parents[3] / "sequence_service" / "app" / "cell" / "modbus_protocol.py").resolve()
    if not mod_file.exists():
        raise RuntimeError(f"sequence modbus_protocol.py not found: {mod_file}")

    spec = importlib.util.spec_from_file_location("sequence_modbus_protocol", str(mod_file))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for: {mod_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = getattr(module, "ModbusHandshakeClient", None)
    if cls is None:
        raise RuntimeError("ModbusHandshakeClient not found in sequence modbus_protocol.py")
    return cls


@lru_cache(maxsize=1)
def _load_io_csv_map() -> dict:
    """
    Load IO.csv and build board-wise input/output label maps.
    """
    csv_path = Path(settings.AJIN_IO_CSV_PATH)
    if not csv_path.is_absolute():
        csv_path = (Path(__file__).resolve().parents[2] / csv_path).resolve()

    result: dict[int, dict[str, dict[int, str]]] = {}
    if not csv_path.exists():
        return result

    # IO.csv can be utf-8-sig or cp949 depending on source tooling.
    rows = None
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                rows = list(csv.DictReader(f))
            break
        except Exception:
            rows = None
    if rows is None:
        return result

    for r in rows:
        try:
            in_out = int((r.get("IN_OUT") or "").strip())
            board_no = int((r.get("Board_No") or "").strip())
            address = int((r.get("Address") or "").strip())
        except Exception:
            continue
        wire_num = (r.get("WIRE_NUM") or "").strip()
        name = (r.get("NAME") or "").strip()
        label = name or wire_num or f'{"IN" if in_out == 0 else "OUT"}{address}'
        b = result.setdefault(board_no, {"inputs": {}, "outputs": {}})
        if in_out == 0:
            b["inputs"][address] = label
        else:
            b["outputs"][address] = label
    return result


# ===========================================
# 헬스체크 & 상태
# ===========================================

@router.get(
    "/health",
    tags=["Local API"],
    summary="Local API 상태 확인"
)
async def health_check():
    """Local API 및 PreFormServer 연결 상태 확인"""
    client = await get_preform_client()
    preform_connected = await client.health_check()

    return {
        "local_api": "ok",
        "preform_server": "connected" if preform_connected else "disconnected",
        "preform_server_url": f"http://{settings.PREFORM_SERVER_HOST}:{settings.PREFORM_SERVER_PORT}"
    }


# ===========================================
# 프린터 검색
# ===========================================

@router.post(
    "/printers/discover",
    response_model=List[DiscoveredPrinter],
    tags=["Local API"],
    summary="네트워크 프린터 검색"
)
async def discover_printers(timeout: int = Query(10, ge=5, le=60)):
    """
    로컬 네트워크에서 Form 프린터 검색

    - PreFormServer가 실행 중이어야 함
    - 프린터와 같은 네트워크에 있어야 함
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="PreFormServer에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요."
        )

    printers = await client.discover_printers(timeout)
    return printers


# ===========================================
# 프리셋 CRUD
# ===========================================

@router.post(
    "/presets",
    response_model=PresetResponse,
    tags=["Presets"],
    summary="프리셋 생성"
)
async def create_preset(data: PresetCreate, db: Session = Depends(get_local_db)):
    """
    새 프린트 프리셋 생성

    - 부품별 최적 세팅을 저장
    - 나중에 동일한 세팅으로 빠르게 출력 가능
    """
    service = PresetService(db)
    return service.create(data)


@router.get(
    "/presets",
    response_model=PresetListResponse,
    tags=["Presets"],
    summary="프리셋 목록 조회"
)
async def list_presets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    part_type: Optional[str] = None,
    printer_serial: Optional[str] = Query(None, description="프린터 시리얼 (지정 시 해당 프린터 전용만)"),
    db: Session = Depends(get_local_db)
):
    """프리셋 목록 조회 (페이지네이션 지원, 프린터별 필터링)"""
    service = PresetService(db)
    items, total = service.list(skip=skip, limit=limit, part_type=part_type, printer_serial=printer_serial)
    return PresetListResponse(items=items, total=total)


@router.get(
    "/presets/{preset_id}",
    response_model=PresetResponse,
    tags=["Presets"],
    summary="프리셋 상세 조회"
)
async def get_preset(preset_id: str, db: Session = Depends(get_local_db)):
    """특정 프리셋 상세 정보 조회"""
    service = PresetService(db)
    preset = service.get(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")
    return preset


@router.put(
    "/presets/{preset_id}",
    response_model=PresetResponse,
    tags=["Presets"],
    summary="프리셋 수정"
)
async def update_preset(
    preset_id: str,
    data: PresetUpdate,
    db: Session = Depends(get_local_db)
):
    """프리셋 정보 수정"""
    service = PresetService(db)
    preset = service.update(preset_id, data)
    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")
    return preset


@router.delete(
    "/presets/{preset_id}",
    tags=["Presets"],
    summary="프리셋 삭제"
)
async def delete_preset(preset_id: str, db: Session = Depends(get_local_db)):
    """프리셋 삭제"""
    service = PresetService(db)
    if not service.delete(preset_id):
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")
    return {"message": "프리셋이 삭제되었습니다"}


# ===========================================
# 파일 업로드
# ===========================================

@router.post(
    "/upload",
    tags=["Files"],
    summary="STL 파일 업로드"
)
async def upload_file(file: UploadFile = File(...)):
    """
    STL 파일 업로드

    - 지원 형식: .stl, .obj, .form
    - 최대 크기: 100MB
    """
    # 확장자 검증
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {settings.ALLOWED_EXTENSIONS}"
        )

    # 파일 크기 검증 (대략적)
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)

    if size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 너무 큽니다. 최대: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    # 업로드 디렉토리 생성
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 파일 저장
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info(f"📁 파일 업로드: {file.filename} ({size / 1024 / 1024:.2f}MB)")

    return {
        "filename": file.filename,
        "size_bytes": size,
        "path": str(file_path.resolve())
    }


@router.get(
    "/files",
    tags=["Files"],
    summary="업로드된 파일 목록"
)
async def list_files():
    """업로드된 STL 파일 목록 조회"""
    upload_dir = Path(settings.UPLOAD_DIR)
    if not upload_dir.exists():
        return {"files": []}

    files = []
    for f in upload_dir.iterdir():
        if f.is_file() and f.suffix.lower() in settings.ALLOWED_EXTENSIONS:
            files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "modified_at": f.stat().st_mtime
            })

    return {"files": sorted(files, key=lambda x: x["modified_at"], reverse=True)}


@router.delete(
    "/files/{filename}",
    tags=["Files"],
    summary="업로드된 파일 삭제"
)
async def delete_file(filename: str):
    """업로드된 파일 삭제"""
    file_path = Path(settings.UPLOAD_DIR) / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    os.remove(file_path)
    logger.info(f"🗑️ 파일 삭제: {filename}")

    return {"message": "파일이 삭제되었습니다"}


# ===========================================
# 프린트 작업
# ===========================================

async def _process_print_job(
    job_id: str,
    stl_path: str,
    printer_serial: str,
    print_settings: PrintSettings,
    db: Session
):
    """백그라운드에서 프린트 작업 처리"""
    job_service = PrintJobService(db)

    # 상태: 준비 중
    job_service.update_status(job_id, PrintJobStatus.PREPARING)

    client = await get_preform_client()
    result = await client.prepare_and_print(
        stl_path=stl_path,
        printer_serial=printer_serial,
        settings=print_settings
    )

    if result["success"]:
        job_service.update_status(
            job_id,
            PrintJobStatus.SENT,
            scene_id=result.get("scene_id"),
            estimated_print_time_ms=result.get("estimated_print_time_ms"),
            estimated_material_ml=result.get("estimated_material_ml")
        )
    else:
        job_service.update_status(
            job_id,
            PrintJobStatus.FAILED,
            scene_id=result.get("scene_id"),
            error_message=result.get("error")
        )


@router.post(
    "/print",
    response_model=PrintJobResponse,
    tags=["Print Jobs"],
    summary="프린트 작업 시작"
)
async def start_print_job(
    data: PrintJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_local_db)
):
    """
    프린트 작업 시작

    - 프리셋 ID 또는 직접 설정으로 프린트 시작
    - 백그라운드에서 STL 처리 및 프린터 전송
    """
    preset_service = PresetService(db)
    job_service = PrintJobService(db)

    if data.simul_mode:
        stl_filename = data.stl_file
        if not stl_filename:
            raise HTTPException(status_code=400, detail="simul_mode requires stl_file")
        stl_path = Path(settings.UPLOAD_DIR) / stl_filename
        if not stl_path.exists():
            raise HTTPException(status_code=404, detail=f"STL file not found: {stl_filename}")

        print_settings = data.settings or PrintSettings()
        job = job_service.create(data, stl_filename, print_settings)
        job = job_service.update_status(job.id, PrintJobStatus.SENT) or job
        return job

    # 프린터 readiness 검증
    try:
        polling_svc = await get_polling_service()
        printer_summary = polling_svc.get_printer_summary(data.printer_serial)
        if printer_summary:
            issues = []
            if not printer_summary.is_ready:
                issues.append("프린터가 준비되지 않았습니다 (NOT READY)")
            if printer_summary.is_cartridge_missing:
                issues.append("레진 카트리지가 장착되지 않았습니다")
            if printer_summary.is_tank_missing:
                issues.append("레진 탱크가 장착되지 않았습니다")
            if printer_summary.build_platform_contents in (
                "BUILD_PLATFORM_CONTENTS_MISSING", "MISSING"
            ):
                issues.append("빌드 플레이트가 설치되지 않았습니다")
            if printer_summary.build_platform_contents in (
                "BUILD_PLATFORM_CONTENTS_HAS_PARTS", "HAS_PARTS"
            ):
                issues.append("빌드 플레이트에 이전 부품이 남아있습니다")
            if not printer_summary.is_online:
                issues.append("프린터가 오프라인 상태입니다")
            if issues:
                raise HTTPException(
                    status_code=409,
                    detail={"message": "프린터 준비 상태 확인 필요", "issues": issues}
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"⚠️ 프린터 readiness 확인 실패 (무시): {e}")

    # 설정 결정 (프리셋 또는 직접 입력)
    if data.preset_id:
        preset = preset_service.get(data.preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")
        print_settings = preset.settings
        stl_filename = preset.stl_filename or data.stl_file
    else:
        if not data.settings:
            raise HTTPException(status_code=400, detail="프리셋 ID 또는 설정이 필요합니다")
        print_settings = data.settings
        stl_filename = data.stl_file

    if not stl_filename:
        raise HTTPException(status_code=400, detail="STL 파일이 지정되지 않았습니다")

    # 파일 존재 확인
    stl_path = Path(settings.UPLOAD_DIR) / stl_filename
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail=f"STL 파일을 찾을 수 없습니다: {stl_filename}")

    # 작업 생성
    job = job_service.create(data, stl_filename, print_settings)

    # 프리셋 사용 시 카운트 증가
    if data.preset_id:
        preset_service.increment_print_count(data.preset_id)

    # 백그라운드 작업 시작
    background_tasks.add_task(
        _process_print_job,
        job.id,
        str(stl_path),
        data.printer_serial,
        print_settings,
        db
    )

    return job


@router.get(
    "/print/{job_id}",
    response_model=PrintJobResponse,
    tags=["Print Jobs"],
    summary="프린트 작업 상태 조회"
)
async def get_print_job(job_id: str, db: Session = Depends(get_local_db)):
    """프린트 작업 상태 조회"""
    service = PrintJobService(db)
    job = service.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="프린트 작업을 찾을 수 없습니다")
    return job


@router.get(
    "/print",
    response_model=List[PrintJobResponse],
    tags=["Print Jobs"],
    summary="프린트 작업 목록 조회"
)
async def list_print_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_local_db)
):
    """프린트 작업 목록 조회"""
    service = PrintJobService(db)
    return service.list(skip=skip, limit=limit)


# ===========================================
# 슬라이스 준비 + 예측
# ===========================================

@router.post(
    "/scene/prepare",
    response_model=SceneEstimate,
    tags=["Scene"],
    summary="슬라이스 준비 및 예측"
)
async def prepare_scene(data: ScenePrepareRequest):
    """
    STL 파일을 슬라이스 준비하고 예측 결과 반환

    - Scene 생성 → 모델 임포트 → 자동 방향/서포트/배치 → 예측 결과
    - 프린터로 전송하지 않음 (확인 후 별도 전송)
    - 반환된 scene_id로 /scene/{scene_id}/print 호출하여 프린터 전송
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="PreFormServer에 연결할 수 없습니다"
        )

    # 파일 존재 확인
    stl_path = Path(settings.UPLOAD_DIR) / data.stl_file
    if not stl_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"STL 파일을 찾을 수 없습니다: {data.stl_file}"
        )

    result = await client.prepare_scene(
        stl_path=str(stl_path),
        machine_type=data.machine_type,
        material_code=data.material_code,
        layer_thickness_mm=data.layer_thickness_mm,
        support_density=data.support_density,
        touchpoint_size=data.touchpoint_size,
        hollow=data.hollow,
        hollow_wall_thickness_mm=data.hollow_wall_thickness_mm,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=f"슬라이스 준비 실패: {result.get('error', '알 수 없는 오류')}"
        )

    return result["estimate"]


@router.post(
    "/scene/{scene_id}/print",
    tags=["Scene"],
    summary="준비된 Scene을 프린터로 전송"
)
async def print_prepared_scene(
    scene_id: str,
    printer_serial: str = Query(..., description="프린터 시리얼 번호"),
    job_name: Optional[str] = Query(None, description="작업 이름"),
):
    """
    슬라이스 준비가 완료된 Scene을 프린터로 전송

    - /scene/prepare로 얻은 scene_id 사용
    - 예측 결과 확인 후 프린트 시작 시 호출
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(
            status_code=503,
            detail="PreFormServer에 연결할 수 없습니다"
        )

    success = await client.send_to_printer(
        scene_id=scene_id,
        printer_serial=printer_serial,
        job_name=job_name or "print-job"
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="프린터 전송 실패"
        )

    return {
        "success": True,
        "message": "프린터로 전송 완료",
        "scene_id": scene_id,
        "printer_serial": printer_serial,
    }


@router.delete(
    "/scene/{scene_id}",
    tags=["Scene"],
    summary="준비된 Scene 삭제"
)
async def delete_scene(scene_id: str):
    """
    슬라이스 준비된 Scene을 삭제 (프린트 취소 시)
    """
    client = await get_preform_client()
    success = await client.delete_scene(scene_id)

    if not success:
        raise HTTPException(status_code=500, detail="Scene 삭제 실패")

    return {"success": True, "message": "Scene이 삭제되었습니다"}


# ===========================================
# Scene 유효성 검사 / 모델 복제 / 재료 목록
# ===========================================

@router.get(
    "/scene/{scene_id}/validate",
    tags=["Scene"],
    summary="프린트 전 유효성 검사"
)
async def validate_scene(scene_id: str):
    """Scene의 프린트 유효성 검사 (서포트, 빌드 영역 등)"""
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(status_code=503, detail="PreFormServer에 연결할 수 없습니다")

    result = await client.validate_scene(scene_id)
    return result


@router.get(
    "/scene/{scene_id}/models",
    tags=["Scene"],
    summary="Scene 모델 목록 조회"
)
async def get_scene_models(scene_id: str):
    """Scene에 포함된 모델 목록 (모델 ID 포함)"""
    client = await get_preform_client()
    models = await client.get_scene_models(scene_id)
    return {"models": models}


@router.post(
    "/scene/{scene_id}/models/{model_id}/duplicate",
    tags=["Scene"],
    summary="모델 복제 (대량 배치)"
)
async def duplicate_model(scene_id: str, model_id: str, data: DuplicateModelRequest):
    """
    모델을 N개 복제하고 자동 재배치

    - 키링 같은 소형 부품을 빌드 플레이트에 최대한 채우기 위해 사용
    - 복제 후 자동으로 auto-layout, 유효성 검사 수행
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(status_code=503, detail="PreFormServer에 연결할 수 없습니다")

    if not await client.duplicate_model(scene_id, model_id, data.count):
        raise HTTPException(status_code=500, detail="모델 복제 실패")

    # 복제 후 자동 재배치
    await client.auto_layout(scene_id)

    # 업데이트된 Scene 정보 반환
    scene_info = await client.get_scene_info(scene_id)
    validation = await client.validate_scene(scene_id)

    est_time_ms = scene_info.estimated_print_time_ms if scene_info else None
    est_time_min = round(est_time_ms / 60000, 1) if est_time_ms else None

    # 정밀 시간 예측
    precise_time = await client.estimate_print_time(scene_id)
    precise_total_s = None
    precise_preprint_s = None
    precise_printing_s = None
    if precise_time:
        precise_total_s = precise_time.get("total_print_time_s")
        precise_preprint_s = precise_time.get("preprint_time_s")
        precise_printing_s = precise_time.get("printing_time_s")
        if precise_total_s:
            est_time_ms = int(precise_total_s * 1000)
            est_time_min = round(precise_total_s / 60, 1)

    # 간섭 검사
    interferences = await client.get_interferences(scene_id)

    # 스크린샷 갱신
    screenshot_filename = f"{scene_id}.png"
    screenshot_path = f"C:\\STL_Files\\screenshots\\{screenshot_filename}"
    screenshot_url = None
    if await client.save_screenshot(scene_id, screenshot_path):
        screenshot_url = f"/api/v1/local/scene/{scene_id}/screenshot/{screenshot_filename}"

    return {
        "success": True,
        "model_count": scene_info.model_count if scene_info else 0,
        "estimated_print_time_ms": est_time_ms,
        "estimated_print_time_min": est_time_min,
        "estimated_material_ml": scene_info.estimated_material_ml if scene_info else None,
        "validation": validation,
        "precise_total_s": precise_total_s,
        "precise_preprint_s": precise_preprint_s,
        "precise_printing_s": precise_printing_s,
        "interferences": interferences,
        "screenshot_url": screenshot_url,
    }


@router.get(
    "/materials",
    tags=["Local API"],
    summary="사용 가능한 재료(레진) 목록"
)
async def list_materials():
    """PreFormServer에서 사용 가능한 재료 목록 조회"""
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(status_code=503, detail="PreFormServer에 연결할 수 없습니다")

    materials = await client.list_materials()
    return {"materials": materials}


# ===========================================
# 스크린샷 / 정밀 시간 예측 / 간섭 검사
# ===========================================

@router.get(
    "/scene/{scene_id}/screenshot/{filename}",
    tags=["Scene"],
    summary="스크린샷 이미지 프록시"
)
async def get_screenshot(scene_id: str, filename: str):
    """
    공장 PC에 저장된 스크린샷 이미지를 프록시로 서빙

    - PreFormServer의 save-screenshot으로 공장 PC에 저장된 PNG 반환
    - 프론트엔드에서 직접 img src로 사용 가능
    """
    from fastapi.responses import Response

    client = await get_preform_client()
    image_data = await client._download_screenshot_from_factory(filename)

    if not image_data:
        raise HTTPException(status_code=404, detail="스크린샷을 찾을 수 없습니다")

    content_type = "image/png" if filename.endswith(".png") else "image/webp"
    return Response(
        content=image_data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"}
    )


@router.post(
    "/scene/{scene_id}/estimate-time",
    tags=["Scene"],
    summary="정밀 프린트 시간 예측"
)
async def estimate_print_time(scene_id: str):
    """
    슬라이스 완료된 Scene의 정밀 시간 예측

    - 기본 예측보다 정확한 시간 반환 (프린트 전 준비 + 실제 프린팅 분리)
    - 계산에 시간이 걸릴 수 있음 (최대 수 분)
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(status_code=503, detail="PreFormServer에 연결할 수 없습니다")

    result = await client.estimate_print_time(scene_id)
    if not result:
        raise HTTPException(status_code=500, detail="시간 예측 실패")

    # 분 단위 변환 추가
    total_s = result.get("total_print_time_s", 0)
    result["total_print_time_min"] = round(total_s / 60, 1) if total_s else 0

    return result


@router.post(
    "/scene/{scene_id}/interferences",
    tags=["Scene"],
    summary="모델 간 간섭(충돌) 검사"
)
async def get_interferences(
    scene_id: str,
    collision_offset_mm: Optional[float] = Query(None, ge=0, description="간섭 판단 최소 거리 (mm)")
):
    """
    Scene 내 모델들의 간섭(겹침) 검사

    - 모델 복제(duplicate) 후 겹치는 모델 쌍 확인
    - collision_offset_mm: 이 거리보다 가까우면 간섭으로 판단
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(status_code=503, detail="PreFormServer에 연결할 수 없습니다")

    pairs = await client.get_interferences(scene_id, collision_offset_mm)
    return {
        "interferences": pairs,
        "count": len(pairs),
        "has_interferences": len(pairs) > 0,
    }


@router.post(
    "/scene/{scene_id}/screenshot",
    tags=["Scene"],
    summary="스크린샷 수동 저장"
)
async def save_screenshot(
    scene_id: str,
    view_type: str = Query("ZOOM_ON_MODELS", description="카메라 뷰 (ZOOM_ON_MODELS, FULL_BUILD_VOLUME, FULL_PLATFORM_WIDTH)"),
    image_size_px: int = Query(820, ge=100, le=2000, description="이미지 크기 (px)"),
):
    """
    Scene의 스크린샷을 수동으로 저장

    - prepare_scene에서 자동으로 저장되지만, 복제 후 다시 찍을 때 사용
    - 반환된 screenshot_url로 이미지 접근 가능
    """
    client = await get_preform_client()

    if not await client.health_check():
        raise HTTPException(status_code=503, detail="PreFormServer에 연결할 수 없습니다")

    screenshot_filename = f"{scene_id}.png"
    screenshot_path = f"C:\\STL_Files\\screenshots\\{screenshot_filename}"

    success = await client.save_screenshot(
        scene_id, screenshot_path,
        view_type=view_type,
        image_size_px=image_size_px,
    )

    if not success:
        raise HTTPException(status_code=500, detail="스크린샷 저장 실패")

    return {
        "success": True,
        "screenshot_url": f"/api/v1/local/scene/{scene_id}/screenshot/{screenshot_filename}",
    }


# ===========================================
# 빠른 프린트 (프리셋 기반)
# ===========================================

@router.post(
    "/presets/{preset_id}/print",
    response_model=PrintJobResponse,
    tags=["Presets"],
    summary="프리셋으로 바로 프린트"
)
async def print_with_preset(
    preset_id: str,
    printer_serial: str = Query(..., description="프린터 시리얼 번호"),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_local_db)
):
    """
    저장된 프리셋으로 바로 프린트 시작

    - 프리셋에 STL 파일이 연결되어 있어야 함
    """
    preset_service = PresetService(db)
    preset = preset_service.get(preset_id)

    if not preset:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")

    if not preset.stl_filename:
        raise HTTPException(status_code=400, detail="프리셋에 STL 파일이 연결되어 있지 않습니다")

    # PrintJobCreate 생성
    job_data = PrintJobCreate(
        preset_id=preset_id,
        printer_serial=printer_serial
    )

    return await start_print_job(job_data, background_tasks, db)


# ===========================================
# 메모 (Notes) API
# ===========================================

@router.get(
    "/notes/{print_guid}",
    tags=["Notes"],
    summary="프린트 작업 메모 조회"
)
async def get_notes(print_guid: str, db: Session = Depends(get_local_db)):
    """특정 프린트 작업의 메모 목록 조회"""
    from app.local.models import PrintNote
    notes = db.query(PrintNote).filter(
        PrintNote.print_guid == print_guid
    ).order_by(PrintNote.created_at.desc()).all()
    return [
        {
            "id": n.id,
            "print_guid": n.print_guid,
            "content": n.content,
            "created_at": to_kst_iso(n.created_at),
            "updated_at": to_kst_iso(n.updated_at),
        }
        for n in notes
    ]


@router.get(
    "/notes",
    tags=["Notes"],
    summary="여러 프린트 작업의 메모 일괄 조회"
)
async def get_notes_bulk(
    guids: str = Query(..., description="콤마로 구분된 print_guid 목록"),
    db: Session = Depends(get_local_db)
):
    """여러 프린트 작업의 메모를 한 번에 조회"""
    from app.local.models import PrintNote
    guid_list = [g.strip() for g in guids.split(",") if g.strip()]
    notes = db.query(PrintNote).filter(
        PrintNote.print_guid.in_(guid_list)
    ).order_by(PrintNote.created_at.desc()).all()
    result: dict = {}
    for n in notes:
        if n.print_guid not in result:
            result[n.print_guid] = []
        result[n.print_guid].append({
            "id": n.id,
            "content": n.content,
            "created_at": to_kst_iso(n.created_at),
            "updated_at": to_kst_iso(n.updated_at),
        })
    return result


@router.post(
    "/notes/{print_guid}",
    tags=["Notes"],
    summary="프린트 작업에 메모 추가"
)
async def create_note(
    print_guid: str,
    body: dict,
    db: Session = Depends(get_local_db)
):
    """프린트 작업에 메모를 추가"""
    from app.local.models import PrintNote
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="메모 내용이 비어있습니다")

    note = PrintNote(print_guid=print_guid, content=content)
    db.add(note)
    db.commit()
    db.refresh(note)

    return {
        "id": note.id,
        "print_guid": note.print_guid,
        "content": note.content,
        "created_at": to_kst_iso(note.created_at),
    }


@router.put(
    "/notes/{note_id}",
    tags=["Notes"],
    summary="메모 수정"
)
async def update_note(
    note_id: str,
    body: dict,
    db: Session = Depends(get_local_db)
):
    """메모 내용 수정"""
    from app.local.models import PrintNote
    note = db.query(PrintNote).filter(PrintNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")

    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="메모 내용이 비어있습니다")

    note.content = content
    db.commit()
    db.refresh(note)

    return {
        "id": note.id,
        "print_guid": note.print_guid,
        "content": note.content,
        "updated_at": to_kst_iso(note.updated_at),
    }


@router.delete(
    "/notes/{note_id}",
    tags=["Notes"],
    summary="메모 삭제"
)
async def delete_note(note_id: str, db: Session = Depends(get_local_db)):
    """메모 삭제"""
    from app.local.models import PrintNote
    note = db.query(PrintNote).filter(PrintNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="메모를 찾을 수 없습니다")

    db.delete(note)
    db.commit()
    return {"detail": "삭제되었습니다"}


# ===========================================
# 알림 (Notifications) API
# ===========================================

@router.get(
    "/notifications",
    tags=["Notifications"],
    summary="알림 이벤트 목록 조회"
)
async def get_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    db: Session = Depends(get_local_db)
):
    """알림 이벤트 목록 조회"""
    from app.local.models import NotificationEvent
    query = db.query(NotificationEvent)
    if unread_only:
        query = query.filter(NotificationEvent.is_read == 0)
    events = query.order_by(NotificationEvent.created_at.desc()).limit(limit).all()
    unread_count = db.query(NotificationEvent).filter(NotificationEvent.is_read == 0).count()

    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "printer_serial": e.printer_serial,
                "printer_name": e.printer_name,
                "job_name": e.job_name,
                "message": e.message,
                "is_read": bool(e.is_read),
                "created_at": to_kst_iso(e.created_at),
            }
            for e in events
        ],
        "unread_count": unread_count,
    }


@router.post(
    "/notifications/mark-read",
    tags=["Notifications"],
    summary="알림 읽음 처리"
)
async def mark_notifications_read(
    body: dict = None,
    db: Session = Depends(get_local_db)
):
    """알림 읽음 처리 (전체 또는 특정 ID)"""
    from app.local.models import NotificationEvent
    body = body or {}
    ids = body.get("ids", [])

    if ids:
        db.query(NotificationEvent).filter(
            NotificationEvent.id.in_(ids)
        ).update({"is_read": 1}, synchronize_session=False)
    else:
        # 전체 읽음 처리
        db.query(NotificationEvent).filter(
            NotificationEvent.is_read == 0
        ).update({"is_read": 1}, synchronize_session=False)

    db.commit()
    unread_count = db.query(NotificationEvent).filter(NotificationEvent.is_read == 0).count()
    return {"detail": "읽음 처리 완료", "unread_count": unread_count}

# ===========================================
# Automation API (sequence_service integration)
# ===========================================

class AutomationCommandCreate(BaseModel):
    file_path: str | None = Field(default=None, max_length=1024)
    file_name: str | None = Field(default=None, max_length=255)
    preset_id: str | None = Field(default=None, max_length=36)
    washing_time: int = Field(..., ge=1, le=86400)
    curing_time: int = Field(..., ge=1, le=7200)
    target_printer: int | None = Field(default=None, ge=1, le=4) #260410 추가


class AutomationManualSend(BaseModel):
    payload: str = Field(..., min_length=1, max_length=2048)


class AutomationCommandUseUpdate(BaseModel):
    cmd_ids: list[str] = Field(..., min_length=1)
    use_yn: str = Field(..., pattern="^[YyNn]$")


class AutomationIoWrite(BaseModel):
    board_no: int = Field(default=0, ge=0, le=255)
    offset: int = Field(..., ge=0, le=255)
    value: bool = Field(...)


class AutomationCommConfigUpdate(BaseModel):
    robot_host: str = Field(..., min_length=1, max_length=255)
    robot_port: int = Field(..., ge=1, le=65535)
    vision_host: str = Field(..., min_length=1, max_length=255)
    vision_port: int = Field(..., ge=1, le=65535)


class AutomationModbusWrite(BaseModel):
    address: int = Field(..., ge=0, le=65535)
    value: int = Field(..., ge=0, le=65535)


@router.post(
    "/automation/commands",
    tags=["Automation"],
    summary="Sequence CMD 생성"
)
async def create_automation_command(body: AutomationCommandCreate, db: Session = Depends(get_local_db)):
    try:
        if not body.preset_id:
            raise HTTPException(status_code=400, detail='preset_id is required')

        resolved_file_path = (body.file_path or '').strip()
        resolved_file_name = body.file_name
        allocated_data: dict[str, object] = {}

        preset = PresetService(db).get(body.preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail='Preset not found')
        if not preset.stl_filename:
            raise HTTPException(status_code=400, detail='Selected preset has no STL file')

        resolved_file_name = preset.stl_filename
        resolved_file_path = str((Path(settings.UPLOAD_DIR) / preset.stl_filename).resolve())
        allocated_data = {
            'preset_id': preset.id,
            'preset_name': preset.name,
            'preset_part_type': preset.part_type,
            'print_settings': preset.settings.model_dump(),
            'stl_filename': preset.stl_filename,
        }

        cmd_id = create_sequence_command(
            file_path=resolved_file_path,
            file_name=resolved_file_name,
            washing_time=body.washing_time,
            curing_time=body.curing_time,
            allocated_data=allocated_data,
            target_printer=body.target_printer  #260410 추가
        )
        return {"ok": True, "cmd_id": cmd_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"automation cmd create failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/commands",
    tags=["Automation"],
    summary="Sequence CMD 목록"
)
async def get_automation_commands(limit: int = Query(100, ge=1, le=500)):
    try:
        return {"items": list_sequence_commands(limit=limit)}
    except Exception as e:
        logger.error(f"automation cmd list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/automation/commands/use",
    tags=["Automation"],
    summary="Sequence CMD use_yn bulk update"
)
async def update_automation_commands_use(body: AutomationCommandUseUpdate):
    try:
        updated = set_sequence_commands_use_yn(body.cmd_ids, body.use_yn)
        return {"ok": True, "updated": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"automation cmd use_yn update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/automation/control/{action}",
    tags=["Automation"],
    summary="Sequence START/STOP/PAUSE/RESUME"
)
async def control_automation(action: str):
    if action.lower() not in {"start", "stop", "pause", "resume"}:
        raise HTTPException(status_code=400, detail="action must be start|stop|pause|resume")
    try:
        state = set_sequence_cell_state(action)
        return {"ok": True, "state": state}
    except Exception as e:
        logger.error(f"automation control failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/state",
    tags=["Automation"],
    summary="Sequence 동작 상태"
)
async def get_automation_state():
    try:
        return get_sequence_cell_state()
    except Exception as e:
        logger.error(f"automation state read failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/queues",
    tags=["Automation"],
    summary="Sequence runtime queue snapshot"
)
async def get_automation_queues():
    try:
        return {"items": get_sequence_queue_state()}
    except Exception as e:
        logger.error(f"automation queue read failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/logs",
    tags=["Automation"],
    summary="Sequence/Program logs"
)
async def get_automation_logs(limit: int = Query(200, ge=1, le=1000)):
    try:
        return {"items": list_sequence_logs(limit=limit)}
    except Exception as e:
        logger.error(f"automation log read failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/manual/io/state",
    tags=["Automation"],
    summary="Read Ajin IO state (input/output bit list)"
)
async def automation_manual_io_state(
    board_no: int = Query(0, ge=0, le=255),
    count: int = Query(32, ge=1, le=64),
    io_type: str = Query("all"),
):
    try:
        gateway = get_ajin_gateway(
            simulation=settings.AJIN_SIMULATION,
            irq_no=settings.AJIN_IRQ_NO,
            dll_path=settings.AJIN_DLL_PATH,
        )
        io_map = _load_io_csv_map()
        input_boards = sorted([b for b, v in io_map.items() if v.get("inputs")]) if io_map else [0]
        output_boards = sorted([b for b, v in io_map.items() if v.get("outputs")]) if io_map else [0]
        boards = sorted(io_map.keys()) if io_map else [0]
        io_type_norm = (io_type or "all").strip().lower()
        if io_type_norm == "input":
            boards = input_boards or [0]
        elif io_type_norm == "output":
            boards = output_boards or [0]
        if board_no not in boards:
            board_no = boards[0]
        inputs = gateway.read_inputs(board_no=board_no, count=count)
        outputs = gateway.read_outputs(board_no=board_no, count=count)
        in_labels = [io_map.get(board_no, {}).get("inputs", {}).get(i, f"IN{i}") for i in range(count)]
        out_labels = [io_map.get(board_no, {}).get("outputs", {}).get(i, f"OUT{i}") for i in range(count)]
        return {
            "ok": True,
            "board_no": board_no,
            "available_boards": boards,
            "available_input_boards": input_boards or [0],
            "available_output_boards": output_boards or [0],
            "io_type": io_type_norm,
            "count": count,
            "simulation": settings.AJIN_SIMULATION,
            "inputs": inputs,
            "outputs": outputs,
            "input_labels": in_labels,
            "output_labels": out_labels,
            "timestamp": to_kst_iso(datetime.now(timezone.utc)),
        }
    except Exception as e:
        logger.error(f"automation io state failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/automation/manual/io/output",
    tags=["Automation"],
    summary="Write Ajin output bit"
)
async def automation_manual_io_output(body: AutomationIoWrite):
    try:
        gateway = get_ajin_gateway(
            simulation=settings.AJIN_SIMULATION,
            irq_no=settings.AJIN_IRQ_NO,
            dll_path=settings.AJIN_DLL_PATH,
        )
        ok = gateway.write_output(board_no=body.board_no, offset=body.offset, value=body.value)
        if not ok:
            raise HTTPException(status_code=502, detail="Ajin output write failed")
        # Read-back result from output port bit (do not trust requested value blindly).
        read_back_list = gateway.read_outputs(board_no=body.board_no, count=max(1, body.offset + 1))
        read_back = bool(read_back_list[body.offset]) if body.offset < len(read_back_list) else False
        return {
            "ok": True,
            "board_no": body.board_no,
            "offset": body.offset,
            "value": read_back,
            "timestamp": to_kst_iso(datetime.now(timezone.utc)),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"automation io output failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/automation/manual/robot-send",
    tags=["Automation"],
    summary="Manual TCP send to robot (ST/<payload>\\n)"
)
async def manual_robot_send(body: AutomationManualSend):
    try:
        targets = get_comm_targets()
        result = send_st_framed(
            host=str(targets.get("robot_host") or settings.ROBOT_TCP_HOST),
            port=int(targets.get("robot_port") or settings.ROBOT_TCP_PORT),
            payload=body.payload,
            timeout_seconds=settings.MANUAL_TCP_TIMEOUT_SECONDS,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "robot send failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"manual robot send failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/automation/manual/vision-send",
    tags=["Automation"],
    summary="Manual TCP send to vision (ST/<payload>\\n)"
)
async def manual_vision_send(body: AutomationManualSend):
    try:
        targets = get_comm_targets()
        result = send_st_framed(
            host=str(targets.get("vision_host") or settings.VISION_TCP_HOST),
            port=int(targets.get("vision_port") or settings.VISION_TCP_PORT),
            payload=body.payload,
            timeout_seconds=settings.MANUAL_TCP_TIMEOUT_SECONDS,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "vision send failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"manual vision send failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/manual/robot-status",
    tags=["Automation"],
    summary="Robot TCP connection status"
)
async def manual_robot_status():
    try:
        targets = get_comm_targets()
        host = str(targets.get("robot_host") or settings.ROBOT_TCP_HOST)
        port = int(targets.get("robot_port") or settings.ROBOT_TCP_PORT)
        r = probe_tcp(
            host=host,
            port=port,
            timeout_seconds=settings.MANUAL_TCP_TIMEOUT_SECONDS,
        )
        return {
            "ok": bool(r.get("ok")),
            "connected": bool(r.get("connected")),
            "host": host,
            "port": port,
            "error": r.get("error"),
            "timestamp": to_kst_iso(datetime.now(timezone.utc)),
        }
    except Exception as e:
        logger.error(f"manual robot status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/manual/vision-status",
    tags=["Automation"],
    summary="Vision TCP connection status"
)
async def manual_vision_status():
    try:
        targets = get_comm_targets()
        host = str(targets.get("vision_host") or settings.VISION_TCP_HOST)
        port = int(targets.get("vision_port") or settings.VISION_TCP_PORT)
        r = probe_tcp(
            host=host,
            port=port,
            timeout_seconds=settings.MANUAL_TCP_TIMEOUT_SECONDS,
        )
        return {
            "ok": bool(r.get("ok")),
            "connected": bool(r.get("connected")),
            "host": host,
            "port": port,
            "error": r.get("error"),
            "timestamp": to_kst_iso(datetime.now(timezone.utc)),
        }
    except Exception as e:
        logger.error(f"manual vision status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/manual/comm-config",
    tags=["Automation"],
    summary="Get manual communication target config"
)
async def get_automation_manual_comm_config():
    try:
        item = get_comm_targets()
        return {
            "ok": True,
            "robot_host": str(item.get("robot_host") or settings.ROBOT_TCP_HOST),
            "robot_port": int(item.get("robot_port") or settings.ROBOT_TCP_PORT),
            "vision_host": str(item.get("vision_host") or settings.VISION_TCP_HOST),
            "vision_port": int(item.get("vision_port") or settings.VISION_TCP_PORT),
            "updated_at": to_kst_iso(item.get("updated_at")),
        }
    except Exception as e:
        logger.error(f"manual comm-config read failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/automation/manual/comm-config",
    tags=["Automation"],
    summary="Update manual communication target config"
)
async def update_automation_manual_comm_config(body: AutomationCommConfigUpdate):
    try:
        item = set_comm_targets(
            robot_host=body.robot_host,
            robot_port=body.robot_port,
            vision_host=body.vision_host,
            vision_port=body.vision_port,
        )
        return {
            "ok": True,
            "robot_host": str(item.get("robot_host") or settings.ROBOT_TCP_HOST),
            "robot_port": int(item.get("robot_port") or settings.ROBOT_TCP_PORT),
            "vision_host": str(item.get("vision_host") or settings.VISION_TCP_HOST),
            "vision_port": int(item.get("vision_port") or settings.VISION_TCP_PORT),
            "updated_at": to_kst_iso(item.get("updated_at")),
        }
    except Exception as e:
        logger.error(f"manual comm-config update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/manual/modbus/registers",
    tags=["Automation"],
    summary="Read robot Modbus holding registers"
)
async def automation_manual_modbus_registers(
    start_addr: int = Query(130, ge=130, le=65535),
    end_addr: int = Query(255, ge=130, le=65535),
):
    if end_addr < start_addr:
        raise HTTPException(status_code=400, detail="end_addr must be >= start_addr")
    if (end_addr - start_addr + 1) > 1000:
        raise HTTPException(status_code=400, detail="max readable range is 1000 registers")
    targets = get_comm_targets()
    host = str(targets.get("robot_host") or settings.ROBOT_TCP_HOST)
    port = int(targets.get("robot_port") or settings.ROBOT_TCP_PORT)
    timeout_seconds = float(getattr(settings, "MANUAL_TCP_TIMEOUT_SECONDS", 5.0))
    slave_id = int(getattr(settings, "ROBOT_MODBUS_SLAVE_ID", 1))
    try:
        modbus_cls = _get_sequence_modbus_client_class()
        client = modbus_cls(
            host=host,
            port=port,
            timeout_seconds=timeout_seconds,
            slave_id=slave_id,
        )
        ok, data = client.read_range(start_addr, end_addr, block_size=100)
        if not ok:
            raise HTTPException(status_code=502, detail=f"modbus read failed: {data}")
        values = data

        return {
            "ok": True,
            "host": host,
            "port": port,
            "start_addr": start_addr,
            "end_addr": end_addr,
            "count": len(values),
            "items": values,
            "timestamp": to_kst_iso(datetime.now(timezone.utc)),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"manual modbus read failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route(
    "/automation/manual/modbus/write",
    methods=["POST", "PUT", "PATCH"],
    tags=["Automation"],
    summary="Write single robot Modbus holding register"
)
async def automation_manual_modbus_write(body: AutomationModbusWrite):
    targets = get_comm_targets()
    host = str(targets.get("robot_host") or settings.ROBOT_TCP_HOST)
    port = int(targets.get("robot_port") or settings.ROBOT_TCP_PORT)
    timeout_seconds = float(getattr(settings, "MANUAL_TCP_TIMEOUT_SECONDS", 5.0))
    slave_id = int(getattr(settings, "ROBOT_MODBUS_SLAVE_ID", 1))
    try:
        modbus_cls = _get_sequence_modbus_client_class()
        client = modbus_cls(
            host=host,
            port=port,
            timeout_seconds=timeout_seconds,
            slave_id=slave_id,
        )
        ok, result = client.write_single(body.address, body.value)
        if not ok:
            raise HTTPException(status_code=502, detail=f"modbus write failed: {result}")
        read_back = int(result) if isinstance(result, int) else body.value

        return {
            "ok": True,
            "host": host,
            "port": port,
            "address": body.address,
            "value": int(body.value),
            "read_back": read_back,
            "timestamp": to_kst_iso(datetime.now(timezone.utc)),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"manual modbus write failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/automation/manual/modbus/write",
    tags=["Automation"],
    summary="Write single robot Modbus holding register (query fallback)"
)
async def automation_manual_modbus_write_get(
    address: int = Query(..., ge=0, le=65535),
    value: int = Query(..., ge=0, le=65535),
):
    return await automation_manual_modbus_write(AutomationModbusWrite(address=address, value=value))
