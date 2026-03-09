# boot.py -- OpenMV AE3 부팅 시 자동 실행
# ============================================
# WiFi 연결 후 메인 스크립트(main.py)가 실행됨
#
# 이 파일은 OpenMV 카메라의 내부 플래시에 저장됨
# OpenMV IDE에서 Tools > Save open script to OpenMV Cam

import network
import time
from config import WIFI_SSID, WIFI_PASSWORD, WIFI_TIMEOUT_MS

def connect_wifi():
    """WiFi 연결 (재시도 포함)"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("[boot] WiFi already connected:", wlan.ifconfig())
        return wlan

    print("[boot] Connecting to WiFi:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
            print("[boot] WiFi connection timeout!")
            return None
        time.sleep_ms(100)

    print("[boot] WiFi connected:", wlan.ifconfig())
    return wlan

# WiFi 연결 시도
wlan = connect_wifi()
