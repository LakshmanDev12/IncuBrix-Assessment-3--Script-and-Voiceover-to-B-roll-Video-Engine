import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    react()
  ],
  server: {
    // 👉 React dev server on port 8000, bound to IPv4 so 127.0.0.1:8000 works
    host: '127.0.0.1',
    port: 8000,
    strictPort: true, // fail fast if 8000 is already taken
    proxy: {
      // 👉 All API calls forwarded to FastAPI on 8001
      '/v1': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true
      },
      '/output': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true
      },
      // 👉 Health check endpoints — needed for the Online/Offline badge in the UI
      '/health': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true
      }
    }
  }
})
