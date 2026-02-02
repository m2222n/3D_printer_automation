"""
PreFormServer 클라이언트
========================
Local API를 통한 프린터 제어
"""

import httpx
import logging
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.core.config import get_settings
from app.local.schemas import (
    DiscoveredPrinter, SceneInfo, PrintSettings,
    MaterialCode, SupportDensity
)

logger = logging.getLogger(__name__)


class PreFormServerClient:
    """
    PreFormServer API 클라이언트

    사용법:
        client = PreFormServerClient()
        if await client.health_check():
            printers = await client.discover_printers()
    """

    def __init__(self):
        self.settings = get_settings()
        self.base_url = f"http://{self.settings.PREFORM_SERVER_HOST}:{self.settings.PREFORM_SERVER_PORT}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 반환 (재사용)"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.settings.PREFORM_SERVER_TIMEOUT)
            )
        return self._client

    async def close(self):
        """클라이언트 종료"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ===========================================
    # 헬스 체크
    # ===========================================

    async def health_check(self) -> bool:
        """
        PreFormServer 연결 상태 확인

        Returns:
            bool: 연결 성공 여부
        """
        try:
            client = await self._get_client()
            response = await client.get("/")
            return response.status_code == 200
        except httpx.ConnectError:
            logger.warning(f"PreFormServer 연결 실패: {self.base_url}")
            return False
        except Exception as e:
            logger.error(f"PreFormServer 헬스체크 오류: {e}")
            return False

    # ===========================================
    # 프린터 검색
    # ===========================================

    async def discover_printers(self, timeout_seconds: int = 10) -> List[DiscoveredPrinter]:
        """
        네트워크에서 프린터 검색

        Args:
            timeout_seconds: 검색 타임아웃 (초)

        Returns:
            List[DiscoveredPrinter]: 검색된 프린터 목록
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/discover-devices/",
                json={"timeout": timeout_seconds}
            )

            if response.status_code != 200:
                logger.error(f"프린터 검색 실패: {response.status_code} - {response.text}")
                return []

            data = response.json()
            printers = []

            for device in data.get("devices", []):
                printers.append(DiscoveredPrinter(
                    serial=device.get("serial", ""),
                    name=device.get("name", ""),
                    ip_address=device.get("ip_address", ""),
                    machine_type=device.get("machine_type", ""),
                    is_online=device.get("is_online", False)
                ))

            logger.info(f"🔍 {len(printers)}대 프린터 검색됨")
            return printers

        except Exception as e:
            logger.error(f"프린터 검색 오류: {e}")
            return []

    # ===========================================
    # Scene 관리
    # ===========================================

    async def create_scene(
        self,
        machine_type: str = "FORM-4-0",
        material_code: str = "FLGPGR05"
    ) -> Optional[str]:
        """
        새 Scene 생성

        Args:
            machine_type: 프린터 타입
            material_code: 레진 코드

        Returns:
            Optional[str]: Scene ID (실패 시 None)
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/scene/",
                json={
                    "machine_type": machine_type,
                    "material_code": material_code
                }
            )

            if response.status_code == 200:
                data = response.json()
                scene_id = data.get("id")
                logger.info(f"✅ Scene 생성: {scene_id}")
                return scene_id
            else:
                logger.error(f"Scene 생성 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Scene 생성 오류: {e}")
            return None

    async def delete_scene(self, scene_id: str) -> bool:
        """Scene 삭제"""
        try:
            client = await self._get_client()
            response = await client.delete(f"/scene/{scene_id}/")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Scene 삭제 오류: {e}")
            return False

    # ===========================================
    # 모델 작업
    # ===========================================

    async def import_model(self, scene_id: str, file_path: str) -> bool:
        """
        STL 파일을 Scene에 추가

        Args:
            scene_id: Scene ID
            file_path: STL 파일 경로

        Returns:
            bool: 성공 여부
        """
        if not os.path.exists(file_path):
            logger.error(f"파일 없음: {file_path}")
            return False

        try:
            client = await self._get_client()

            # 파일 업로드
            with open(file_path, "rb") as f:
                response = await client.post(
                    f"/scene/{scene_id}/import-model/",
                    files={"file": (Path(file_path).name, f, "application/octet-stream")}
                )

            if response.status_code == 200:
                logger.info(f"✅ 모델 임포트 성공: {file_path}")
                return True
            else:
                logger.error(f"모델 임포트 실패: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"모델 임포트 오류: {e}")
            return False

    async def auto_orient(self, scene_id: str) -> bool:
        """자동 방향 설정"""
        try:
            client = await self._get_client()
            response = await client.post(f"/scene/{scene_id}/auto-orient/")

            if response.status_code == 200:
                logger.info("✅ 자동 방향 설정 완료")
                return True
            else:
                logger.error(f"자동 방향 설정 실패: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"자동 방향 설정 오류: {e}")
            return False

    async def auto_support(
        self,
        scene_id: str,
        density: str = "normal",
        touchpoint_size: float = 0.5
    ) -> bool:
        """
        자동 서포트 생성

        Args:
            scene_id: Scene ID
            density: 밀도 (light, normal, heavy)
            touchpoint_size: 터치포인트 크기 (mm)

        Returns:
            bool: 성공 여부
        """
        try:
            client = await self._get_client()
            response = await client.post(
                f"/scene/{scene_id}/auto-support/",
                json={
                    "density": density,
                    "touchpoint_size": touchpoint_size
                }
            )

            if response.status_code == 200:
                logger.info("✅ 자동 서포트 생성 완료")
                return True
            else:
                logger.error(f"자동 서포트 생성 실패: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"자동 서포트 생성 오류: {e}")
            return False

    async def auto_layout(self, scene_id: str) -> bool:
        """자동 배치"""
        try:
            client = await self._get_client()
            response = await client.post(f"/scene/{scene_id}/auto-layout/")

            if response.status_code == 200:
                logger.info("✅ 자동 배치 완료")
                return True
            else:
                logger.error(f"자동 배치 실패: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"자동 배치 오류: {e}")
            return False

    # ===========================================
    # 프린트 작업
    # ===========================================

    async def get_scene_info(self, scene_id: str) -> Optional[SceneInfo]:
        """Scene 정보 조회"""
        try:
            client = await self._get_client()
            response = await client.get(f"/scene/{scene_id}/")

            if response.status_code == 200:
                data = response.json()
                return SceneInfo(
                    scene_id=scene_id,
                    machine_type=data.get("machine_type", ""),
                    material_code=data.get("material_code", ""),
                    model_count=len(data.get("models", [])),
                    estimated_print_time_ms=data.get("estimated_print_time_ms"),
                    estimated_material_ml=data.get("estimated_material_ml")
                )
            return None

        except Exception as e:
            logger.error(f"Scene 정보 조회 오류: {e}")
            return None

    async def send_to_printer(self, scene_id: str, printer_serial: str) -> bool:
        """
        프린터로 작업 전송

        Args:
            scene_id: Scene ID
            printer_serial: 프린터 시리얼 번호

        Returns:
            bool: 성공 여부
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/print/",
                json={
                    "scene_id": scene_id,
                    "printer": printer_serial
                }
            )

            if response.status_code == 200:
                logger.info(f"✅ 프린터 전송 완료: {printer_serial}")
                return True
            else:
                logger.error(f"프린터 전송 실패: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"프린터 전송 오류: {e}")
            return False

    # ===========================================
    # 통합 워크플로우
    # ===========================================

    async def prepare_and_print(
        self,
        stl_path: str,
        printer_serial: str,
        settings: PrintSettings,
        auto_prepare: bool = True
    ) -> Dict[str, Any]:
        """
        STL 파일을 준비하고 프린터로 전송

        Args:
            stl_path: STL 파일 경로
            printer_serial: 프린터 시리얼 번호
            settings: 프린트 설정
            auto_prepare: 자동 방향/서포트/배치 적용 여부

        Returns:
            Dict: 결과 정보 (success, scene_id, error 등)
        """
        result = {
            "success": False,
            "scene_id": None,
            "error": None,
            "estimated_print_time_ms": None,
            "estimated_material_ml": None
        }

        # 1. Scene 생성
        scene_id = await self.create_scene(
            machine_type=settings.machine_type,
            material_code=settings.material_code.value if isinstance(settings.material_code, MaterialCode) else settings.material_code
        )
        if not scene_id:
            result["error"] = "Scene 생성 실패"
            return result
        result["scene_id"] = scene_id

        try:
            # 2. 모델 임포트
            if not await self.import_model(scene_id, stl_path):
                result["error"] = "모델 임포트 실패"
                return result

            # 3. 자동 준비 (옵션)
            if auto_prepare:
                if not await self.auto_orient(scene_id):
                    logger.warning("자동 방향 설정 실패, 계속 진행")

                if not await self.auto_support(
                    scene_id,
                    density=settings.support.density.value if isinstance(settings.support.density, SupportDensity) else settings.support.density,
                    touchpoint_size=settings.support.touchpoint_size
                ):
                    logger.warning("자동 서포트 생성 실패, 계속 진행")

                if not await self.auto_layout(scene_id):
                    logger.warning("자동 배치 실패, 계속 진행")

            # 4. Scene 정보 조회
            scene_info = await self.get_scene_info(scene_id)
            if scene_info:
                result["estimated_print_time_ms"] = scene_info.estimated_print_time_ms
                result["estimated_material_ml"] = scene_info.estimated_material_ml

            # 5. 프린터로 전송
            if not await self.send_to_printer(scene_id, printer_serial):
                result["error"] = "프린터 전송 실패"
                return result

            result["success"] = True
            logger.info(f"🎉 프린트 작업 전송 완료: {printer_serial}")
            return result

        except Exception as e:
            result["error"] = str(e)
            # 실패 시 Scene 정리
            await self.delete_scene(scene_id)
            return result


# 전역 클라이언트 인스턴스
_preform_client: Optional[PreFormServerClient] = None


async def get_preform_client() -> PreFormServerClient:
    """PreFormServer 클라이언트 싱글톤 반환"""
    global _preform_client
    if _preform_client is None:
        _preform_client = PreFormServerClient()
    return _preform_client
