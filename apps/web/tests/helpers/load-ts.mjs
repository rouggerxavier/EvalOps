// Execute production TS/TSX in node:test without maintaining a JS copy.
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runInThisContext } from "node:vm";
import ts from "typescript";

const root = fileURLToPath(new URL("../../", import.meta.url));
const requireNative = createRequire(import.meta.url);

export function loadTs(relativePath, overrides = {}) {
  const cache = new Map();
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename).exports;
    const module = { exports: {} };
    cache.set(filename, module);
    const compiled = ts.transpileModule(readFileSync(filename, "utf8"), {
      fileName: filename,
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    }).outputText;
    const require = (name) => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (name.startsWith("@/") || name.startsWith(".")) {
        const base = name.startsWith("@/") ? resolve(root, name.slice(2)) : resolve(dirname(filename), name);
        const target = [base, `${base}.ts`, `${base}.tsx`].find((candidate) => existsSync(candidate));
        if (target) return load(target);
      }
      return requireNative(name);
    };
    runInThisContext(`(function(require,module,exports){${compiled}\n})`, { filename })(require, module, module.exports);
    return module.exports;
  }
  return load(resolve(root, relativePath));
}
