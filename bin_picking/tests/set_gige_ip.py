"""
GigE 카메라 IP 강제 지정 (MAC 지정식) — 대역 어긋남 복구용
==========================================================

⭐ 규칙(7/28 확립): **카메라 IP 대역 = 그 카메라가 꽂힌 랜포트 대역**
어긋나면 증상이 헷갈린다 — **열거(발견)는 되는데 열기만 timeout**
(`Failed to download the XML configuration file` / `0xe101800b`).
이유: 열거는 브로드캐스트(모든 포트로 뿌림), 열기는 유니캐스트(정확한 포트 필요).

`find_blaze.py --force-ip` 는 **Blaze에만** 적용된다(모델명으로 골라냄).
ACE2 등 다른 카메라를 옮기려면 이 스크립트로 **MAC을 명시**할 것.

⚠️ ForceIp는 임시다 — 재부팅 시 소멸. 영구 고정은 pylon IP Configurator.
⚠️ 랜포트 IP(`sudo ifconfig en10 192.168.30.1 ...`)도 재부팅 시 소멸하니 함께 확인.

사용:
    # 1) 발견만 (무엇이 어느 대역에 있는지)
    python bin_picking/tests/set_gige_ip.py

    # 2) ACE2를 30 대역으로 (MAC은 콜론 유무·대소문자 무관)
    python bin_picking/tests/set_gige_ip.py --mac 003053381ABC --ip 192.168.30.20

    # 3) 모델명 일부로 지정해도 됨 (MAC 대신)
    python bin_picking/tests/set_gige_ip.py --match a2A2448 --ip 192.168.30.20
"""
from __future__ import annotations

import argparse


def _norm_mac(s: str) -> str:
    """콜론·하이픈·공백 제거 + 대문자 — 표기 차이를 흡수."""
    return "".join(c for c in str(s) if c.isalnum()).upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mac", help="대상 카메라 MAC (예: 003053381ABC 또는 00:30:53:38:1A:BC)")
    ap.add_argument("--match", help="MAC 대신 모델명 부분일치로 지정 (예: a2A2448)")
    ap.add_argument("--ip", help="부여할 static IP (예: 192.168.30.20)")
    ap.add_argument("--subnet", default="255.255.255.0")
    ap.add_argument("--gateway", default="0.0.0.0")
    args = ap.parse_args()

    from pypylon import pylon

    tlf = pylon.TlFactory.GetInstance()
    gige = tlf.CreateTl("BaslerGigE")

    # GigE TL 전용 열거가 링크 스캔에 강함 (7/20 확립)
    try:
        found = list(gige.EnumerateAllDevices())
    except Exception:
        found = list(tlf.EnumerateDevices())

    print(f"발견된 GigE 장치: {len(found)}개")
    rows = []
    for d in found:
        mac = d.GetMacAddress() if d.IsMacAddressAvailable() else ""
        ip = d.GetIpAddress() if d.IsIpAddressAvailable() else "N/A"
        model = d.GetModelName() if d.IsModelNameAvailable() else "N/A"
        sn = d.GetSerialNumber() if d.IsSerialNumberAvailable() else "N/A"
        rows.append((model, sn, mac, ip))
        print(f"  - model={model}  SN={sn}")
        print(f"    MAC={mac}  IP={ip}")

    if not args.ip:
        print("\n→ 옮길 카메라를 --mac 또는 --match 로 지정하고 --ip 를 주면 ForceIp 실행.")
        print("  ⚠️ 부여할 IP 대역 = 그 카메라가 꽂힌 랜포트 대역과 같아야 함.")
        return 0

    if not (args.mac or args.match):
        print("\n❌ --ip 를 줬으면 --mac 또는 --match 로 대상을 명시해야 한다.")
        print("   (실수로 다른 카메라 IP를 덮어쓰는 것을 막기 위해 필수)")
        return 2

    # 대상 선별 — MAC 우선, 없으면 모델명 부분일치
    target = None
    if args.mac:
        want = _norm_mac(args.mac)
        cands = [r for r in rows if _norm_mac(r[2]) == want]
    else:
        want = args.match.lower()
        cands = [r for r in rows if want in str(r[0]).lower()]

    if not cands:
        print(f"\n❌ 대상 미발견: {args.mac or args.match}")
        return 1
    if len(cands) > 1:
        print(f"\n❌ 대상이 {len(cands)}개 매칭됨 — MAC으로 정확히 지정할 것:")
        for m, sn, mac, ip in cands:
            print(f"   {m}  MAC={mac}  IP={ip}")
        return 1

    target = cands[0]
    model, sn, mac, cur_ip = target
    if not mac:
        print(f"\n❌ {model}: MAC을 읽을 수 없어 ForceIp 불가.")
        return 1

    print(f"\n대상: {model} (SN={sn})")
    print(f"  MAC   : {mac}")
    print(f"  현재IP: {cur_ip}")
    print(f"  변경  : {cur_ip} → {args.ip} / {args.subnet}")

    try:
        gige.ForceIp(mac, args.ip, args.subnet, args.gateway)
    except Exception as e:
        print(f"\n❌ ForceIp 실패: {e}")
        print("   권한 문제면 sudo 로 재실행.")
        return 1

    print("\n✅ ForceIp 전송. 몇 초 후 확인:")
    print(f"   python bin_picking/tests/set_gige_ip.py        # IP가 바뀌었나")
    print(f"   ping -c 2 {args.ip}                            # ⚠️ Blaze(ToF)는 ICMP 무응답이 정상")
    print("   (임시 IP — 재부팅 시 소멸. 영구 고정은 pylon IP Configurator)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
