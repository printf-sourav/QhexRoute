import { defineConfig } from 'vite';

export default defineConfig({
  server: { port: 4321, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { port: 4321, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } },
});
