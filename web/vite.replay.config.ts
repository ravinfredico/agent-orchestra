import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static replay page (M6): `npm run build:replay` writes ../replay/dist, ready for GitHub Pages.
// Relative base so it works under https://<user>.github.io/<repo>/. No API calls, no server.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../replay/dist',
    emptyOutDir: true,
    rollupOptions: { input: 'replay.html' },
  },
})
