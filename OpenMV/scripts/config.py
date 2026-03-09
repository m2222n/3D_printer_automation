# OpenMV AE3 카메라 설정
# ========================
# 카메라별로 이 파일의 값을 수정하여 사용

# ===========================================
# WiFi 설정
# ===========================================
WIFI_SSID = "FACTORY_WIFI"
WIFI_PASSWORD = "factory_password"
WIFI_TIMEOUT_MS = 10000

# ===========================================
# MQTT 설정
# ===========================================
MQTT_BROKER = "192.168.219.xxx"  # 서버 IP (6000 서버)
MQTT_PORT = 1883
MQTT_KEEPALIVE = 60

# ===========================================
# 카메라 식별 (카메라별 수정 필요)
# ===========================================
# wash_1, wash_2, cure_1, cure_2 중 하나
CAMERA_ID = "wash_1"
DEVICE_TYPE = "wash"   # "wash" or "cure"
DEVICE_ID = 1          # 1 or 2

# ===========================================
# MQTT 토픽 (자동 생성)
# ===========================================
TOPIC_PREFIX = "factory"
TOPIC_STATUS = "{}/{}/{}/status".format(TOPIC_PREFIX, DEVICE_TYPE, DEVICE_ID)
TOPIC_HEARTBEAT = "{}/{}/{}/heartbeat".format(TOPIC_PREFIX, DEVICE_TYPE, DEVICE_ID)
TOPIC_INFO = "{}/camera/{}/info".format(TOPIC_PREFIX, CAMERA_ID)

# ===========================================
# AI 추론 설정
# ===========================================
CONFIDENCE_THRESHOLD = 0.7     # 최소 confidence (이하 무시)
DEBOUNCE_COUNT = 5             # 연속 N프레임 동일 결과 시 상태 전환

# ===========================================
# 타이밍 설정
# ===========================================
HEARTBEAT_INTERVAL_S = 30      # 하트비트 전송 주기 (초)
WATCHDOG_TIMEOUT_MS = 10000    # Watchdog 타임아웃 (ms)

# ===========================================
# 카메라 설정
# ===========================================
FRAME_WIDTH = 240
FRAME_HEIGHT = 240
