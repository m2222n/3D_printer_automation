"""
Formlabs Web API 클라이언트
============================
프린터 상태 조회, 이력 조회 등 API 호출 담당
"""

import httpx
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.core.config import get_settings
from app.core.auth import FormlabsAuthManager, get_auth_manager
from app.schemas.printer import (
    Printer, PrinterStatus, CurrentPrintRun,
    CartridgeStatus, TankStatus, PrinterSummary,
    PrintStatus, PrintHistoryItem, PrintHistoryPart, now_kst
)

logger = logging.getLogger(__name__)

# Formlabs material code → 사람이 읽기 쉬운 이름 매핑
MATERIAL_CODE_NAMES = {
    "FLGPCL05": "Clear V5",
    "FLGPGR05": "Grey V5",
    "FLGPWH05": "White V5",
    "FLGPBK05": "Black V5",
    "FLGPCL04": "Clear V4",
    "FLGPGR04": "Grey V4",
    "FLGPWH04": "White V4",
    "FLGPBK04": "Black V4",
    "FLRGWH01": "Rigid White",
    "FLFLGR02": "Flexible Grey",
    "FLFL8011": "Flexible 80A V1.1",
    "FLFL8001": "Flexible 80A",
    "FLTOTL05": "Tough 2000",
    "FLDUCL02": "Durable Clear",
    "FLHTAM02": "High Temp Amber",
    "FLDCBL01": "Draft Clear Blue",
}


class FormlabsAPIClient:
    """
    Formlabs Web API 클라이언트
    
    사용법:
        client = FormlabsAPIClient(auth_manager)
        printers = await client.get_all_printers()
    """
    
    def __init__(self, auth_manager: FormlabsAuthManager):
        self.settings = get_settings()
        self.auth = auth_manager
        self.base_url = self.settings.FORMLABS_API_BASE_URL
        
    def _api_url(self, path: str) -> str:
        """API URL 생성"""
        return f"{self.base_url}/developer/v1{path}"
    
    async def _request(
        self, 
        method: str, 
        path: str, 
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        retry_count: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        API 요청 공통 메서드
        
        - 자동 토큰 갱신
        - Rate Limit 처리 (429)
        - 에러 핸들링
        """
        url = self._api_url(path)
        
        for attempt in range(retry_count + 1):
            try:
                # 유효한 토큰 획득
                token = await self.auth.get_valid_token()
                headers = {
                    "Authorization": f"bearer {token}",
                    "Content-Type": "application/json"
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_data
                    )
                    
                    # 성공
                    if response.status_code == 200:
                        return response.json()
                    
                    # Rate Limit
                    elif response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        logger.warning(f"⚠️ Rate Limit 초과. {retry_after}초 후 재시도 필요")
                        # 여기서는 바로 반환, 호출측에서 처리
                        return None
                    
                    # 인증 오류 - 토큰 갱신 후 재시도
                    elif response.status_code == 401:
                        if attempt < retry_count:
                            logger.warning("🔄 인증 오류, 토큰 갱신 후 재시도...")
                            await self.auth._refresh_token()
                            continue
                        logger.error("❌ 인증 실패")
                        return None
                    
                    # 기타 오류
                    else:
                        logger.error(f"❌ API 오류 [{response.status_code}]: {response.text}")
                        return None
                        
            except httpx.TimeoutException:
                logger.error(f"❌ 타임아웃: {url}")
                if attempt < retry_count:
                    continue
                return None
            except httpx.RequestError as e:
                logger.error(f"❌ 네트워크 오류: {e}")
                if attempt < retry_count:
                    continue
                return None
        
        return None
    
    # ===========================================
    # 프린터 관련 API
    # ===========================================
    
    async def get_all_printers(self) -> List[Printer]:
        """
        전체 프린터 목록 및 상태 조회
        
        GET /developer/v1/printers/
        
        Returns:
            List[Printer]: 프린터 목록
        """
        data = await self._request("GET", "/printers/")
        if not data:
            return []
        
        printers = []
        # API 응답이 리스트인 경우
        items = data if isinstance(data, list) else data.get("results", [])
        
        for item in items:
            try:
                printer = self._parse_printer(item)
                printers.append(printer)
            except Exception as e:
                logger.error(f"프린터 파싱 오류: {e}")
                continue
        
        logger.info(f"📊 {len(printers)}대 프린터 상태 조회 완료")
        return printers
    
    async def get_printer(self, serial: str) -> Optional[Printer]:
        """
        특정 프린터 상세 정보 조회
        
        GET /developer/v1/printers/{printer_serial}/
        """
        data = await self._request("GET", f"/printers/{serial}/")
        if not data:
            return None
        
        return self._parse_printer(data)
    
    async def get_target_printers(self) -> List[Printer]:
        """
        설정된 프린터만 조회 (설정 없으면 전체)
        """
        all_printers = await self.get_all_printers()

        # 설정된 시리얼만 필터링 (플레이스홀더면 전체 사용)
        target_serials = set(self.settings.PRINTER_SERIALS)
        placeholder_serials = {"PRINTER_SERIAL_1", "PRINTER_SERIAL_2", "PRINTER_SERIAL_3", "PRINTER_SERIAL_4"}

        # 플레이스홀더이거나 빈 리스트면 전체 프린터 반환
        if not target_serials or target_serials == placeholder_serials:
            return all_printers

        return [p for p in all_printers if p.serial in target_serials]
    
    def _parse_printer(self, data: Dict) -> Printer:
        """API 응답을 Printer 객체로 변환"""
        
        # printer_status 파싱
        printer_status = None
        if "printer_status" in data and data["printer_status"]:
            ps = data["printer_status"]
            
            # current_print_run 파싱
            current_run = None
            if "current_print_run" in ps and ps["current_print_run"]:
                cpr = ps["current_print_run"]
                current_run = CurrentPrintRun(
                    guid=cpr.get("guid"),
                    name=cpr.get("name"),
                    status=cpr.get("status"),
                    currently_printing_layer=cpr.get("currently_printing_layer", 0),
                    layer_count=cpr.get("layer_count", 0),
                    estimated_duration_ms=cpr.get("estimated_duration_ms", 0),
                    elapsed_duration_ms=cpr.get("elapsed_duration_ms", 0),
                    estimated_time_remaining_ms=cpr.get("estimated_time_remaining_ms", 0),
                    print_started_at=self._parse_datetime(cpr.get("print_started_at")),
                    print_finished_at=self._parse_datetime(cpr.get("print_finished_at")),
                )
            
            # Enum 값 안전 파싱 (Formlabs API가 새 값 추가해도 오류 방지)
            ready_to_print = ps.get("ready_to_print")
            try:
                from app.schemas.printer import PrinterReadyState
                PrinterReadyState(ready_to_print)
            except (ValueError, KeyError):
                logger.warning(f"⚠️ 알 수 없는 ready_to_print 값: {ready_to_print}")
                ready_to_print = None

            build_platform = ps.get("build_platform_contents")
            try:
                from app.schemas.printer import BuildPlatformState
                BuildPlatformState(build_platform)
            except (ValueError, KeyError):
                logger.warning(f"⚠️ 알 수 없는 build_platform_contents 값: {build_platform}")
                build_platform = None

            printer_status = PrinterStatus(
                status=ps.get("status"),
                last_pinged_at=self._parse_datetime(ps.get("last_pinged_at")),
                current_print_run=current_run,
                ready_to_print=ready_to_print,
                build_platform_contents=build_platform,
                temperature=ps.get("temperature"),
            )
        
        # cartridge_status 파싱
        # API 응답 구조: cartridge_status.cartridge.{initial_volume_ml, volume_dispensed_ml}
        cartridge_status = None
        if "cartridge_status" in data and data["cartridge_status"]:
            cs = data["cartridge_status"]
            cartridge = cs.get("cartridge")

            if cartridge:
                initial_ml = cartridge.get("initial_volume_ml", 0) or 0
                dispensed_ml = cartridge.get("volume_dispensed_ml", 0) or 0
                remaining_ml = max(0, initial_ml - dispensed_ml)

                cartridge_status = CartridgeStatus(
                    serial=cartridge.get("serial"),
                    material_code=cartridge.get("material"),
                    material_name=cartridge.get("display_name"),
                    initial_ml=initial_ml,
                    remaining_ml=remaining_ml,
                )
        
        # tank_status 파싱
        # API 응답 구조: tank_status.tank.{serial, material, ...}
        tank_status = None
        if "tank_status" in data and data["tank_status"]:
            ts = data["tank_status"]
            tank = ts.get("tank")

            if tank:
                tank_status = TankStatus(
                    serial=tank.get("serial"),
                    material_code=tank.get("material"),
                    print_count=tank.get("print_count", 0),
                    days_since_first_print=tank.get("days_since_first_print", 0),
                )
        
        return Printer(
            serial=data.get("serial", ""),
            alias=data.get("alias"),
            machine_type=data.get("machine_type"),
            printer_status=printer_status,
            cartridge_status=cartridge_status,
            tank_status=tank_status,
            firmware_version=data.get("firmware_version"),
            created_at=self._parse_datetime(data.get("created_at")),
            is_remote_print_enabled=data.get("is_remote_print_enabled"),
            group_name=data.get("group_name"),
            location=data.get("location"),
        )
    
    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        """날짜/시간 문자열 파싱"""
        if not value:
            return None
        try:
            # ISO 8601 형식
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    
    # ===========================================
    # 프린트 이력 API
    # ===========================================
    
    async def _request_full_url(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
    ) -> Optional[Dict[str, Any]]:
        """절대 URL로 API 요청 (페이지네이션 next URL용)"""
        try:
            token = await self.auth.get_valid_token()
            headers = {
                "Authorization": f"bearer {token}",
                "Content-Type": "application/json"
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method, url=url, headers=headers, params=params
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    await self.auth._refresh_token()
                    token = await self.auth.get_valid_token()
                    headers["Authorization"] = f"bearer {token}"
                    response = await client.request(
                        method=method, url=url, headers=headers, params=params
                    )
                    if response.status_code == 200:
                        return response.json()
                logger.error(f"❌ API 오류 [{response.status_code}]: {url}")
                return None
        except Exception as e:
            logger.error(f"❌ 요청 오류: {e}")
            return None

    async def get_print_history(
        self,
        printer_serial: Optional[str] = None,
        status: Optional[PrintStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50
    ) -> List[PrintHistoryItem]:
        """
        프린트 이력 조회 (페이지네이션 순회)

        GET /developer/v1/prints/
        또는
        GET /developer/v1/printers/{serial}/prints/

        Formlabs API는 paginated response를 반환:
        {"results": [...], "next": "https://...?cursor=..."}
        next URL을 순회하여 limit까지 모든 이력을 가져옴
        """
        params = {}

        if status:
            params["status"] = status.value
        if date_from:
            params["date__gt"] = date_from.isoformat()
        if date_to:
            params["date__lt"] = date_to.isoformat()
        # Formlabs API 페이지 크기 (최대값으로 요청하여 왕복 횟수 최소화)
        params["limit"] = min(limit, 100)

        # 특정 프린터 또는 전체
        path = f"/printers/{printer_serial}/prints/" if printer_serial else "/prints/"

        all_raw_items = []
        max_pages = 20  # 안전장치: 최대 20페이지 (2000건)

        # 첫 페이지
        data = await self._request("GET", path, params=params)
        if not data:
            return []

        if isinstance(data, list):
            all_raw_items = data
        else:
            all_raw_items.extend(data.get("results", []))

            # next URL 순회
            next_url = data.get("next")
            page_count = 1
            while next_url and len(all_raw_items) < limit and page_count < max_pages:
                page_count += 1
                next_data = await self._request_full_url("GET", next_url)
                if not next_data:
                    break
                if isinstance(next_data, list):
                    all_raw_items.extend(next_data)
                    break
                else:
                    all_raw_items.extend(next_data.get("results", []))
                    next_url = next_data.get("next")

            if page_count > 1:
                logger.info(f"📄 페이지네이션: {page_count}페이지 순회, 총 {len(all_raw_items)}건")

        # limit 적용
        all_raw_items = all_raw_items[:limit]

        history = []
        for item in all_raw_items:
            try:
                # duration 계산
                started = self._parse_datetime(item.get("print_started_at"))
                finished = self._parse_datetime(item.get("print_finished_at"))
                duration_min = None
                if started and finished:
                    duration_min = int((finished - started).total_seconds() / 60)

                # print_run_success 파싱
                prs = item.get("print_run_success")
                prs_value = prs.get("print_run_success") if isinstance(prs, dict) else None

                # 썸네일
                thumb = item.get("print_thumbnail")
                thumb_url = thumb.get("thumbnail") if isinstance(thumb, dict) else None

                # 파트 목록
                parts = []
                for part in item.get("parts", []):
                    parts.append(PrintHistoryPart(
                        display_name=part.get("display_name", ""),
                        volume_ml=part.get("volume_ml"),
                        stl_path=part.get("name"),
                    ))

                history.append(PrintHistoryItem(
                    guid=item.get("guid", ""),
                    name=item.get("name", ""),
                    printer_serial=item.get("printer", ""),
                    status=item.get("status", PrintStatus.FINISHED),
                    started_at=started,
                    finished_at=finished,
                    duration_minutes=duration_min,
                    layer_count=item.get("layer_count", 0),
                    material_code=item.get("material"),
                    material_name=item.get("material_name"),
                    estimated_ml_used=item.get("volume_ml"),
                    message=item.get("message"),
                    print_run_success=prs_value,
                    thumbnail_url=thumb_url,
                    volume_ml=item.get("volume_ml"),
                    parts=parts,
                ))
            except Exception as e:
                logger.error(f"이력 파싱 오류: {e}")
                continue

        return history
    
    # ===========================================
    # 이벤트 API
    # ===========================================
    
    async def get_events(
        self,
        printer_serial: Optional[str] = None,
        event_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        프린터 이벤트 조회 (완료, 에러 등)
        
        GET /developer/v1/events/
        """
        params = {}
        
        if printer_serial:
            params["printer"] = printer_serial
        if event_type:
            params["type"] = event_type
        if date_from:
            params["date__gt"] = date_from.isoformat()
        if limit:
            params["limit"] = limit
        
        data = await self._request("GET", "/events/", params=params)
        if not data:
            return []
        
        return data if isinstance(data, list) else data.get("results", [])
    
    # ===========================================
    # 유틸리티
    # ===========================================
    
    # 프린트 단계 → 한국어 매핑
    PHASE_LABELS = {
        "PREHEAT": "예열 중",
        "PRECOAT": "초기 코팅",
        "PRINTING": "출력 중",
        "POSTCOAT": "후처리 코팅",
        "PAUSING": "일시정지 중",
        "PAUSED": "일시정지됨",
        "ABORTING": "중단 중",
    }

    def printer_to_summary(self, printer: Printer) -> PrinterSummary:
        """Printer를 대시보드용 PrinterSummary로 변환"""

        # 기본 상태 결정
        status = "IDLE"
        is_online = printer.is_online
        has_error = False
        current_run = None
        print_phase = None
        temperature = None

        if not is_online:
            status = "OFFLINE"
        elif printer.printer_status:
            ps = printer.printer_status

            # 프린터 온도
            temperature = ps.temperature

            current_run = ps.current_print_run

            if current_run and current_run.status:
                run_status = current_run.status
                if run_status == PrintStatus.PRINTING:
                    status = "PRINTING"
                    print_phase = "출력 중"
                elif run_status == PrintStatus.PREHEAT:
                    status = "PREHEAT"
                    print_phase = "예열 중"
                elif run_status == PrintStatus.PRECOAT:
                    status = "PRINTING"  # UI에서는 출력 중으로 표시
                    print_phase = "초기 코팅"
                elif run_status == PrintStatus.POSTCOAT:
                    status = "PRINTING"
                    print_phase = "후처리 코팅"
                elif run_status == PrintStatus.PAUSING:
                    status = "PAUSING"
                    print_phase = "일시정지 중"
                elif run_status == PrintStatus.PAUSED:
                    status = "PAUSED"
                    print_phase = "일시정지됨"
                elif run_status == PrintStatus.ABORTING:
                    status = "ABORTING"
                    print_phase = "중단 중"
                elif run_status == PrintStatus.FINISHED:
                    status = "FINISHED"
                elif run_status == PrintStatus.ERROR:
                    status = "ERROR"
                    has_error = True
                elif run_status == PrintStatus.ABORTED:
                    status = "IDLE"  # 중단 후 대기

        # 레진 정보
        resin_ml = None
        resin_percent = None
        is_resin_low = False
        cartridge_material_code = None
        cartridge_material_name = None
        if printer.cartridge_status:
            resin_ml = printer.cartridge_status.remaining_ml
            resin_percent = printer.cartridge_status.remaining_percent
            is_resin_low = printer.cartridge_status.is_low
            cartridge_material_code = printer.cartridge_status.material_code
            cartridge_material_name = printer.cartridge_status.material_name
            # Formlabs API에서 display_name이 없는 경우 material_code로 매핑
            if not cartridge_material_name and cartridge_material_code:
                cartridge_material_name = MATERIAL_CODE_NAMES.get(
                    cartridge_material_code, cartridge_material_code
                )

        return PrinterSummary(
            serial=printer.serial,
            name=printer.display_name,
            status=status,
            current_job_name=current_run.name if current_run else None,
            progress_percent=current_run.progress_percent if current_run else None,
            remaining_minutes=current_run.estimated_remaining_minutes if current_run else None,
            elapsed_minutes=current_run.elapsed_minutes if current_run else None,
            estimated_total_minutes=(current_run.estimated_duration_ms // 60000) if current_run and current_run.estimated_duration_ms else None,
            current_layer=current_run.currently_printing_layer if current_run else None,
            total_layers=current_run.layer_count if current_run else None,
            print_started_at=current_run.print_started_at if current_run else None,
            print_phase=print_phase,
            temperature=temperature,
            resin_remaining_ml=resin_ml,
            resin_remaining_percent=resin_percent,
            is_resin_low=is_resin_low,
            cartridge_material_code=cartridge_material_code,
            cartridge_material_name=cartridge_material_name,
            machine_type=printer.machine_type,
            firmware_version=printer.firmware_version,
            tank_serial=printer.tank_status.serial if printer.tank_status else None,
            tank_material_code=printer.tank_status.material_code if printer.tank_status else None,
            tank_print_count=printer.tank_status.print_count if printer.tank_status else None,
            is_remote_print_enabled=printer.is_remote_print_enabled,
            group_name=printer.group_name,
            location=printer.location,
            last_print_finished_at=current_run.print_finished_at if current_run and current_run.print_finished_at else None,
            last_print_thumbnail=None,  # 별도 API 호출 필요, 추후 연동
            is_online=is_online,
            is_ready=printer.printer_status.ready_to_print in ("READY", "READY_TO_PRINT_READY") if printer.printer_status else False,
            ready_to_print=printer.printer_status.ready_to_print if printer.printer_status else None,
            build_platform_contents=printer.printer_status.build_platform_contents if printer.printer_status else None,
            has_error=has_error,
            last_update=now_kst()
        )


# 전역 클라이언트 팩토리
async def get_formlabs_client() -> FormlabsAPIClient:
    """FormlabsAPIClient 인스턴스 반환"""
    auth = await get_auth_manager()
    return FormlabsAPIClient(auth)
