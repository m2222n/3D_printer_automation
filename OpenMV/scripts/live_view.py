# OpenMV AE3 - 라이브 뷰 (가장 단순)
# ================================================
# OpenMV IDE에서 이 스크립트 실행 → 우측 프레임 버퍼에 실시간 영상이 뜬다.
# 카메라 살아있는지·초점·화각·조명 확인용. 저장·추론 없음.
#
# ⚠️ 2026-07-13 미검증: IDE 연결 자체가 "펌웨어 버전 타임아웃"으로 막혀 라이브뷰 실행 못 함.
#    (26년 3월엔 됐음, 원인=Mass Storage 모드/USB 스택 꼬임 추정). 재개=Mac 재부팅부터.
#    상세 트러블슈팅 = 개발 메모리 참조. IDE 기본 helloworld 예제도 동일 csi 방식.
#
# 사용법:
#   1. OpenMV AE3를 USB로 PC(Mac/공장PC)에 연결
#   2. OpenMV IDE 열고 좌하단 연결 버튼(초록 링크) 클릭 → 카메라 연결
#   3. 이 스크립트 열어서 실행(녹색 재생 버튼)
#   4. 우측 상단 프레임 버퍼에 라이브 영상 확인
#      - FPS는 좌하단 상태바에 표시
#      - 초점 안 맞으면 렌즈 링 조정, 어두우면 조명/노출

import csi
import time

# 카메라 초기화 (기존 capture 스크립트와 동일 설정)
csi0 = csi.CSI()
csi0.reset()
csi0.pixformat(csi.RGB565)   # 컬러
csi0.framesize(csi.VGA)      # 640x480
csi0.skip_frames(time=2000)  # 안정화 2초

clock = time.clock()

while True:
    clock.tick()
    img = csi0.snapshot()    # 이 프레임이 IDE 화면에 자동 표시됨
    # FPS를 화면 좌상단에 표시
    img.draw_string(4, 4, "FPS %.1f" % clock.fps(), color=(255, 0, 0), scale=2)
