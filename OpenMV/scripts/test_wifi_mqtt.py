# OpenMV AE3 - WiFi + MQTT 단계별 연결 테스트
# =============================================
# OpenMV IDE에서 실행: 단계별로 WiFi → MQTT 연결 테스트
# 각 단계 성공/실패를 시리얼 터미널에 출력

import time
import json
import gc

# ===========================================
# 설정 (사무실 환경에 맞게 수정)
# ===========================================
WIFI_SSID = "OrinuAI_5GHz"
WIFI_PASSWORD = "OrinuAI2026!"
WIFI_TIMEOUT_MS = 15000

# MQTT 브로커 주소 (아래 중 하나가 작동할 것)
# 같은 네트워크면 내부 IP, 아니면 외부 IP
MQTT_BROKER_INTERNAL = "192.168.100.29"  # 서버 내부 IP
MQTT_BROKER_EXTERNAL = "106.244.6.242"   # 서버 외부 IP
MQTT_PORT = 1883

# 카메라 식별
CAMERA_ID = "wash_1"
DEVICE_TYPE = "wash"
DEVICE_ID = 1

print("=" * 50)
print("OpenMV AE3 WiFi + MQTT 연결 테스트")
print("=" * 50)
print()

# ===========================================
# Step 1: WiFi 연결
# ===========================================
print("[Step 1] WiFi 연결 시도...")
print(f"  SSID: {WIFI_SSID}")

import network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
time.sleep_ms(500)

# 이미 연결된 경우 해제
if wlan.isconnected():
    print("  기존 연결 해제 중...")
    wlan.disconnect()
    time.sleep(1)

# WiFi 스캔
print("  WiFi 스캔 중...")
try:
    networks = wlan.scan()
    found = False
    for net in networks:
        ssid = net[0].decode("utf-8") if isinstance(net[0], bytes) else str(net[0])
        rssi = net[3] if len(net) > 3 else "?"
        if ssid == WIFI_SSID:
            print(f"  ✓ 대상 네트워크 발견: {ssid} (RSSI: {rssi})")
            found = True
        # 상위 5개 네트워크 표시
    if not found:
        print(f"  ✗ '{WIFI_SSID}' 네트워크를 찾을 수 없습니다!")
        print("  발견된 네트워크:")
        for net in networks[:5]:
            ssid = net[0].decode("utf-8") if isinstance(net[0], bytes) else str(net[0])
            print(f"    - {ssid}")
except Exception as e:
    print(f"  WiFi 스캔 오류: {e}")

# WiFi 연결
print(f"  연결 중... (타임아웃: {WIFI_TIMEOUT_MS}ms)")
try:
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
            print("  ✗ WiFi 연결 타임아웃!")
            raise Exception("WiFi timeout")
        time.sleep_ms(500)
        print("  ...", end="")

    ip = wlan.ifconfig()[0]
    print()
    print(f"  ✓ WiFi 연결 성공!")
    print(f"  IP 주소: {ip}")
    print(f"  서브넷: {wlan.ifconfig()[1]}")
    print(f"  게이트웨이: {wlan.ifconfig()[2]}")
    print(f"  DNS: {wlan.ifconfig()[3]}")

    # RSSI 확인
    try:
        rssi = wlan.status("rssi")
        print(f"  신호 강도: {rssi} dBm")
    except:
        pass

except Exception as e:
    print(f"  ✗ WiFi 연결 실패: {e}")
    print("  나머지 테스트를 건너뜁니다.")
    raise SystemExit

print()
gc.collect()

# ===========================================
# Step 2: MQTT 브로커 연결 테스트
# ===========================================
print("[Step 2] MQTT 브로커 연결 테스트...")

from umqtt.robust import MQTTClient

mqtt_connected = False
broker_ip = None

# 내부 IP 먼저 시도
for label, host in [("내부 IP", MQTT_BROKER_INTERNAL), ("외부 IP", MQTT_BROKER_EXTERNAL)]:
    print(f"  {label} 시도: {host}:{MQTT_PORT}")
    try:
        client = MQTTClient(
            client_id=CAMERA_ID + "_test",
            server=host,
            port=MQTT_PORT,
            keepalive=30,
        )
        client.connect()
        print(f"  ✓ MQTT 연결 성공! ({label}: {host})")
        mqtt_connected = True
        broker_ip = host
        break
    except Exception as e:
        print(f"  ✗ 실패: {e}")
        try:
            client.disconnect()
        except:
            pass

if not mqtt_connected:
    print("  ✗ 모든 브로커 주소 연결 실패!")
    print("  → 서버에서 1883 포트 개방 필요")
    raise SystemExit

print()
gc.collect()

# ===========================================
# Step 3: MQTT 메시지 발행 테스트
# ===========================================
print("[Step 3] MQTT 메시지 발행 테스트...")

# 3-1. 카메라 정보 발행
topic_info = "factory/camera/{}/info".format(CAMERA_ID)
info_payload = {
    "camera_id": CAMERA_ID,
    "firmware_version": "4.8.1",
    "model_name": "test_mode",
    "model_classes": ["wash_idle", "wash_running", "wash_complete"],
    "ip_address": wlan.ifconfig()[0],
}
try:
    client.publish(topic_info, json.dumps(info_payload), qos=1)
    print(f"  ✓ 카메라 정보 발행: {topic_info}")
except Exception as e:
    print(f"  ✗ 정보 발행 실패: {e}")

time.sleep(1)

# 3-2. 상태 메시지 발행
topic_status = "factory/{}/{}/status".format(DEVICE_TYPE, DEVICE_ID)
status_payload = {
    "camera_id": CAMERA_ID,
    "device_type": DEVICE_TYPE,
    "device_id": DEVICE_ID,
    "status": "wash_idle",
    "confidence": 0.95,
    "timestamp": str(time.time()),
    "consecutive_count": 5,
    "fps": 15.0,
    "mem_free": gc.mem_free(),
}
try:
    client.publish(topic_status, json.dumps(status_payload), qos=1)
    print(f"  ✓ 상태 메시지 발행: {topic_status}")
except Exception as e:
    print(f"  ✗ 상태 발행 실패: {e}")

time.sleep(1)

# 3-3. 하트비트 발행
topic_hb = "factory/{}/{}/heartbeat".format(DEVICE_TYPE, DEVICE_ID)
hb_payload = {
    "camera_id": CAMERA_ID,
    "uptime_s": 0,
    "mem_free": gc.mem_free(),
    "temperature_c": 0,
    "wifi_rssi": wlan.status("rssi") if wlan.isconnected() else -100,
    "timestamp": str(time.time()),
}
try:
    client.publish(topic_hb, json.dumps(hb_payload), qos=1)
    print(f"  ✓ 하트비트 발행: {topic_hb}")
except Exception as e:
    print(f"  ✗ 하트비트 발행 실패: {e}")

print()

# ===========================================
# Step 4: 연결 정리 + 결과 요약
# ===========================================
try:
    client.disconnect()
except:
    pass

print("=" * 50)
print("테스트 결과 요약")
print("=" * 50)
print(f"  WiFi:  ✓ 연결됨 ({WIFI_SSID}, IP: {wlan.ifconfig()[0]})")
print(f"  MQTT:  ✓ 연결됨 ({broker_ip}:{MQTT_PORT})")
print(f"  발행:  카메라 정보 + 상태 + 하트비트 3건")
print()
print("→ 서버 로그에서 메시지 수신 확인하세요:")
print(f"  docker logs formlabs-mosquitto --tail 20")
print()
print("→ config.py에 설정할 값:")
print(f'  WIFI_SSID = "{WIFI_SSID}"')
print(f'  WIFI_PASSWORD = "{WIFI_PASSWORD}"')
print(f'  MQTT_BROKER = "{broker_ip}"')
print()
print("테스트 완료!")
