// Used by test_required.py: runs the real required/visibility functions of journey.js (cut out of the file, so there is
// no copy to drift) on the cases read from stdin, and prints the unmet required questions for every screen of every case.
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const cut = (from, to) => { const a = src.indexOf(from); const b = src.indexOf(to, a); if (a < 0 || b < 0) throw new Error(`markers not found: ${from} / ${to}`); return src.slice(a, b); };
const code = cut('const questions = () =>', 'const screenNumbers = ') + cut('const NEED_TEXT', 'function actionLabel');
const build = new Function('state', 'answers', `let visibleKeys = new Set();\n${code}\nreturn { computeVisible, unmetQuestions, visible: () => [...visibleKeys] };`);
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cases.map(({ state, answers }) => {
  const api = build(state, answers);
  api.computeVisible();
  const result = {};
  state.screens.forEach((s) => { result[s.number] = api.unmetQuestions(s.number).map((q) => q.key).sort(); });
  return { unmet: result, visible: api.visible().sort() };
});
process.stdout.write(JSON.stringify(out));
