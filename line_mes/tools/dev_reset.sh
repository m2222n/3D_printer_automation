#!/usr/bin/env bash
set -e
# 비번은 git 에 두지 않는다 — 실행 전 export PGPASSWORD=… (개발 DB 사용자 mes)
: "${PGPASSWORD:?PGPASSWORD 를 설정하세요 (개발 DB 비번)}"
DB_URL="${LINE_DSN:-postgresql://mes@127.0.0.1/factory}"

echo "=== 1. DB 재생성 ==="
sudo -u postgres psql -q -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='factory' AND pid <> pg_backend_pid();" > /dev/null
sudo -u postgres dropdb --if-exists --force factory
sudo -u postgres createdb -O mes factory

echo "=== 2. schema.sql 적용 ==="
psql "$DB_URL" -q -f line_mes/schema.sql
psql "$DB_URL" -tAc "SELECT '테이블 ' || count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
psql "$DB_URL" -tAc "SELECT '뷰 ' || count(*) FROM information_schema.views WHERE table_schema='public';"

echo "=== 3. topo_sync --apply ==="
python -m line_mes.topo_sync --apply

echo "=== 4. simulator ==="
python -m line_mes.simulator --minutes 600 --speed 500 --spawn-every 700

echo "=== 결과 ==="
psql "$DB_URL" -c "SELECT node_id, status, count(*) FROM product_state GROUP BY node_id, status ORDER BY 1;"
psql "$DB_URL" -c "SELECT * FROM v_product_display LIMIT 15;"
psql "$DB_URL" -c "SELECT * FROM v_node_status ORDER BY step_order;"
