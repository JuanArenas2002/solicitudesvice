import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El refresh token viaja en cookie SameSite=strict: el proxy mantiene SPA y API en el mismo "site".
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } } },
})
