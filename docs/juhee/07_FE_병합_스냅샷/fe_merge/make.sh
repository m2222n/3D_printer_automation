#!/usr/bin/env bash
# 기존 FE(데모 모드) 를 그대로 떠서 새 와이어프레임 패널과 합친 단일 HTML 을 만든다.
#   1) web-api/scripts/run_demo.sh 로 데모 백엔드(:8085) 를 먼저 띄운다
#   2) ./docs/juhee/07_FE_병합_스냅샷/fe_merge/make.sh
set -euo pipefail
cd "$(dirname "$0")/../../../.."          # repo root
FE=frontend
NODE_PATH="${NODE_PATH:-/tmp/node_modules}"; export NODE_PATH

curl -sf -o /dev/null http://127.0.0.1:8085/health \
  || { echo "✗ 데모 백엔드(:8085)가 필요합니다 — web-api/scripts/run_demo.sh"; exit 1; }
node -e "require('jsdom')" 2>/dev/null || { echo "✗ jsdom 이 필요합니다 (NODE_PATH 확인)"; exit 1; }

cleanup() { rm -f "$FE/vite.snap.config.ts" "$FE/vite.css.config.ts" "$FE/wf_entry.css"; }
trap cleanup EXIT

# ① jsdom 이 실행할 수 있는 클래식 번들 (기본 ESM 은 jsdom 이 못 읽는다)
cat > "$FE/vite.snap.config.ts" <<'CFG'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: '/tmp/dist-snap', emptyOutDir: true, minify: false,
    rollupOptions: { output: { format: 'iife', inlineDynamicImports: true, entryFileNames: 'app.js', assetFileNames: '[name][extname]' } } },
})
CFG
# ② 기존 FE + 새 패널을 한 번에 훑는 Tailwind CSS
cat > "$FE/wf_entry.css" <<'CSS'
@import "tailwindcss";
@source "./src";
@source "../docs/juhee/07_FE_병합_스냅샷/fe_merge";
CSS
cat > "$FE/vite.css.config.ts" <<'CFG'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins: [tailwindcss()],
  build: { outDir: '/tmp/dist-css', emptyOutDir: true,
    rollupOptions: { input: './wf_entry.css', output: { assetFileNames: 'wf.css' } } },
})
CFG

( cd "$FE" && npx vite build --config vite.snap.config.ts >/dev/null )
echo "① 번들 빌드 완료"
( cd "$FE" && node ../docs/juhee/07_FE_병합_스냅샷/fe_merge/snapshot.js /tmp/fe-snapshot.json )
( cd "$FE" && npx vite build --config vite.css.config.ts >/dev/null )
echo "② CSS 빌드 완료"
python3 docs/juhee/07_FE_병합_스냅샷/fe_merge/topo_extract.py /tmp/wf-topo.json
node docs/juhee/07_FE_병합_스냅샷/fe_merge/build.js
node docs/juhee/07_FE_병합_스냅샷/fe_merge/check_merged.js | tail -3
