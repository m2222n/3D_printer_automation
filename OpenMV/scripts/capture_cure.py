# OpenMV AE3 - 경화기(Form Cure) 학습용 이미지 캡처
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
#   cure_idle     — 경화기 꺼진 상태 (100장+)
#   cure_running  — 경화 진행 중, 디스플레이 활성 (100장+)
#   cure_complete — 경화 완료, 디스플레이 완료 표시 (100장+)
#
# 팁: 경화기 디스플레이 화면을 디텍션하는 게 조명 조건에 덜 민감 (한솔 조언)

import time
import gc
import csi

csi0 = csi.CSI()
csi0.reset()
csi0.pixformat(csi.RGB565)
csi0.framesize(csi.VGA)
csi0.window((240, 240))

print("=" * 50)
print("경화기(Form Cure) 이미지 캡처")
print("IDE Frame Buffer → Mac 직접 저장")
print("=" * 50)
print()
print("촬영 상태:")
print("  cure_idle     — 꺼진 상태")
print("  cure_running  — 경화 중")
print("  cure_complete — 완료")
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
