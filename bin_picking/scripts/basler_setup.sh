#!/usr/bin/env bash
# ============================================================
# Basler pylon + Blaze-112 설치 스크립트 (Ubuntu 22.04 x86_64)
# ------------------------------------------------------------
# 비전 PC에서 실행. 카메라 도착 당일 3시간 → 1시간으로 단축.
#
# 실행 전 준비물 (~/Downloads/basler/ 에 배치):
#   - pylon/pylon_<version>_linux-x86_64_debs.tar.gz
#   - blaze/Basler_blaze_<version>_linux-x86_64.tar.gz (또는 .deb)
#
# 사용법:
#   bash basler_setup.sh                # 전체 실행
#   bash basler_setup.sh --check        # 설치 상태만 확인
#   bash basler_setup.sh --network      # 네트워크 튜닝만
#
# 참고: docs/basler_download_checklist.md
# ============================================================

set -euo pipefail

# ---------- 색상 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---------- 변수 ----------
DOWNLOAD_DIR="${BASLER_DOWNLOAD_DIR:-$HOME/Downloads/basler}"
PYLON_DIR="$DOWNLOAD_DIR/pylon"
BLAZE_DIR="$DOWNLOAD_DIR/blaze"
PYLON_INSTALL_ROOT="/opt/pylon"

# ---------- 실행 모드 ----------
MODE="${1:-full}"

# ============================================================
# 0. 사전 점검
# ============================================================
pre_check() {
    log_info "사전 점검 시작..."

    # OS 확인
    if [[ ! -f /etc/os-release ]]; then
        log_error "Linux 배포판을 식별할 수 없습니다."
        exit 1
    fi

    source /etc/os-release
    log_info "OS: $PRETTY_NAME"

    if [[ "$ID" != "ubuntu" ]]; then
        log_warn "Ubuntu 외 배포판은 검증되지 않았습니다. 계속 진행하려면 Ctrl+C 후 수동 진행."
    fi

    # 아키텍처 확인
    local arch
    arch=$(uname -m)
    if [[ "$arch" != "x86_64" ]]; then
        log_error "x86_64 아키텍처 필요 (현재: $arch)"
        exit 1
    fi

    # 네트워크 인터페이스 확인
    local iface_count
    iface_count=$(ip -o link show | grep -E 'eno|enp|eth' | wc -l)
    log_info "이더넷 인터페이스 수: $iface_count"
    if (( iface_count < 2 )); then
        log_warn "GigE 카메라 2대 연결에는 이더넷 포트 2개 이상 필요"
    fi

    log_ok "사전 점검 완료"
}

# ============================================================
# 1. pylon 설치 파일 확인
# ============================================================
check_files() {
    log_info "설치 파일 확인..."

    if [[ ! -d "$PYLON_DIR" ]]; then
        log_error "pylon 디렉토리 없음: $PYLON_DIR"
        log_info "docs/basler_download_checklist.md 참고하여 다운로드 후 재실행"
        exit 1
    fi

    local pylon_archive
    pylon_archive=$(find "$PYLON_DIR" -maxdepth 1 \
        \( -name "pylon*debs.tar.gz" -o -name "pylon*linux-x86_64.tar.gz" \) \
        | head -1)
    if [[ -z "$pylon_archive" ]]; then
        log_error "pylon 아카이브 없음 (pylon*.tar.gz)"
        exit 1
    fi
    log_ok "pylon 아카이브: $(basename "$pylon_archive")"
    export PYLON_ARCHIVE="$pylon_archive"

    if [[ ! -d "$BLAZE_DIR" ]]; then
        log_warn "Blaze 디렉토리 없음: $BLAZE_DIR (Blaze 설치 스킵)"
        export BLAZE_ARCHIVE=""
    else
        local blaze_archive
        blaze_archive=$(find "$BLAZE_DIR" -maxdepth 1 \
            \( -name "*blaze*.tar.gz" -o -name "*blaze*.deb" \) \
            | head -1)
        if [[ -z "$blaze_archive" ]]; then
            log_warn "Blaze 아카이브 없음 - Blaze 설치 스킵"
            export BLAZE_ARCHIVE=""
        else
            log_ok "Blaze 아카이브: $(basename "$blaze_archive")"
            export BLAZE_ARCHIVE="$blaze_archive"
        fi
    fi
}

# ============================================================
# 2. pylon 설치
# ============================================================
install_pylon() {
    log_info "pylon 설치..."

    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap 'rm -rf "$tmp_dir"' EXIT

    log_info "아카이브 압축 해제: $tmp_dir"
    tar -xzf "$PYLON_ARCHIVE" -C "$tmp_dir"

    # debs 패키지 방식 우선
    local deb_files
    deb_files=$(find "$tmp_dir" -name "*.deb")
    if [[ -n "$deb_files" ]]; then
        log_info ".deb 패키지 설치 (sudo 필요)"
        # shellcheck disable=SC2086
        sudo apt-get install -y $deb_files
        log_ok "pylon .deb 설치 완료"
    else
        # tar 방식 (/opt/pylon 에 설치)
        log_info "tar 방식 설치: $PYLON_INSTALL_ROOT"
        sudo mkdir -p "$PYLON_INSTALL_ROOT"
        sudo tar -xzf "$tmp_dir"/pylon*linux-x86_64.tar.gz -C "$PYLON_INSTALL_ROOT" --strip-components=1 2>/dev/null || true
        # setup-usb.sh 실행 (USB 카메라용 udev 규칙)
        if [[ -f "$PYLON_INSTALL_ROOT/share/pylon/setup-usb.sh" ]]; then
            sudo bash "$PYLON_INSTALL_ROOT/share/pylon/setup-usb.sh"
        fi
        log_ok "pylon tar 설치 완료"
    fi

    rm -rf "$tmp_dir"
    trap - EXIT
}

# ============================================================
# 3. Blaze Supplementary Package 설치
# ============================================================
install_blaze() {
    if [[ -z "$BLAZE_ARCHIVE" ]]; then
        log_warn "Blaze 패키지 없음 - 스킵"
        return 0
    fi

    log_info "Blaze 패키지 설치..."

    if [[ "$BLAZE_ARCHIVE" == *.deb ]]; then
        sudo apt-get install -y "$BLAZE_ARCHIVE"
    else
        local tmp_dir
        tmp_dir=$(mktemp -d)
        tar -xzf "$BLAZE_ARCHIVE" -C "$tmp_dir"
        # Blaze 패키지는 보통 install.sh 포함
        local install_script
        install_script=$(find "$tmp_dir" -name "install.sh" | head -1)
        if [[ -n "$install_script" ]]; then
            log_info "install.sh 실행"
            sudo bash "$install_script"
        else
            log_warn "Blaze install.sh 없음. 수동 설치 필요: $tmp_dir"
        fi
        rm -rf "$tmp_dir"
    fi

    log_ok "Blaze 패키지 설치 완료"
}

# ============================================================
# 4. 네트워크 튜닝 (GigE Vision 필수)
# ============================================================
tune_network() {
    log_info "GigE 네트워크 튜닝..."

    # 이더넷 인터페이스 자동 감지
    local ifaces
    ifaces=$(ip -o link show | awk -F': ' '/eno|enp|eth/ {print $2}' | cut -d'@' -f1)

    log_info "감지된 이더넷 인터페이스:"
    echo "$ifaces" | while read -r iface; do
        local state mtu
        state=$(cat "/sys/class/net/$iface/operstate" 2>/dev/null || echo "unknown")
        mtu=$(cat "/sys/class/net/$iface/mtu" 2>/dev/null || echo "?")
        echo "    - $iface (state=$state, mtu=$mtu)"
    done

    # 1) Jumbo Frame (MTU 9000) 설정 — 사용자 확인 후
    read -p "  GigE 인터페이스에 Jumbo Frame(MTU 9000)을 설정할까요? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "  대상 인터페이스 이름 입력 (예: enp3s0): " target_iface
        if [[ -n "$target_iface" && -d "/sys/class/net/$target_iface" ]]; then
            sudo ip link set dev "$target_iface" mtu 9000
            log_ok "MTU 9000 설정: $target_iface (재부팅 시 리셋됨, netplan으로 영구화 필요)"
        else
            log_warn "인터페이스 없음: $target_iface"
        fi
    fi

    # 2) UDP 수신 버퍼 증가 (GigE Vision 스트림 드랍 방지)
    log_info "UDP 수신 버퍼 증가 (sysctl)"
    sudo sysctl -w net.core.rmem_max=26214400 >/dev/null
    sudo sysctl -w net.core.rmem_default=26214400 >/dev/null
    log_ok "UDP 버퍼 설정 완료 (재부팅 시 리셋, /etc/sysctl.conf에 추가 권장)"

    # 3) 방화벽 (ufw) GigE Vision Discovery 포트 허용
    if command -v ufw &>/dev/null; then
        if sudo ufw status | grep -q "Status: active"; then
            log_info "ufw 활성 - GigE Vision 포트 허용 (3956 UDP)"
            sudo ufw allow 3956/udp
            log_ok "방화벽 규칙 추가"
        else
            log_info "ufw 비활성 - 방화벽 규칙 스킵"
        fi
    fi
}

# ============================================================
# 5. pypylon Python 래퍼 확인
# ============================================================
check_pypylon() {
    log_info "pypylon Python 래퍼 확인..."

    # venv/binpick 우선 (프로젝트 표준)
    local venv_python="$HOME/3D_printer_automation/.venv/binpick/bin/python"
    if [[ ! -f "$venv_python" ]]; then
        venv_python=$(command -v python3 || true)
    fi

    if [[ -z "$venv_python" ]]; then
        log_warn "Python 인터프리터를 찾을 수 없음"
        return 0
    fi

    if "$venv_python" -c "import pypylon" 2>/dev/null; then
        local version
        version=$("$venv_python" -c "import pypylon; print(pypylon.__version__)" 2>/dev/null || echo "?")
        log_ok "pypylon 설치됨 (version: $version, python: $venv_python)"
    else
        log_warn "pypylon 미설치 - 다음 명령어로 설치:"
        echo "    $venv_python -m pip install pypylon"
    fi
}

# ============================================================
# 6. 설치 검증
# ============================================================
verify_install() {
    log_info "설치 검증..."

    # pylon-config 또는 PylonViewerApp 존재 확인
    if command -v pylon-config &>/dev/null; then
        log_ok "pylon-config: $(pylon-config --version 2>/dev/null || echo '?')"
    elif [[ -f "$PYLON_INSTALL_ROOT/bin/pylon-config" ]]; then
        log_ok "pylon-config: $("$PYLON_INSTALL_ROOT/bin/pylon-config" --version 2>/dev/null || echo '?')"
    else
        log_warn "pylon-config 없음"
    fi

    # IP Configurator 경로
    local ip_cfg
    ip_cfg=$(command -v ipconfigurator || find /opt/pylon -name "ipconfigurator" -executable 2>/dev/null | head -1)
    if [[ -n "$ip_cfg" ]]; then
        log_ok "IP Configurator: $ip_cfg"
        echo "    실행: $ip_cfg"
    else
        log_warn "IP Configurator 없음"
    fi

    # pylon Viewer
    local viewer
    viewer=$(command -v pylonviewer || find /opt/pylon -name "PylonViewerApp*" -executable 2>/dev/null | head -1)
    if [[ -n "$viewer" ]]; then
        log_ok "pylon Viewer: $viewer"
    fi

    check_pypylon
}

# ============================================================
# MAIN
# ============================================================
main() {
    echo "============================================================"
    echo "  Basler pylon + Blaze-112 설치 스크립트"
    echo "  작성: 2026-04-21, 대상: Ubuntu 22.04 x86_64 (비전 PC)"
    echo "============================================================"
    echo

    case "$MODE" in
        --check)
            verify_install
            ;;
        --network)
            tune_network
            ;;
        --pypylon)
            check_pypylon
            ;;
        full|--full|"")
            pre_check
            check_files
            install_pylon
            install_blaze
            tune_network
            verify_install
            echo
            log_ok "설치 완료!"
            echo
            echo "다음 단계:"
            echo "  1. 카메라 2대 GigE 연결 + 전원 (Blaze-112 PoE 또는 12V)"
            echo "  2. IP Configurator로 카메라 IP 할당 (예: 192.168.10.10/11)"
            echo "  3. Smoke test 실행:"
            echo "     python bin_picking/scripts/basler_smoke_test.py"
            ;;
        *)
            echo "사용법: $0 [--check | --network | --pypylon | full]"
            exit 1
            ;;
    esac
}

main
