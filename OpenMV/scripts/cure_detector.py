# OpenMV AE3 - 경화기(Form Cure) 완료 감지 스크립트
# ================================================
# 샘플 기반: Python Scripts/yolov8.py, blazeface_face_detector.py
#
# 구조: CSI 초기화 -> 모델 로드 -> 메인 루프 (추론 -> Debounce -> MQTT)
# 상태: cure_idle, cure_running, cure_complete, error
#
# wash_detector.py와 동일 구조, 모델/라벨만 다름

import time
import gc
import json
import machine

# CSI 카메라 (AE3 v4.8.1+, sensor는 deprecated)
import csi
# AI 추론
import ml
# MQTT 통신
from umqtt.robust import MQTTClient

from config import (
    CAMERA_ID, DEVICE_TYPE, DEVICE_ID,
    MQTT_BROKER, MQTT_PORT, MQTT_KEEPALIVE,
    TOPIC_STATUS, TOPIC_HEARTBEAT, TOPIC_INFO,
    CONFIDENCE_THRESHOLD, DEBOUNCE_COUNT,
    HEARTBEAT_INTERVAL_S, WATCHDOG_TIMEOUT_MS,
    FRAME_WIDTH, FRAME_HEIGHT,
)

# ===========================================
# 1. 초기화
# ===========================================

# Watchdog Timer (10초 내 무응답 시 자동 리셋)
wdt = machine.WDT(timeout=WATCHDOG_TIMEOUT_MS)

# CSI 카메라 초기화 (blazeface 샘플 패턴)
csi0 = csi.CSI()
csi0.reset()
csi0.pixformat(csi.RGB565)
csi0.framesize(csi.VGA)
csi0.window((FRAME_WIDTH, FRAME_HEIGHT))

# TFLite Classification 모델 로드
# Edge Impulse에서 학습 후 배포된 모델
MODEL_PATH = "/rom/cure_classifier.tflite"
MODEL_LABELS = ["cure_idle", "cure_running", "cure_complete"]

try:
    model = ml.Model(MODEL_PATH)
    print("[cure] Model loaded:", MODEL_PATH)
except Exception as e:
    print("[cure] Model not found, running in test mode:", e)
    model = None

# MQTT 클라이언트
mqtt = MQTTClient(
    client_id=CAMERA_ID,
    server=MQTT_BROKER,
    port=MQTT_PORT,
    keepalive=MQTT_KEEPALIVE,
)

def connect_mqtt():
    """MQTT 브로커 연결 (재시도 포함)"""
    for attempt in range(5):
        try:
            mqtt.connect()
            print("[cure] MQTT connected to", MQTT_BROKER)
            return True
        except Exception as e:
            print("[cure] MQTT connect failed (attempt {}): {}".format(attempt + 1, e))
            time.sleep(2)
    return False

def publish_json(topic, data, qos=0):
    """JSON 메시지 MQTT 발행"""
    try:
        payload = json.dumps(data)
        mqtt.publish(topic, payload, qos=qos)
    except Exception as e:
        print("[cure] MQTT publish failed:", e)

def send_camera_info():
    """카메라 정보 발행 (부팅 시 1회)"""
    import network
    wlan = network.WLAN(network.STA_IF)
    ip = wlan.ifconfig()[0] if wlan.isconnected() else "unknown"

    info = {
        "camera_id": CAMERA_ID,
        "firmware_version": "4.8.1",
        "model_name": MODEL_PATH.split("/")[-1] if model else "none",
        "model_classes": MODEL_LABELS,
        "ip_address": ip,
    }
    publish_json(TOPIC_INFO, info, qos=1)
    print("[cure] Camera info sent")

def send_heartbeat(uptime_s):
    """하트비트 발행"""
    import network
    wlan = network.WLAN(network.STA_IF)

    hb = {
        "camera_id": CAMERA_ID,
        "uptime_s": uptime_s,
        "mem_free": gc.mem_free(),
        "temperature_c": 0,
        "wifi_rssi": wlan.status("rssi") if wlan.isconnected() else -100,
        "timestamp": time.time(),
    }
    publish_json(TOPIC_HEARTBEAT, hb, qos=0)

def send_status(status, confidence, consecutive_count, fps):
    """상태 변경 MQTT 발행 (Debounce 통과 시에만 호출)"""
    msg = {
        "camera_id": CAMERA_ID,
        "device_type": DEVICE_TYPE,
        "device_id": DEVICE_ID,
        "status": status,
        "confidence": round(confidence, 3),
        "timestamp": time.time(),
        "consecutive_count": consecutive_count,
        "fps": round(fps, 1),
        "mem_free": gc.mem_free(),
    }
    publish_json(TOPIC_STATUS, msg, qos=1)
    print("[cure] Status change:", status, "confidence:", confidence)

def classify_frame(img):
    """이미지에서 Classification 추론
    Returns: (label, confidence) or (None, 0)
    """
    if model is None:
        return None, 0.0

    try:
        results = model.predict([img])
        if results and len(results) > 0:
            best_idx = 0
            best_score = 0.0
            for i, score in enumerate(results[0]):
                if isinstance(score, (list, tuple)):
                    s = score[1] if len(score) > 1 else score[0]
                else:
                    s = float(score)
                if s > best_score:
                    best_score = s
                    best_idx = i
            if best_idx < len(MODEL_LABELS):
                return MODEL_LABELS[best_idx], best_score
    except Exception as e:
        print("[cure] Inference error:", e)

    return None, 0.0

# ===========================================
# 2. MQTT 연결 + 카메라 정보 전송
# ===========================================

if not connect_mqtt():
    print("[cure] MQTT connection failed, resetting...")
    machine.reset()

send_camera_info()

# ===========================================
# 3. 메인 루프
# ===========================================

current_status = "cure_idle"
consecutive_label = None
consecutive_count = 0

clock = time.clock()
boot_time = time.ticks_ms()
last_heartbeat = time.ticks_ms()

print("[cure] Starting main loop...")

while True:
    try:
        clock.tick()
        wdt.feed()

        # 이미지 캡처
        img = csi0.snapshot()

        # AI 추론
        label, confidence = classify_frame(img)

        # -- Debounce 처리 --
        if label is not None and confidence >= CONFIDENCE_THRESHOLD:
            if label == consecutive_label:
                consecutive_count += 1
            else:
                consecutive_label = label
                consecutive_count = 1

            if consecutive_count >= DEBOUNCE_COUNT and label != current_status:
                current_status = label
                send_status(current_status, confidence, consecutive_count, clock.fps())
                consecutive_count = 0
        else:
            consecutive_count = 0
            consecutive_label = None

        # -- 하트비트 전송 (30초 주기) --
        now = time.ticks_ms()
        if time.ticks_diff(now, last_heartbeat) >= HEARTBEAT_INTERVAL_S * 1000:
            uptime_s = time.ticks_diff(now, boot_time) // 1000
            send_heartbeat(uptime_s)
            last_heartbeat = now

        # MQTT keepalive 유지
        mqtt.check_msg()

        # 메모리 관리
        gc.collect()

    except KeyboardInterrupt:
        break
    except Exception as e:
        print("[cure] Error in main loop:", e)
        try:
            send_status("error", 0.0, 0, 0.0)
        except:
            pass
        time.sleep(1)
        machine.reset()

mqtt.disconnect()
print("[cure] Stopped")
