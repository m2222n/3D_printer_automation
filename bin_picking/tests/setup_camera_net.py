"""
휴대용 랜어댑터 환경 — 꽂을 때마다 카메라 네트워크 한 줄로 맞추기
================================================================

⭐ 배경: 랜어댑터를 꽂았다 뺐다 하면 macOS가 인터페이스 번호(en10→en11…)를
   다시 부여하고, GUI로 en10에 걸어둔 수동 IP가 새 번호엔 적용되지 않는다.
   7/29 아침 1시간 삽질의 구조적 원인 = **매번 어느 en에 뭐가 물렸는지 모른다**.

이 스크립트가 하는 일:
  1. 살아있는 이더넷 인터페이스(en*)를 훑어 **IP가 없거나 APIPA(169.254)** 인 것을 찾음
  2. 카메라를 열거해 **각 카메라가 요구하는 대역**을 확인
  3. 부족한 랜포트 IP를 `ifconfig`로 채우는 **명령을 출력**(--apply면 직접 실행)

⚠️ 카메라 IP 자체는 pylon IP Configurator로 **한 번 영구 고정**해두는 것이 정답
   (카메라 내부 메모리에 저장 → 어느 포트에 꽂아도 유지).
   이 스크립트는 그 **맥 쪽 짝(랜포트 IP)** 을 매번 맞춰주는 용도다.

사용:
    # 진단만 (무엇이 어긋났나)
    python bin_picking/tests/setup_camera_net.py

    # 실제 적용 (sudo 필요 — ifconfig)
    sudo python bin_picking/tests/setup_camera_net.py --apply
"""
from __future__ import annotations

import argparse
import re
import subprocess

# 우리 카메라가 사는 대역 → 그 대역에서 맥이 쓸 IP
#   ⚠️ 배선/카메라 IP를 바꿨으면 여기도 갱신 (docs/gige_ip_permanent_setup.md 표와 함께)
SUBNETS = {
    "192.168.20": "192.168.20.1",   # Blaze-112
    "192.168.30": "192.168.30.1",   # ACE2 (a2A2448)
}


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


def list_ifaces() -> dict[str, dict]:
    """en* 인터페이스별 {status, ip} — ifconfig 파싱."""
    out = sh(["ifconfig", "-a"])
    ifaces: dict[str, dict] = {}
    cur = None
    for line in out.splitlines():
        m = re.match(r"^(en\d+):", line)
        if m:
            cur = m.group(1)
            ifaces[cur] = {"status": "unknown", "ip": None}
            continue
        if cur is None:
            continue
        m = re.search(r"^\s+inet (\d+\.\d+\.\d+\.\d+)", line)
        if m:
            ifaces[cur]["ip"] = m.group(1)
        m = re.search(r"status: (\w+)", line)
        if m:
            ifaces[cur]["status"] = m.group(1)
    return ifaces


def list_cameras() -> list[tuple[str, str, str]]:
    """(model, ip, mac) — pypylon 열거. 실패해도 진단은 계속한다."""
    try:
        from pypylon import pylon
    except Exception as e:
        print(f"  (pypylon 없음 — 카메라 열거 생략: {e})")
        return []
    try:
        tlf = pylon.TlFactory.GetInstance()
        gige = tlf.CreateTl("BaslerGigE")
        try:
            devs = list(gige.EnumerateAllDevices())
        except Exception:
            devs = list(tlf.EnumerateDevices())
        rows = []
        for d in devs:
            rows.append((
                d.GetModelName() if d.IsModelNameAvailable() else "?",
                d.GetIpAddress() if d.IsIpAddressAvailable() else "?",
                d.GetMacAddress() if d.IsMacAddressAvailable() else "?",
            ))
        return rows
    except Exception as e:
        print(f"  (카메라 열거 실패: {e})")
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="ifconfig 를 직접 실행 (sudo 필요). 없으면 명령만 출력")
    args = ap.parse_args()

    ifaces = list_ifaces()
    active = {k: v for k, v in ifaces.items() if v["status"] == "active"}

    print("=== 이더넷 인터페이스 (active) ===")
    if not active:
        print("  ❌ active 인터페이스 없음 — 어댑터가 안 꽂혔거나 링크 미확립")
        return 1
    for name, info in sorted(active.items()):
        ip = info["ip"] or "(IP 없음)"
        flag = ""
        if info["ip"] and info["ip"].startswith("169.254"):
            flag = "  ⚠️ APIPA = DHCP 실패, 수동 IP 필요"
        elif info["ip"] is None:
            flag = "  ⚠️ IP 없음"
        print(f"  {name:6s} {ip}{flag}")

    have = {ip.rsplit(".", 1)[0] for i in active.values() if (ip := i["ip"])}

    print("\n=== 카메라 열거 ===")
    cams = list_cameras()
    if cams:
        for model, ip, mac in cams:
            pfx = ip.rsplit(".", 1)[0] if ip.count(".") == 3 else "?"
            ok = "✅" if pfx in have else "❌ 이 대역의 랜포트가 없음"
            print(f"  {model:22s} {ip:16s} MAC={mac}  {ok}")
    else:
        print("  (열거 0대 — 랜포트 IP를 먼저 맞추면 보일 수 있다)")

    # 비어 있는 대역 = 채워야 할 것
    missing = [(pfx, host) for pfx, host in SUBNETS.items() if pfx not in have]
    # IP가 없거나 APIPA인 포트 = 채울 자리
    free = [n for n, i in sorted(active.items())
            if i["ip"] is None or i["ip"].startswith("169.254")]

    print("\n=== 판정 ===")
    if not missing:
        print("  ✅ 필요한 대역이 모두 랜포트에 있음. 추가 조치 불필요.")
        return 0

    print(f"  비어 있는 대역: {', '.join(p + '.x' for p, _ in missing)}")
    if not free:
        print("  ⚠️ 채울 수 있는 빈 포트가 없다. 어댑터를 더 꽂거나,")
        print("     이미 다른 IP가 붙은 포트를 수동으로 비워야 한다.")
        print("     (현재 포트에 이미 IP가 있으면 이 스크립트는 건드리지 않는다)")
        return 1

    for (pfx, host), iface in zip(missing, free):
        cmd = ["ifconfig", iface, host, "netmask", "255.255.255.0", "up"]
        print(f"\n  {iface} → {host}/24")
        if args.apply:
            r = subprocess.run(["sudo"] + cmd, capture_output=True, text=True)
            if r.returncode == 0:
                print("    ✅ 적용됨")
            else:
                print(f"    ❌ 실패: {r.stderr.strip()}  (sudo 로 실행했나?)")
        else:
            print(f"    sudo {' '.join(cmd)}")

    if not args.apply:
        print("\n  → 위 명령을 실행하거나 --apply 로 재실행 (sudo 필요)")
    else:
        print("\n  → 확인: python bin_picking/tests/setup_camera_net.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
