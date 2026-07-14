#!/usr/bin/env python3
# OpenMV AE3 자동 캡처 v3 — Mac에 PNG 저장 + focus 표시 미리보기 (IDE 불필요)
# =====================================================================
# 배경: 세척기/경화기 상태 학습 데이터를 OpenMV 실물로 촬영(2026-07-14 공장).
#   USB 선이 짧아 카메라를 손으로 들어야 함 → IDE Dataset Editor(버튼 매번)·
#   테이프 초점고정·IDE 영상녹화(인텔 Mac ffmpeg 실행 불가) 모두 부적합 →
#   "IDE 없이 스크립트 하나로 초점 확인 + 자동 저장"이 최종 결론.
#
# v1(어제 openmv_capture.py) 깨짐 원인·해결:
#   - 일반 REPL로 base64 주고받아 에코/개행 섞임 → JPEG 손상(미리보기 못 엶).
#   - 해결 = raw REPL(Ctrl-A) 프레이밍 + 디코딩 검증 후 PNG 재저장(깨진 프레임 스킵).
#   → PNG 정상 열림 검증 완료.
#
# 사용법:
#   1) OpenMV IDE 완전 종료(Cmd-Q) — 같은 시리얼 포트 충돌(Resource busy) 방지
#   2) 터미널: python3 ~/Desktop/openmv_capture_v3.py
#   3) 라벨 입력 (wash_idle/wash_running/wash_complete/cure_idle/cure_running/cure_complete)
#   4) 창이 PAUSED로 시작 → FOCUS 숫자 보며 렌즈 돌려 초점 최대로 (숫자 높을수록 선명)
#   5) p = 촬영 시작(3초 자동 저장) / 다시 p = 정지(조건 바꿀 때) / s = 즉시저장 / q = 종료
#   6) 저장 → ~/Desktop/openmv_0714/<라벨>/  (PNG)
#
# ⚠️ 포트가 14201이 아니면 아래 PORT 수정 (터미널: ls /dev/cu.usbmodem*)
# ⚠️ 미리보기는 base64 왕복(115200)이라 끊김 = 정상. 초점은 정지화면 선명도로 판단 OK.
#    매끄러운 라이브뷰가 필요하면 그건 IDE만 가능(단 IDE는 촬영 자동화 안 됨).

import serial, time, os, sys, base64

PORT = "/dev/cu.usbmodem14201"
INTERVAL = 3.0
BASE = os.path.expanduser("~/Desktop/openmv_0714")

try:
    import cv2, numpy as np
    HAVE_CV = True
except ImportError:
    HAVE_CV = False
    print("opencv 없음 → 미리보기 없이 저장만. (pip3 install opencv-python)")

label = input("라벨 입력 (예: wash_running / cure_idle): ").strip() or "capture"
outdir = os.path.join(BASE, label)
os.makedirs(outdir, exist_ok=True)
print(f"→ 저장 폴더: {outdir}")

try:
    s = serial.Serial(PORT, 115200, timeout=1)
except serial.SerialException as e:
    print(f"포트 열기 실패: {e}")
    print("→ OpenMV IDE Cmd-Q로 종료 후 재실행. 포트확인: ls /dev/cu.usbmodem*")
    sys.exit(1)
time.sleep(0.3)

def raw_repl_exec(code, read_timeout=6.0):
    """raw REPL로 code 실행 후 stdout(bytes) 반환. \x04 프레이밍."""
    s.write(b'\x03'); time.sleep(0.1)   # Ctrl-C 정지
    s.write(b'\x01'); time.sleep(0.1)   # Ctrl-A raw REPL
    s.reset_input_buffer()
    s.write(code.encode() + b'\x04')    # 코드 + Ctrl-D 실행
    buf = b""; t0 = time.time()
    while buf.count(b'\x04') < 2 and time.time() - t0 < read_timeout:
        chunk = s.read(8192)
        if chunk: buf += chunk
    s.write(b'\x02')                    # Ctrl-B 복귀
    if b'OK' in buf:
        return buf.split(b'OK', 1)[1].split(b'\x04')[0]
    return b""

init = (
 "import sensor,ubinascii\n"
 "sensor.reset()\n"
 "sensor.set_pixformat(sensor.RGB565)\n"
 "sensor.set_framesize(sensor.VGA)\n"
 "sensor.set_auto_gain(True)\n"
 "sensor.skip_frames(time=2000)\n"
 "print('INIT_OK')\n"
)
r = raw_repl_exec(init, read_timeout=8.0)
if b'INIT_OK' not in r:
    print("카메라 초기화 실패:", r[:200]); s.close(); sys.exit(1)
print("카메라 초기화 완료.")

SNAP = ("img=sensor.snapshot().compress(quality=90)\n"
        "print(ubinascii.b2a_base64(img.bytearray()).decode().strip())\n")

n = 0; last_save = 0.0; paused = True
print(">>> 창에서: p=촬영시작/정지  s=즉시저장  q=종료. 처음엔 FOCUS 숫자 보며 초점 맞추세요.")
try:
    while True:
        out = raw_repl_exec(SNAP, read_timeout=5.0)
        lines = [ln for ln in out.split(b'\n') if ln.strip()]
        jpg = None
        if lines:
            try: jpg = base64.b64decode(lines[-1].strip())
            except Exception: jpg = None
        frame = None
        if jpg and HAVE_CV:
            arr = np.frombuffer(jpg, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)   # 깨졌으면 None

        now = time.time(); want_save = (now - last_save) >= INTERVAL; key = -1
        if HAVE_CV and frame is not None:
            disp = frame.copy()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            focus = cv2.Laplacian(gray, cv2.CV_64F).var()   # 라플라시안 분산=선명도
            cv2.putText(disp, f"FOCUS: {focus:.0f}", (8,30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,255,255), 2)
            cv2.putText(disp, f"{label} saved:{n}", (8,62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
            if paused:
                cv2.putText(disp, "PAUSED (p=start)", (8,94),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
            cv2.imshow("OpenMV (p=start/stop s=save q=quit)", disp)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'): break
            if key == ord('s'): want_save = True
            if key == ord('p'): paused = not paused
        if paused: want_save = False

        if want_save:
            fn = os.path.join(outdir, f"{label}_{n:04d}.png"); ok = False
            if HAVE_CV and frame is not None:
                ok = cv2.imwrite(fn, frame)
            elif jpg and not HAVE_CV:
                fn = fn[:-4] + ".jpg"
                with open(fn, "wb") as f: f.write(jpg); ok = True
            if ok:
                n += 1; last_save = now; print(f"저장 {n}장  {fn}")
            else:
                print("프레임 깨짐 → 스킵(재시도)")
except KeyboardInterrupt:
    pass
finally:
    if HAVE_CV: cv2.destroyAllWindows()
    s.close(); print(f"\n종료. 총 {n}장 → {outdir}")
