#!/usr/bin/env bash
# 5/15 (금) 사무실 도착 후 인프라 smoke test (~5분)
# ====================================================
# 본 캡처 진입 전 인프라 sanity 한 번에 확인.
# 통과하면 Phase 3 (P5 시범) 진입 가능.
#
# 검증 항목:
#   1. 환경 (venv 활성화, BASLER_BLAZE_IP)
#   2. 네트워크 (en8 IP / Blaze ping latency)
#   3. 카메라 (--discover 인식)
#   4. 라이브 캡처 (--save 1프레임, valid % 확인)
#   5. auto_label simulate 모드 (코드 무결성)
#
# 사용:
#   cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation
#   bash scripts/friday_smoke_test.sh
#
# 종료 코드:
#   0: 모두 PASS — 본 캡처 진입 OK
#   1: 셋업 문제 — 본 캡처 보류

set -u  # set -e 안 씀 (개별 검사가 실패해도 다른 검사 진행)

# ============================================================
# 색상
# ============================================================
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

# ============================================================
# 카운터
# ============================================================
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass() { echo -e "  ${GREEN}✅ PASS${NC} — $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "  ${RED}❌ FAIL${NC} — $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
warn() { echo -e "  ${YELLOW}⚠️  WARN${NC} — $1"; WARN_COUNT=$((WARN_COUNT + 1)); }
section() { echo -e "\n${BOLD}━━━ $1 ━━━${NC}"; }

# Float 비교 헬퍼 (bc 없어도 python 으로 fallback, macOS는 bc 기본 설치되나 안전망)
flt_lt() {  # flt_lt A B  → A < B 이면 0, 아니면 1
    python3 -c "import sys; sys.exit(0 if float('$1') < float('$2') else 1)" 2>/dev/null
}
flt_gt() {  # flt_gt A B  → A > B 이면 0, 아니면 1
    python3 -c "import sys; sys.exit(0 if float('$1') > float('$2') else 1)" 2>/dev/null
}

# ============================================================
# 0. 작업 디렉토리 확인
# ============================================================
section "0. 작업 디렉토리 확인"

PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
if [[ ! -d "$PROJECT_ROOT/bin_picking" ]]; then
    fail "bin_picking/ 디렉토리 없음. 프로젝트 루트에서 실행하세요"
    echo -e "\n  현재: $(pwd)"
    echo "  예: cd ~/Work/Orinu.ai/3D_printer_automation/3D_printer_automation && bash scripts/friday_smoke_test.sh"
    exit 1
fi
pass "프로젝트 루트: $PROJECT_ROOT"

# ============================================================
# 1. Python 환경
# ============================================================
section "1. Python 환경"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    warn "venv 미활성화 — 'source .venv/binpick/bin/activate' 먼저 실행 권장"
    # 시도해 보기
    if [[ -f "$PROJECT_ROOT/.venv/binpick/bin/activate" ]]; then
        source "$PROJECT_ROOT/.venv/binpick/bin/activate"
        if [[ -n "${VIRTUAL_ENV:-}" ]]; then
            pass "venv 자동 활성화: $VIRTUAL_ENV"
        else
            fail "venv 활성화 실패"
        fi
    else
        fail ".venv/binpick 없음"
    fi
else
    pass "venv 활성화됨: $VIRTUAL_ENV"
fi

# 필수 모듈
for mod in pypylon open3d numpy yaml trimesh; do
    if python -c "import $mod" 2>/dev/null; then
        ver=$(python -c "import $mod; print(getattr($mod, '__version__', '?'))" 2>/dev/null)
        pass "$mod $ver"
    else
        fail "$mod 미설치"
    fi
done

# ============================================================
# 2. 네트워크
# ============================================================
section "2. 네트워크 (en8 ↔ Blaze)"

if [[ -z "${BASLER_BLAZE_IP:-}" ]]; then
    fail "BASLER_BLAZE_IP 환경변수 없음 — 'export BASLER_BLAZE_IP=192.168.20.10' 먼저"
else
    pass "BASLER_BLAZE_IP=$BASLER_BLAZE_IP"
fi

# en8 IP 확인 (macOS)
if command -v ifconfig &> /dev/null; then
    EN8_IP=$(ifconfig en8 2>/dev/null | awk '/inet / {print $2}' | head -1)
    if [[ "$EN8_IP" == "192.168.20.1" ]]; then
        pass "en8 IP: 192.168.20.1 (Wi-Fi 분리 OK)"
    elif [[ -n "$EN8_IP" ]]; then
        warn "en8 IP: $EN8_IP (192.168.20.1 기대)"
    else
        warn "en8 인터페이스 IP 없음 (어댑터 연결 확인)"
    fi
fi

# Blaze ping
if [[ -n "${BASLER_BLAZE_IP:-}" ]]; then
    PING_OUT=$(ping -c 2 -t 2 "$BASLER_BLAZE_IP" 2>&1 | tail -3)
    PING_AVG=$(echo "$PING_OUT" | grep -oE 'avg = [0-9.]+' | awk '{print $3}' | head -1)
    if [[ -z "$PING_AVG" ]]; then
        PING_AVG=$(echo "$PING_OUT" | grep -oE '[0-9.]+/[0-9.]+/[0-9.]+' | awk -F/ '{print $2}' | head -1)
    fi
    if [[ -n "$PING_AVG" ]]; then
        if flt_lt "$PING_AVG" "5.0"; then
            pass "Blaze ping avg ${PING_AVG}ms (Wi-Fi 분리 정상)"
        elif flt_lt "$PING_AVG" "20.0"; then
            warn "Blaze ping avg ${PING_AVG}ms (Wi-Fi 충돌 의심, 5/12 메모리 § 192.168.20/24 참조)"
        else
            warn "Blaze ping avg ${PING_AVG}ms (네트워크 불안정)"
        fi
    else
        fail "Blaze ping 실패 — 카메라 전원 / 케이블 / IP 재확인"
    fi
fi

# ============================================================
# 3. 카메라 인식
# ============================================================
section "3. 카메라 인식 (test_basler_live.py --discover)"

DISCOVER_OUT=$(python bin_picking/tests/test_basler_live.py --discover 2>&1 | tail -20)
if echo "$DISCOVER_OUT" | grep -qE "Blaze|40737830"; then
    pass "Blaze 발견 (S/N 40737830)"
else
    fail "Blaze 미발견"
    echo "$DISCOVER_OUT" | sed 's/^/      /'
fi

# ============================================================
# 4. 1프레임 라이브 캡처
# ============================================================
section "4. 1프레임 라이브 캡처 (--live --save --no-ace2)"

SMOKE_DIR="/tmp/friday_smoke_$(date +%H%M%S)"
mkdir -p "$SMOKE_DIR"

CAPTURE_OUT=$(python bin_picking/tests/test_basler_live.py \
    --live --save --no-ace2 \
    --output "$SMOKE_DIR" 2>&1 | tail -20)

if [[ -f "$SMOKE_DIR/depth.npy" ]]; then
    pass "캡처 성공: $SMOKE_DIR/depth.npy"

    # depth 통계 추출
    STATS=$(python -c "
import numpy as np
import json
from pathlib import Path
d = np.load('$SMOKE_DIR/depth.npy')
valid = d[d > 0]
print(f'shape={d.shape}')
print(f'valid_pct={len(valid) / d.size * 100:.1f}')
if len(valid) > 0:
    print(f'median_mm={np.median(valid):.0f}')
    print(f'unique={len(np.unique(valid))}')
meta = json.loads(Path('$SMOKE_DIR/meta.json').read_text())
print(f'intrinsics_version={meta.get(\"intrinsics_version\", \"?\")}')
print(f'fx={meta.get(\"fx\", \"?\")}')
" 2>&1)
    echo "$STATS" | sed 's/^/      /'

    VALID_PCT=$(echo "$STATS" | grep valid_pct | awk -F= '{print $2}')
    if [[ -n "$VALID_PCT" ]] && flt_gt "$VALID_PCT" "70"; then
        pass "valid % ${VALID_PCT}% > 70% (본 캡처 OK)"
    elif [[ -n "$VALID_PCT" ]] && flt_gt "$VALID_PCT" "50"; then
        warn "valid % ${VALID_PCT}% (50~70%, 거리/조명 조정 권장)"
    else
        fail "valid % ${VALID_PCT:-?}% < 50% (시야 / 거리 / 반사 재점검)"
    fi
else
    fail "캡처 실패 — $SMOKE_DIR/depth.npy 없음"
    echo "$CAPTURE_OUT" | sed 's/^/      /'
fi

# ============================================================
# 5. auto_label simulate 모드
# ============================================================
section "5. auto_label simulate (코드 무결성)"

SIM_OUT=$(python bin_picking/src/labeling/auto_label.py --simulate 2>&1 | tail -3)
if echo "$SIM_OUT" | grep -q "모든 시뮬 검증 PASS"; then
    pass "auto_label 시뮬 PASS (대칭 그룹 + 품질 게이트 + rotation_distance)"
else
    fail "auto_label 시뮬 실패"
    echo "$SIM_OUT" | sed 's/^/      /'
fi

# ============================================================
# 요약
# ============================================================
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}5/15 Smoke Test 요약${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}PASS${NC}: $PASS_COUNT"
echo -e "  ${YELLOW}WARN${NC}: $WARN_COUNT"
echo -e "  ${RED}FAIL${NC}: $FAIL_COUNT"
echo ""

if [[ $FAIL_COUNT -eq 0 ]]; then
    if [[ $WARN_COUNT -eq 0 ]]; then
        echo -e "${GREEN}✅ 모든 검사 PASS — 다음 단계: Phase 2.2 A4 평면 sanity check${NC}"
        echo "   python bin_picking/tests/check_intrinsics_planar.py --capture-and-check"
    else
        echo -e "${YELLOW}⚠️ WARN 있음 — Runbook 트러블슈팅 표 확인 후 본 캡처 진입${NC}"
    fi
    exit 0
else
    echo -e "${RED}❌ FAIL 있음 — 본 캡처 보류, Phase 1 셋업 재점검${NC}"
    echo "   참조: docs/binpicking_friday_runbook_20260515.md § Phase 1"
    exit 1
fi
