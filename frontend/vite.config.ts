import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5180,
    proxy: {
      // Local API (프리셋, 파일 업로드, 프린트 제어)
      '/api/v1/local': {
        target: 'http://localhost:8086',
        changeOrigin: true,
      },
      // Web API (프린터 모니터링)
      '/api': {
        target: 'http://localhost:8085',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8085',
        ws: true,
      },
    },
  },
})
