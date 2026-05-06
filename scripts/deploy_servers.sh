#!/bin/bash
# ============================================================================
# Auto-deploy to 6000 server + Kakao VM
# ============================================================================
# Usage: ./scripts/deploy_servers.sh [--skip-deps] [--skip-build] [--6000-only] [--kakao-only]
#
# What it does:
#   1) 6000 서버: git pull → pip install → npm build → restart formlabs-web
#   2) 카카오 VM: SSH로 동일 작업
#
# 공장 PC는 별도 (AnyDesk 관리자 cmd → deploy.bat 한 줄)
# ============================================================================

set -e

REPO_ROOT="/home/jtm/3D_printer_automation"
KAKAO_KEY="$HOME/.ssh/kakao_key"
KAKAO_HOST="ubuntu@61.109.239.142"
KAKAO_PATH="/home/ubuntu/3D_printer_automation"

SKIP_DEPS=false
SKIP_BUILD=false
DEPLOY_6000=true
DEPLOY_KAKAO=true

for arg in "$@"; do
    case $arg in
        --skip-deps) SKIP_DEPS=true ;;
        --skip-build) SKIP_BUILD=true ;;
        --6000-only) DEPLOY_KAKAO=false ;;
        --kakao-only) DEPLOY_6000=false ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

color_green() { printf "\033[0;32m%s\033[0m\n" "$1"; }
color_red() { printf "\033[0;31m%s\033[0m\n" "$1"; }
color_blue() { printf "\033[0;34m%s\033[0m\n" "$1"; }

# ============================================================================
# 6000 서버 배포 (로컬)
# ============================================================================
deploy_6000() {
    color_blue "=========================================="
    color_blue "  [1/2] 6000 서버 배포 (로컬)"
    color_blue "=========================================="

    cd "$REPO_ROOT"

    echo "→ git pull origin main"
    git pull origin main 2>&1 | tail -5

    if [ "$SKIP_DEPS" = false ]; then
        echo ""
        echo "→ pip install (web-api)"
        ./web-api/venv/bin/pip install -q -r web-api/requirements.txt 2>&1 | tail -3
    fi

    if [ "$SKIP_BUILD" = false ]; then
        echo ""
        echo "→ frontend npm build"
        cd frontend
        npm install --no-audit --no-fund --silent 2>&1 | tail -3
        npm run build 2>&1 | tail -5
        cd ..
    fi

    echo ""
    echo "→ systemctl restart formlabs-web"
    systemctl --user restart formlabs-web
    sleep 3

    echo ""
    echo "→ 검증"
    if systemctl --user is-active formlabs-web > /dev/null; then
        color_green "  ✅ 6000 서버 active"
    else
        color_red "  ❌ 6000 서버 부팅 실패"
        journalctl --user -u formlabs-web --since "10 seconds ago" --no-pager | tail -10
        return 1
    fi

    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8085/api/v1/dashboard)
    if [ "$code" = "401" ]; then
        color_green "  ✅ JWT 인증 활성 (401 expected)"
    elif [ "$code" = "200" ]; then
        color_red "  ⚠️  인증 미설정? (200 응답 — .env 확인)"
    else
        color_red "  ⚠️  예상 외 응답: $code"
    fi
}

# ============================================================================
# 카카오 VM 배포 (SSH)
# ============================================================================
deploy_kakao() {
    color_blue "=========================================="
    color_blue "  [2/2] 카카오 VM 배포 (SSH)"
    color_blue "=========================================="

    if [ ! -f "$KAKAO_KEY" ]; then
        color_red "  ❌ SSH key not found: $KAKAO_KEY"
        return 1
    fi

    local skip_deps=$SKIP_DEPS skip_build=$SKIP_BUILD

    ssh -i "$KAKAO_KEY" "$KAKAO_HOST" bash -s -- "$skip_deps" "$skip_build" "$KAKAO_PATH" << 'REMOTE'
SKIP_DEPS=$1
SKIP_BUILD=$2
KAKAO_PATH=$3

set -e
cd "$KAKAO_PATH"

echo "→ git pull origin main"
git pull origin main 2>&1 | tail -5

if [ "$SKIP_DEPS" = "false" ]; then
    echo ""
    echo "→ pip install (web-api)"
    ./web-api/venv/bin/pip install -q -r web-api/requirements.txt 2>&1 | tail -3
fi

if [ "$SKIP_BUILD" = "false" ]; then
    echo ""
    echo "→ frontend npm build"
    cd frontend
    npm install --no-audit --no-fund --silent 2>&1 | tail -3
    npm run build 2>&1 | tail -5
    cd ..
fi

echo ""
echo "→ systemctl restart formlabs-web"
systemctl --user restart formlabs-web
sleep 3

if systemctl --user is-active formlabs-web > /dev/null; then
    echo "  ✅ 카카오 VM active"
else
    echo "  ❌ 카카오 VM 부팅 실패"
    journalctl --user -u formlabs-web --since "10 seconds ago" --no-pager | tail -10
    exit 1
fi

CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8085/api/v1/dashboard)
if [ "$CODE" = "401" ]; then
    echo "  ✅ JWT 인증 활성 (401 expected)"
elif [ "$CODE" = "200" ]; then
    echo "  ⚠️  인증 미설정? (200 응답)"
else
    echo "  ⚠️  예상 외 응답: $CODE"
fi
REMOTE
}

# ============================================================================
# 외부 접속 검증
# ============================================================================
verify_external() {
    color_blue "=========================================="
    color_blue "  외부 접속 검증"
    color_blue "=========================================="

    if [ "$DEPLOY_6000" = true ]; then
        local code_6000
        code_6000=$(curl -s -o /dev/null -w "%{http_code}" http://106.244.6.242:8085/api/v1/dashboard)
        echo "  6000 서버:    $code_6000 $([ "$code_6000" = "401" ] && echo '✅' || echo '⚠️')"
    fi

    if [ "$DEPLOY_KAKAO" = true ]; then
        local code_kakao
        code_kakao=$(curl -s -o /dev/null -w "%{http_code}" http://61.109.239.142:8085/api/v1/dashboard)
        echo "  카카오 VM:    $code_kakao $([ "$code_kakao" = "401" ] && echo '✅' || echo '⚠️')"
    fi

    local code_factory
    code_factory=$(curl -s -o /dev/null -w "%{http_code}" https://factory.flickdone.com/api/v1/dashboard)
    echo "  공장 PC:      $code_factory $([ "$code_factory" = "401" ] && echo '(이전 배포 상태)' || echo '(미배포 또는 인증 미설정)')"
    echo ""
    echo "  ⚠️  공장 PC는 별도 배포 필요:"
    echo "     AnyDesk → 관리자 cmd:"
    echo "       cd /d D:\\3D_printer_automation_0305\\3D_printer_automation"
    echo "       deploy.bat"
}

# ============================================================================
# 실행
# ============================================================================
START_TIME=$(date +%s)

[ "$DEPLOY_6000" = true ] && deploy_6000
echo ""
[ "$DEPLOY_KAKAO" = true ] && deploy_kakao
echo ""
verify_external

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo ""
color_green "=========================================="
color_green "  완료 (소요: ${DURATION}초)"
color_green "=========================================="
