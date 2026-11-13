import { defineConfig } from 'vite';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const parserPath = require.resolve('dicom-parser');
const names = Object.keys(require('dicom-parser')).filter(name => name !== 'default');
// dicom-parser ships UMD, including in its module entry. Convert it before
// serving excluded Cornerstone modules, which import both namespace and default.
const parserModule = {
  name: 'dicom-parser-es-module',
  enforce: 'pre' as const,
  resolveId(id: string) { if (id === 'dicom-parser') return '\0dicom-parser-es-module'; },
  transform(code: string, id: string) {
    const path = id.split('?')[0].replace(/\\/g, '/');
    // Emscripten codec factories are CommonJS, even when imported by the
    // ESM DICOM loader. Keep the original URL so WASM resolution still works.
    if (!/\/@cornerstonejs\/codec-[^/]+\/dist\/.*\.js$/.test(path)) return;
    if (!code.includes('module.exports') || /export\s+default/.test(code)) return;
    return {
      code: `const module = { exports: {} }; const exports = module.exports;\n${code}\nexport default module.exports;`,
      map: null,
    };
  },
  load(id: string) {
    if (id !== '\0dicom-parser-es-module') return;
    return `const module = { exports: {} }; const exports = module.exports;\n${readFileSync(parserPath, 'utf8').replace(/require\(["']zlib["']\)/g, '{}')}\nexport default module.exports;\nexport const { ${names.join(', ')} } = module.exports;`;
  },
};
export default defineConfig({
  plugins: [parserModule],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  assetsInclude: ['**/*.wasm'],
  optimizeDeps: { exclude: ['@cornerstonejs/dicom-image-loader', 'dicom-parser'] },
  worker: { format: 'es', plugins: () => [parserModule] },
});
