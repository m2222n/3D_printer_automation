"""
Blaze GigE 발견 진단 — IP 불일치/self-assigned 상태에서도 찾기
=============================================================

macOS + pypylon 에서 Blaze(ToF)가 ping/ARP 에 응답 안 하거나 IP가 어긋나
'discover 실패'로 안 잡힐 때, GigE TL의 EnumerateAllDevices 로 물리 링크의
카메라를 강제로 훑어 실제 IP/서브넷 상태를 출력.

발견되면:
  - 카메라가 self-assigned(169.254.x) 또는 우리 서브넷 밖이면 → ForceIp 로
    올바른 static IP(예: 192.168.30.10)를 임시 부여 시도(--force-ip).

사용:
    # 1) 발견만
    python bin_picking/tests/find_blaze.py

    # 2) 발견 + Blaze를 192.168.30.10 로 강제 설정(en 포트를 30번대로 먼저 맞출 것)
    python bin_picking/tests/find_blaze.py --force-ip 192.168.30.10 --subnet 255.255.255.0
"""
from __future__ import annotations

import argparse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-ip", help="발견된 Blaze에 부여할 static IP")
    ap.add_argument("--subnet", default="255.255.255.0")
    ap.add_argument("--gateway", default="0.0.0.0")
    args = ap.parse_args()

    from pypylon import pylon, genicam

    tlf = pylon.TlFactory.GetInstance()
    gige = tlf.CreateTl("BaslerGigE")

    # GigE TL 전용 강제 열거 (일반 EnumerateDevices보다 링크 스캔에 강함)
    try:
        infos = gige.EnumerateAllDevices()
    except Exception:
        infos = tlf.EnumerateDevices()

    found = list(infos)
    print(f"발견된 GigE 장치: {len(found)}개")
    blaze_info = None
    for d in found:
        mac = d.GetMacAddress() if d.IsMacAddressAvailable() else "N/A"
        ip = d.GetIpAddress() if d.IsIpAddressAvailable() else "N/A"
        subnet = d.GetSubnetMask() if hasattr(d, "IsSubnetMaskAvailable") and d.IsSubnetMaskAvailable() else "N/A"
        model = d.GetModelName() if d.IsModelNameAvailable() else "N/A"
        sn = d.GetSerialNumber() if d.IsSerialNumberAvailable() else "N/A"
        print(f"  - model={model}  SN={sn}")
        print(f"    MAC={mac}  IP={ip}  subnet={subnet}")
        # Blaze MAC 뒷자리 37:BB:6E 또는 모델명 blaze
        if "blaze" in str(model).lower() or "37:bb:6e" in str(mac).lower():
            blaze_info = d

    if blaze_info is None:
        print("\n❌ Blaze 미발견. 전원(24V)·LAN·en포트 확인. "
              "이 스크립트가 0개면 pypylon이 이 링크를 아예 못 봄.")
        return 1

    print(f"\n✅ Blaze 발견: IP={blaze_info.GetIpAddress()}")

    if args.force_ip:
        mac = blaze_info.GetMacAddress()
        print(f"\nForceIp: {mac} → {args.force_ip} / {args.subnet}")
        try:
            gige.ForceIp(mac, args.force_ip, args.subnet, args.gateway)
            print("  ✅ ForceIp 전송. 몇 초 후 ping 확인:")
            print(f"     ping -c 3 {args.force_ip}")
            print("  (임시 IP — 재부팅 시 사라짐. 정식 static은 pylon IP Configurator 권장)")
        except Exception as e:
            print(f"  ❌ ForceIp 실패: {e}")
            return 1
    else:
        print("\n→ 이 IP를 --blaze-ip 로 스크립트에 넘기거나,")
        print("  self-assigned(169.254)면 --force-ip 로 우리 서브넷 IP 부여.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
