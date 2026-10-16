"""운영 화면 패널 e2e — 실제 브라우저(chromium headless)로 로그인 → 모니터링 탭 → 패널 2개가 WebSocket 으로 3초 안에 바뀌는가.
사용: python e2e_panels.py --base http://<ip>:<port> --user U --pw P [--events <events.json>]
"""
import argparse, json, sys, time, urllib.request
from playwright.sync_api import sync_playwright

def api(base, path, token=None, data=None, method=None):
    req = urllib.request.Request(base + path, method=method or ("POST" if data is not None else "GET"),
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read().decode() or "null")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", required=True); ap.add_argument("--user", required=True); ap.add_argument("--pw", required=True)
    ap.add_argument("--chromium", default="/usr/bin/chromium-browser"); ap.add_argument("--out", default="e2e_out")
    a = ap.parse_args()
    ok = True
    def check(name, cond):
        nonlocal ok; print(("  🟢 " if cond else "  🔴 ") + name); ok = ok and bool(cond)

    _, tok = api(a.base, "/api/v1/auth/login", data={"username": a.user, "password": a.pw}); token = tok["access_token"]

    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=a.chromium, headless=True, args=["--no-sandbox", "--disable-gpu"])
        pg = br.new_page(viewport={"width": 1400, "height": 1000})
        logs = []; pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.goto(a.base + "/", wait_until="domcontentloaded")
        # 로그인 화면
        pg.fill("input[name=username], input[type=text]", a.user); pg.fill("input[type=password]", a.pw)
        pg.click("button[type=submit]")
        pg.wait_for_selector("[data-testid=cell-monitor]", timeout=20000)
        check("패널 섹션이 모니터링 탭에 렌더링된다", True)
        time.sleep(2.5)  # WS 접속 대기
        badges = pg.locator("[data-testid=cell-monitor] span:has-text('실시간')").count()
        check(f"패널 2개가 WebSocket '실시간' 상태 ({badges}/2)", badges == 2)
        printer_live = pg.locator("header div.rounded-full:has-text('실시간')").count()   # 프린터 배지는 div(패널 배지는 span)
        check(f"프린터 WebSocket 도 '실시간' (토큰 수정 · {printer_live})", printer_live >= 1)

        # ── 셀A: 시뮬레이터로 상태 변경 → 카드가 3초 안에 바뀌는가
        cards = pg.locator("[data-testid^=device-]").count()
        print(f"  ℹ️ 설비 카드 {cards}장")
        target = "wash_1"
        for st in ("wash_running", "wash_complete", "wash_idle"):
            t0 = time.time()
            api(a.base, "/api/v1/vision/simulate", token, {"camera_id": target, "status": st, "confidence": 0.95})
            try:
                pg.wait_for_selector(f"[data-testid=device-wash-1][data-status={st}]", timeout=3000)
                dt = time.time() - t0
                check(f"셀A {target} → {st} 가 화면에 {dt*1000:.0f}ms 만에 반영 (<3000)", dt < 3.0)
            except Exception as e:
                check(f"셀A {target} → {st} 3초 안 반영 실패: {type(e).__name__}", False)
        label = pg.locator("[data-testid=device-wash-1]").inner_text()
        check("카드에 '대기' 글자 + 경과 시간 표시", "대기" in label and "전 변경" in label)

        # ── 셀B: 보고 1건 → 패널이 3초 안에 바뀌는가 (판정 배지 포함)
        scene_id = f"e2e_{int(time.time())}"
        payload = {"schema_version": "1.0", "module": "bin_picking", "scene_id": scene_id, "timestamp": "2026-10-16T16:00:00",
                   "summary": {"n_detections": 2, "n_unique_labels": 2, "recognition_track": "depth", "latency_ms": 1321.0},
                   "scene_gate": {"verdict": "in_distribution", "trusted": True, "valid_ratio_pct": 2.6, "note": "[e2e]", "n_dropped_by_size_gate": 0},
                   "detections": [{"idx": 0, "label": "02_sol_block_b", "x": 1, "y": 2, "z": 480, "angle": 90, "confidence": 0.91, "gripper_width_mm": 55.0},
                                  {"idx": 1, "label": "plate_e", "x": 3, "y": 4, "z": 481, "angle": 10, "confidence": 0.80, "gripper_width_mm": 60.0}]}
        t0 = time.time(); st, body = api(a.base, "/api/v1/binpick/reports", token, payload)
        try:
            pg.wait_for_selector(f"[data-testid=binpick-scene][data-scene-pk='{body['scene_pk']}']", timeout=3000)
            dt = time.time() - t0
            check(f"셀B 장면 수신 → 패널 반영 {dt*1000:.0f}ms (<3000)", dt < 3.0)
            pg.wait_for_selector("[data-testid=binpick-scene] td:has-text('plate_e')", timeout=3000)
            check("상세 재조회로 부품 목록(02_sol_block_b · plate_e)이 뜬다", pg.locator("[data-testid=binpick-scene] td:has-text('02_sol_block_b')").count() == 1)
            txt = pg.locator("[data-testid=binpick-scene]").inner_text()
            check("판정 배지 '정상' · 부품 2개 · 인식 1.32초", "정상" in txt and "2" in pg.locator("[data-testid=binpick-count]").inner_text() and "1.32초" in txt)
        except Exception as e:
            check(f"셀B 패널 반영 실패: {type(e).__name__}: {e}", False)
        # 분포 밖 장면 → 목록 흐림 + 경고
        payload["scene_id"] = scene_id + "_bad"; payload["scene_gate"]["verdict"] = "out_of_distribution"; payload["scene_gate"]["trusted"] = False
        st, body = api(a.base, "/api/v1/binpick/reports", token, payload)
        pg.wait_for_selector(f"[data-testid=binpick-scene][data-verdict=out_of_distribution]", timeout=3000)
        check("분포 밖 장면 = '화면 이상' 배지 + 목록 흐림(opacity-40)", "화면 이상" in pg.locator("[data-testid=binpick-scene]").inner_text()
              and pg.locator("[data-testid=binpick-scene] table.opacity-40").count() == 1)

        pg.screenshot(path=f"{a.out}_panels.png", full_page=True)
        errs = [l for l in logs if l.startswith("error")]
        check(f"브라우저 콘솔 error 0건 ({len(errs)})", len(errs) == 0)
        for l in errs[:5]: print("     ", l)
        br.close()
    print("  ✅ 통과" if ok else "  🔴 실패"); return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
