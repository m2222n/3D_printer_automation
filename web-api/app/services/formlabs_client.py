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
    PrintStatus, PrintHistoryItem
)

logger = logging.getLogger(__name__)


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
        설정된 4대 프린터만 조회
        """
        all_printers = await self.get_all_printers()
        
        # 설정된 시리얼만 필터링
        target_serials = set(self.settings.PRINTER_SERIALS)
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
            
            printer_status = PrinterStatus(
                status=ps.get("status"),
                last_pinged_at=self._parse_datetime(ps.get("last_pinged_at")),
                current_print_run=current_run,
                ready_to_print=ps.get("ready_to_print"),
                build_platform_contents=ps.get("build_platform_contents"),
            )
        
        # cartridge_status 파싱
        cartridge_status = None
        if "cartridge_status" in data and data["cartridge_status"]:
            cs = data["cartridge_status"]
            cartridge_status = CartridgeStatus(
                serial=cs.get("serial"),
                material_code=cs.get("material_code"),
                material_name=cs.get("material_name"),
                initial_ml=cs.get("initial_ml", 0),
                remaining_ml=cs.get("remaining_ml", 0),
            )
        
        # tank_status 파싱
        tank_status = None
        if "tank_status" in data and data["tank_status"]:
            ts = data["tank_status"]
            tank_status = TankStatus(
                serial=ts.get("serial"),
                material_code=ts.get("material_code"),
                print_count=ts.get("print_count", 0),
                days_since_first_print=ts.get("days_since_first_print", 0),
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
    
    async def get_print_history(
        self,
        printer_serial: Optional[str] = None,
        status: Optional[PrintStatus] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50
    ) -> List[PrintHistoryItem]:
        """
        프린트 이력 조회
        
        GET /developer/v1/prints/
        또는
        GET /developer/v1/printers/{serial}/prints/
        """
        params = {}
        
        if status:
            params["status"] = status.value
        if date_from:
            params["date__gt"] = date_from.isoformat()
        if date_to:
            params["date__lt"] = date_to.isoformat()
        if limit:
            params["limit"] = limit
        
        # 특정 프린터 또는 전체
        path = f"/printers/{printer_serial}/prints/" if printer_serial else "/prints/"
        
        data = await self._request("GET", path, params=params)
        if not data:
            return []
        
        items = data if isinstance(data, list) else data.get("results", [])
        
        history = []
        for item in items:
            try:
                history.append(PrintHistoryItem(
                    guid=item.get("guid", ""),
                    name=item.get("name", ""),
                    printer_serial=item.get("printer", ""),
                    status=item.get("status", PrintStatus.FINISHED),
                    started_at=self._parse_datetime(item.get("print_started_at")),
                    finished_at=self._parse_datetime(item.get("print_finished_at")),
                    layer_count=item.get("layer_count", 0),
                    material_code=item.get("material_code"),
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
    
    def printer_to_summary(self, printer: Printer) -> PrinterSummary:
        """Printer를 대시보드용 PrinterSummary로 변환"""
        
        # 기본 상태 결정
        status = "IDLE"
        is_online = printer.is_online
        has_error = False
        current_run = None
        
        if not is_online:
            status = "OFFLINE"
        elif printer.printer_status:
            ps = printer.printer_status
            current_run = ps.current_print_run
            
            if current_run:
                if current_run.status == PrintStatus.PRINTING:
                    status = "PRINTING"
                elif current_run.status == PrintStatus.FINISHED:
                    status = "FINISHED"
                elif current_run.status == PrintStatus.ERROR:
                    status = "ERROR"
                    has_error = True
                elif current_run.status == PrintStatus.PAUSED:
                    status = "PAUSED"
        
        # 레진 정보
        resin_ml = None
        resin_percent = None
        is_resin_low = False
        if printer.cartridge_status:
            resin_ml = printer.cartridge_status.remaining_ml
            resin_percent = printer.cartridge_status.remaining_percent
            is_resin_low = printer.cartridge_status.is_low
        
        return PrinterSummary(
            serial=printer.serial,
            name=printer.display_name,
            status=status,
            current_job_name=current_run.name if current_run else None,
            progress_percent=current_run.progress_percent if current_run else None,
            remaining_minutes=current_run.estimated_remaining_minutes if current_run else None,
            current_layer=current_run.currently_printing_layer if current_run else None,
            total_layers=current_run.layer_count if current_run else None,
            resin_remaining_ml=resin_ml,
            resin_remaining_percent=resin_percent,
            is_resin_low=is_resin_low,
            is_online=is_online,
            is_ready=printer.printer_status.ready_to_print == "READY" if printer.printer_status else False,
            has_error=has_error,
            last_update=datetime.now()
        )


# 전역 클라이언트 팩토리
async def get_formlabs_client() -> FormlabsAPIClient:
    """FormlabsAPIClient 인스턴스 반환"""
    auth = await get_auth_manager()
    return FormlabsAPIClient(auth)
