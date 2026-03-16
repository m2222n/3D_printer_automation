# OpenMV AE3 - 세척기(Form Wash) 학습용 이미지 캡처
# ================================================
# IDE Frame Buffer → Mac 직접 저장 방식 (플래시 저장 소실 문제 해결)
#
# 사용법:
#   1. OpenMV IDE에서 이 스크립트 열기 → Connect → Run
#   2. IDE 우측 Frame Buffer에 실시간 영상 표시됨
#   3. IDE 메뉴: Tools > Dataset Editor 또는 Frame Buffer 우클릭 > Save Image
#      - Dataset Editor: 폴더 지정 후 캡처 버튼으로 Mac에 직접 저장
#      - 또는 Record 버튼으로 연속 저장
#   4. 상태 변경 시 저장 폴더를 바꿔서 반복
#
# 촬영 계획:
#   wash_idle     — 세척기 꺼진 상태 (100장+)
#   wash_running  — 세척 진행 중 (100장+)
#   wash_complete — 세척 완료 (100장+)

import time
import gc
import csi

csi0 = csi.CSI()
csi0.reset()
csi0.pixformat(csi.RGB565)
csi0.framesize(csi.VGA)
csi0.window((240, 240))

print("=" * 50)
print("세척기(Form Wash) 이미지 캡처")
print("IDE Frame Buffer → Mac 직접 저장")
print("=" * 50)
print()
print("촬영 상태:")
print("  wash_idle     — 꺼진 상태")
print("  wash_running  — 세척 중")
print("  wash_complete — 완료")
print()
print("저장 방법:")
print("  Frame Buffer 우클릭 > Save Image")
print("  또는 Tools > Dataset Editor")
print("=" * 50)

frame_count = 0

while True:
    try:
        img = csi0.snapshot()
        frame_count += 1
        if frame_count % 100 == 0:
            gc.collect()
        time.sleep_ms(50)
    except KeyboardInterrupt:
        break

print("종료. 총 프레임:", frame_count)
