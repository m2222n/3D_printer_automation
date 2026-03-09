"""
MQTT 클라이언트
==============
aiomqtt 기반 MQTT 구독 클라이언트
- Mosquitto 브로커 연결
- 토픽 구독 및 메시지 파싱
- camera_manager로 메시지 전달
"""

import json
import logging
import asyncio
from typing import Optional

import aiomqtt

from app.core.config import get_settings
from app.vision.camera_manager import get_camera_manager
from app.vision.schemas import (
    MQTTStatusMessage,
    MQTTHeartbeatMessage,
    MQTTCameraInfoMessage,
)

logger = logging.getLogger(__name__)


class VisionMQTTClient:
    """Vision MQTT 구독 클라이언트"""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._connected = False
        self._reconnect_interval = 5  # 초

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self):
        """MQTT 구독 태스크 시작"""
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info("MQTT 클라이언트 시작")

    async def stop(self):
        """MQTT 구독 태스크 중지"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._connected = False
        logger.info("MQTT 클라이언트 중지")

    async def _subscribe_loop(self):
        """자동 재연결 MQTT 구독 루프"""
        settings = get_settings()
        prefix = settings.MQTT_TOPIC_PREFIX

        subscribe_topics = [
            f"{prefix}/wash/+/status",
            f"{prefix}/wash/+/heartbeat",
            f"{prefix}/cure/+/status",
            f"{prefix}/cure/+/heartbeat",
            f"{prefix}/camera/+/info",
        ]

        while True:
            try:
                async with aiomqtt.Client(
                    hostname=settings.MQTT_BROKER_HOST,
                    port=settings.MQTT_BROKER_PORT,
                ) as client:
                    self._connected = True
                    logger.info(
                        f"MQTT 브로커 연결 성공: {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}"
                    )

                    for topic in subscribe_topics:
                        await client.subscribe(topic)
                        logger.info(f"MQTT 구독: {topic}")

                    async for message in client.messages:
                        try:
                            await self._handle_message(message)
                        except Exception as e:
                            logger.error(f"MQTT 메시지 처리 오류: {e}")

            except aiomqtt.MqttError as e:
                self._connected = False
                logger.warning(
                    f"MQTT 연결 끊김: {e}. {self._reconnect_interval}초 후 재연결..."
                )
                await asyncio.sleep(self._reconnect_interval)

            except asyncio.CancelledError:
                self._connected = False
                break

            except Exception as e:
                self._connected = False
                logger.error(f"MQTT 예기치 않은 오류: {e}. {self._reconnect_interval}초 후 재연결...")
                await asyncio.sleep(self._reconnect_interval)

    async def _handle_message(self, message: aiomqtt.Message):
        """MQTT 메시지 라우팅"""
        topic = str(message.topic)
        try:
            payload = json.loads(message.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"MQTT 메시지 파싱 실패: {topic} - {e}")
            return

        parts = topic.split("/")
        # factory/{device_type}/{device_id}/{message_type}
        # factory/camera/{camera_id}/info
        if len(parts) < 4:
            logger.warning(f"잘못된 토픽 형식: {topic}")
            return

        manager = get_camera_manager()
        message_type = parts[-1]

        if message_type == "status":
            msg = MQTTStatusMessage(**payload)
            await manager.handle_status(msg)

        elif message_type == "heartbeat":
            msg = MQTTHeartbeatMessage(**payload)
            await manager.handle_heartbeat(msg)

        elif message_type == "info":
            msg = MQTTCameraInfoMessage(**payload)
            await manager.handle_camera_info(msg)

        else:
            logger.debug(f"알 수 없는 메시지 타입: {message_type} ({topic})")

    async def publish(self, topic: str, payload: dict, qos: int = 1):
        """MQTT 메시지 발행 (시뮬레이터용)"""
        settings = get_settings()
        try:
            async with aiomqtt.Client(
                hostname=settings.MQTT_BROKER_HOST,
                port=settings.MQTT_BROKER_PORT,
            ) as client:
                await client.publish(
                    topic,
                    json.dumps(payload).encode(),
                    qos=qos,
                )
        except Exception as e:
            logger.error(f"MQTT 발행 실패: {topic} - {e}")
            raise


# 싱글톤
_mqtt_client: Optional[VisionMQTTClient] = None


def get_mqtt_client() -> VisionMQTTClient:
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = VisionMQTTClient()
    return _mqtt_client
