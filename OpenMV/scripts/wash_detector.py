# OpenMV AE3 - 세척기(Form Wash) 완료 감지 스크립트
# ================================================
# 샘플 기반: Python Scripts/yolov8.py, blazeface_face_detector.py
#
# 구조: CSI 초기화 -> 모델 로드 -> 메인 루프 (추론 -> Debounce -> MQTT)
# 상태: wash_idle, wash_running, wash_complete, error

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

# TFLite Classification 모델 로드 (yolov8 샘플 패턴)
# Edge Impulse에서 학습 후 배포된 모델
# 아직 모델이 없으므로 placeholder
MODEL_PATH = "/rom/wash_classifier.tflite"
MODEL_LABELS = ["wash_idle", "wash_running", "wash_complete"]

try:
    model = ml.Model(MODEL_PATH)
    print("[wash] Model loaded:", MODEL_PATH)
except Exception as e:
    print("[wash] Model not found, running in test mode:", e)
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
            print("[wash] MQTT connected to", MQTT_BROKER)
            return True
        except Exception as e:
            print("[wash] MQTT connect failed (attempt {}): {}".format(attempt + 1, e))
            time.sleep(2)
    return False

def publish_json(topic, data, qos=0):
    """JSON 메시지 MQTT 발행"""
    try:
        payload = json.dumps(data)
        mqtt.publish(topic, payload, qos=qos)
    except Exception as e:
        print("[wash] MQTT publish failed:", e)

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
    print("[wash] Camera info sent")

def send_heartbeat(uptime_s):
    """하트비트 발행"""
    import network
    wlan = network.WLAN(network.STA_IF)

    hb = {
        "camera_id": CAMERA_ID,
        "uptime_s": uptime_s,
        "mem_free": gc.mem_free(),
        "temperature_c": 0,  # AE3 온도 센서 API 확인 필요
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
    print("[wash] Status change:", status, "confidence:", confidence)

def classify_frame(img):
    """이미지에서 Classification 추론
    Returns: (label, confidence) or (None, 0)
    """
    if model is None:
        return None, 0.0

    # Classification 추론 (yolov8 샘플의 model.predict 패턴)
    try:
        results = model.predict([img])
        # Edge Impulse Classification: results[0] = [(label_index, score), ...]
        if results and len(results) > 0:
            # 가장 높은 confidence 찾기
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
        print("[wash] Inference error:", e)

    return None, 0.0

# ===========================================
# 2. MQTT 연결 + 카메라 정보 전송
# ===========================================

if not connect_mqtt():
    print("[wash] MQTT connection failed, resetting...")
    machine.reset()

send_camera_info()

# ===========================================
# 3. 메인 루프
# ===========================================

current_status = "wash_idle"
consecutive_label = None
consecutive_count = 0

clock = time.clock()
boot_time = time.ticks_ms()
last_heartbeat = time.ticks_ms()

print("[wash] Starting main loop...")

while True:
    try:
        clock.tick()
        wdt.feed()  # Watchdog 리셋

        # 이미지 캡처 (blazeface 샘플 패턴)
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

            # 연속 N프레임 동일 결과 -> 상태 전환
            if consecutive_count >= DEBOUNCE_COUNT and label != current_status:
                current_status = label
                send_status(current_status, confidence, consecutive_count, clock.fps())
                consecutive_count = 0  # 전송 후 리셋
        else:
            # confidence 미달 시 카운터 리셋
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
        print("[wash] Error in main loop:", e)
        # 에러 상태 전송 시도
        try:
            send_status("error", 0.0, 0, 0.0)
        except:
            pass
        time.sleep(1)
        # 심각한 에러 시 리셋
        machine.reset()

# 정리
mqtt.disconnect()
print("[wash] Stopped")
