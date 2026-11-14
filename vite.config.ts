import { createHash } from 'node:crypto';
import { readdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';

const dist = resolve('public');

export default defineConfig({
  root: 'frontend',
  publicDir: 'static',
  build: {
    outDir: '../public', emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/@zxing/library/')) return 'zxing-decoder';
        },
      },
    },
  },
  plugins: [{
    name: 'kiosk-offline-assets',
    closeBundle() {
      const assets = readdirSync(resolve(dist, 'assets')).sort().map((file) => '/assets/' + file);
      const version = createHash('sha256').update(assets.join('\n')).digest('hex').slice(0, 16);
      writeFileSync(resolve(dist, 'shell-manifest.js'), `self.siteguardShell = ${JSON.stringify({ version, assets })};\n`);
    },
  }],
});
