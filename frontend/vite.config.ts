import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8085';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // main = 5180 → 8085(기본). develop = scripts/dev_develop.sh 가 VITE_PORT=5181 · VITE_API_TARGET=8086 으로 띄운다
    port: Number(process.env.VITE_PORT ?? 5180),
    proxy: {
      // Local API (프리셋, 파일 업로드, 프린트 제어)
      '/api/v1/local': {
        target: API_TARGET,
        changeOrigin: true,
      },
      // Web API (프린터 모니터링) — /api/v2 라인 MES 도 여기로
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
      '/ws': {
        target: API_TARGET.replace(/^http/, 'ws'),
        ws: true,
      },
    },
  },
})
