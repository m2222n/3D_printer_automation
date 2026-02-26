"""
Local API 라우터
================
프리셋 관리, 파일 업로드, 프린트 작업 API
"""

import os
import logging
import shutil
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.local.database import get_local_db
from app.local.services import PresetService, PrintJobService
from app.local.preform_client import get_preform_client, PreFormServerClient
from app.local.schemas import (
    PresetCreate, PresetUpdate, PresetResponse, PresetListResponse,
    PrintJobCreate, PrintJobResponse, PrintJobStatus,
    DiscoveredPrinter, PrintSettings,
    SceneEstimate, ScenePrepareRequest, DuplicateModelRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


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
    db: Session = Depends(get_local_db)
):
    """프리셋 목록 조회 (페이지네이션 지원)"""
    service = PresetService(db)
    items, total = service.list(skip=skip, limit=limit, part_type=part_type)
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
        "path": str(file_path)
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

    return {
        "success": True,
        "model_count": scene_info.model_count if scene_info else 0,
        "estimated_print_time_ms": est_time_ms,
        "estimated_print_time_min": est_time_min,
        "estimated_material_ml": scene_info.estimated_material_ml if scene_info else None,
        "validation": validation,
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
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
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
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "updated_at": n.updated_at.isoformat() if n.updated_at else None,
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
        "created_at": note.created_at.isoformat() if note.created_at else None,
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
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
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
                "created_at": e.created_at.isoformat() if e.created_at else None,
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
