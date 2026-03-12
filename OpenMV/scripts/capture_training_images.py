# OpenMV AE3 - Edge Impulse 학습용 이미지 캡처 스크립트
# ==================================================
# 공장에서 세척기/경화기 앞에 카메라를 두고 실행
# 버튼(또는 자동 타이머)으로 이미지를 내부 플래시에 저장
#
# 사용법:
#   1. OpenMV IDE에서 이 스크립트 실행
#   2. 카메라를 세척기/경화기 앞에 위치
#   3. 시리얼 터미널에서 상태 라벨 선택 (1/2/3)
#   4. 스페이스바 또는 자동 타이머로 캡처
#   5. 캡처 완료 후 USB로 PC에 이미지 복사
#
# 저장 위치: /images/{label}/img_XXXX.jpg
# Edge Impulse 업로드: 폴더별로 라벨 자동 분류

import time
import gc
import os

# CSI 카메라 초기화
import csi

csi0 = csi.CSI()
csi0.reset()
csi0.pixformat(csi.RGB565)
csi0.framesize(csi.VGA)
csi0.window((240, 240))

# ===========================================
# 설정
# ===========================================

# 장비 타입 선택 (카메라 설치 위치에 맞게 변경)
DEVICE_TYPE = "wash"  # "wash" or "cure"

# 상태 라벨 정의
if DEVICE_TYPE == "wash":
    LABELS = {
        "1": "wash_idle",
        "2": "wash_running",
        "3": "wash_complete",
    }
else:
    LABELS = {
        "1": "cure_idle",
        "2": "cure_running",
        "3": "cure_complete",
    }

# 자동 캡처 간격 (초), 0이면 수동 모드
AUTO_CAPTURE_INTERVAL = 2

# 이미지 크기 (Edge Impulse 권장: 96x96 또는 160x160)
IMG_WIDTH = 240
IMG_HEIGHT = 240

# ===========================================
# 디렉토리 준비
# ===========================================

def ensure_dir(path):
    """디렉토리 생성 (없으면)"""
    try:
        os.stat(path)
    except OSError:
        try:
            os.mkdir(path)
        except OSError:
            # 부모 디렉토리부터 생성
            parts = path.strip("/").split("/")
            current = ""
            for part in parts:
                current += "/" + part
                try:
                    os.stat(current)
                except OSError:
                    os.mkdir(current)

def count_files(path):
    """디렉토리 내 파일 수 카운트"""
    try:
        return len(os.listdir(path))
    except OSError:
        return 0

# 기본 디렉토리 생성
ensure_dir("/images")
for label in LABELS.values():
    ensure_dir("/images/" + label)

# ===========================================
# 캡처 함수
# ===========================================

def capture_image(label):
    """이미지 캡처 + 저장"""
    img = csi0.snapshot()

    # 파일명 생성 (순번)
    save_dir = "/images/" + label
    idx = count_files(save_dir)
    filename = "{}/img_{:04d}.jpg".format(save_dir, idx)

    # JPEG로 저장
    img.save(filename, quality=90)

    gc.collect()
    return filename, idx + 1

# ===========================================
# 메인 루프
# ===========================================

print("=" * 50)
print("Edge Impulse 학습용 이미지 캡처")
print("=" * 50)
print()
print("장비 타입:", DEVICE_TYPE)
print("라벨 목록:")
for key, label in LABELS.items():
    existing = count_files("/images/" + label)
    print("  [{}] {} (기존 {}장)".format(key, label, existing))
print()

current_label = list(LABELS.values())[0]
print("현재 라벨: {} (변경: 1/2/3 입력)".format(current_label))
print("캡처 모드: {}초 간격 자동".format(AUTO_CAPTURE_INTERVAL) if AUTO_CAPTURE_INTERVAL > 0 else "캡처 모드: 수동")
print()
print("시작하려면 IDE에서 Run 버튼 누르기")
print("중지하려면 Stop 버튼")
print("=" * 50)

capturing = False
last_capture_time = 0

while True:
    try:
        # 프레임 표시 (IDE 프레임 버퍼에 실시간 미리보기)
        img = csi0.snapshot()

        # 시리얼 입력 처리 (IDE 터미널에서)
        # OpenMV IDE에서는 직접 입력이 제한적이므로
        # 자동 캡처 모드를 기본으로 사용

        now = time.ticks_ms()

        if AUTO_CAPTURE_INTERVAL > 0:
            if time.ticks_diff(now, last_capture_time) >= AUTO_CAPTURE_INTERVAL * 1000:
                filename, total = capture_image(current_label)
                print("[{}] 저장: {} (총 {}장)".format(current_label, filename, total))
                last_capture_time = now

        gc.collect()
        time.sleep_ms(100)

    except KeyboardInterrupt:
        break
    except Exception as e:
        print("오류:", e)
        time.sleep(1)

print()
print("캡처 종료. 결과:")
for label in LABELS.values():
    count = count_files("/images/" + label)
    print("  {}: {}장".format(label, count))
print()
print("이미지를 PC로 복사하려면:")
print("  1. IDE 중지 (Stop)")
print("  2. Tools > Save open script to camera")
print("  3. USB 드라이브 (/Volumes/NO NAME/images/) 에서 복사")
print("  또는 IDE의 Files 탭에서 /images/ 폴더 다운로드")
