"""
MQTT 시뮬레이터
==============
카메라 없이 전체 파이프라인을 테스트하기 위한 가짜 MQTT 메시지 발행
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta

from app.core.config import get_settings
from app.vision.mqtt_client import get_mqtt_client

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 카메라 -> 장비 매핑
CAMERA_MAP = {
    "wash_1": {"device_type": "wash", "device_id": 1},
    "wash_2": {"device_type": "wash", "device_id": 2},
    "cure_1": {"device_type": "cure", "device_id": 1},
    "cure_2": {"device_type": "cure", "device_id": 2},
}

# 시나리오 정의
SCENARIOS = {
    "full_cycle": [
        # 세척 시작 -> 완료 -> 경화 시작 -> 완료
        ("wash_1", "wash_running"),
        ("wash_1", "wash_complete"),
        ("cure_1", "cure_running"),
        ("cure_1", "cure_complete"),
    ],
    "all_wash": [
        ("wash_1", "wash_running"),
        ("wash_2", "wash_running"),
        ("wash_1", "wash_complete"),
        ("wash_2", "wash_complete"),
    ],
    "all_cure": [
        ("cure_1", "cure_running"),
        ("cure_2", "cure_running"),
        ("cure_1", "cure_complete"),
        ("cure_2", "cure_complete"),
    ],
    "error_recovery": [
        ("wash_1", "wash_running"),
        ("wash_1", "error"),
        ("wash_1", "wash_running"),
        ("wash_1", "wash_complete"),
    ],
}


async def publish_simulated_status(camera_id: str, status: str, confidence: float = 0.95):
    """단건 시뮬레이션 상태 발행"""
    settings = get_settings()
    mqtt = get_mqtt_client()

    if camera_id not in CAMERA_MAP:
        raise ValueError(f"알 수 없는 카메라: {camera_id}")

    info = CAMERA_MAP[camera_id]
    now = datetime.now(KST)

    topic = f"{settings.MQTT_TOPIC_PREFIX}/{info['device_type']}/{info['device_id']}/status"
    payload = {
        "camera_id": camera_id,
        "device_type": info["device_type"],
        "device_id": info["device_id"],
        "status": status,
        "confidence": confidence,
        "timestamp": now.isoformat(),
        "consecutive_count": 5,
        "fps": 15.0,
        "mem_free": 50000,
    }

    await mqtt.publish(topic, payload, qos=1)
    logger.info(f"[시뮬레이터] {camera_id} -> {status} (confidence: {confidence})")


async def publish_simulated_heartbeat(camera_id: str):
    """시뮬레이션 하트비트 발행"""
    settings = get_settings()
    mqtt = get_mqtt_client()

    if camera_id not in CAMERA_MAP:
        return

    info = CAMERA_MAP[camera_id]
    now = datetime.now(KST)

    topic = f"{settings.MQTT_TOPIC_PREFIX}/{info['device_type']}/{info['device_id']}/heartbeat"
    payload = {
        "camera_id": camera_id,
        "uptime_s": 3600,
        "mem_free": 50000,
        "temperature_c": 42.0,
        "wifi_rssi": -55,
        "timestamp": now.isoformat(),
    }

    await mqtt.publish(topic, payload, qos=0)


async def run_scenario(scenario_name: str, interval_seconds: int = 10):
    """시나리오 실행 (백그라운드 태스크)"""
    if scenario_name not in SCENARIOS:
        logger.error(f"알 수 없는 시나리오: {scenario_name}")
        return

    steps = SCENARIOS[scenario_name]
    logger.info(f"[시뮬레이터] 시나리오 '{scenario_name}' 시작 ({len(steps)}단계, {interval_seconds}초 간격)")

    for i, (camera_id, status) in enumerate(steps):
        try:
            await publish_simulated_status(camera_id, status)
            if i < len(steps) - 1:
                await asyncio.sleep(interval_seconds)
        except Exception as e:
            logger.error(f"[시뮬레이터] 시나리오 단계 {i+1} 실패: {e}")
            break

    logger.info(f"[시뮬레이터] 시나리오 '{scenario_name}' 완료")
