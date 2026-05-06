import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  const frontendApiBase = env.VITE_FRONTEND_API_BASE || '/api';
  const frontendApiProxyTarget = env.VITE_FRONTEND_API_PROXY_TARGET || 'http://127.0.0.1:8001';
  const useLocalApiProxy = frontendApiBase.startsWith('/');
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      hmr: process.env.DISABLE_HMR !== 'true',
      proxy: useLocalApiProxy
        ? {
            '/api': {
              target: frontendApiProxyTarget,
              changeOrigin: true,
            },
          }
        : undefined,
    },
  };
});
