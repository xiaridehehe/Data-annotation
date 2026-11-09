from pathlib import Path
p=Path('frontend/vite.config.ts');s=p.read_text()
s=s.replace("  load(id: string) {", """  transform(code: string, id: string) {
    const path = id.split('?')[0].replace(/\\\\/g, '/');
    // Emscripten codec factories are CommonJS, even when imported by the
    // ESM DICOM loader. Keep the original URL so WASM resolution still works.
    if (!/\\/@cornerstonejs\\/codec-[^/]+\\/dist\\/.*\\.js$/.test(path)) return;
    if (!code.includes('module.exports') || /export\\s+default/.test(code)) return;
    return {
      code: `const module = { exports: {} }; const exports = module.exports;\\n${code}\\nexport default module.exports;`,
      map: null,
    };
  },
  load(id: string) {""")
p.write_text(s)
