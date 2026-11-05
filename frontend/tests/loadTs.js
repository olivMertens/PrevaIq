// Loads pure TypeScript modules of src/ in node:test, without the Next.js toolchain.
// Relative and "@/" imports between such modules are loaded the same way.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const srcDir = path.resolve(__dirname, '..', 'src');
const loaded = new Map();

function load(name, dir) {
  const filename = path.join(dir, name);
  if (loaded.has(filename)) return loaded.get(filename).exports;
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  const sourceModule = { exports: {} };
  loaded.set(filename, sourceModule);
  const localRequire = (specifier) => {
    if (!specifier.startsWith('.') && !specifier.startsWith('@/')) return require(specifier);
    const target = specifier.startsWith('@/')
      ? path.join(srcDir, specifier.slice(2))
      : path.resolve(path.dirname(filename), specifier);
    return load(`${path.basename(target)}.ts`, path.dirname(target));
  };
  // Same realm as the test, so deepStrictEqual compares plain arrays and objects.
  vm.runInThisContext(`(function (module, exports, require) {${outputText}\n})`, { filename })(
    sourceModule,
    sourceModule.exports,
    localRequire,
  );
  return sourceModule.exports;
}

module.exports = { load, srcDir };
