// Runs the Claude dashboard page in jsdom against a bundle, for tests/test_claude_dashboard.py.
// usage: node page_harness.js <bundle dir> <status> <json list of css selectors> [json list of steps to take in turn]
// a step is params to set, or {click: selector} to click the first match, or {input: [selector, text]} to type into a field.
// env:   CR_JSDOM = path to a jsdom install (the folder named jsdom), CR_D3 = path to d3.min.js (v7)
// status ok serves the bundle's datasets; any other status serves that status for every dataset.
// prints one JSON object: {errors: [...], probe: {selector: {count, text, hidden, own_hidden}}, steps: [probe after each params set]}
// hidden counts a hidden ancestor (a page not showing); own_hidden only the element's own attribute.
const fs = require('fs');
const path = require('path');

const [bundle, status, selectors, steps] = process.argv.slice(2);
const { JSDOM } = require(process.env.CR_JSDOM);

const manifest = JSON.parse(fs.readFileSync(path.join(bundle, 'manifest.json'), 'utf8'));
const page = fs.readFileSync(path.join(bundle, 'files', 'index.html'), 'utf8').replace(/<script src="[^"]*"><\/script>/, '');
const dom = new JSDOM('<!doctype html><body><div id="dash-root">' + page + '</div></body>', { runScripts: 'outside-only', pretendToBeVisual: true });
const { window } = dom;
const errors = [];
window.addEventListener('error', (event) => errors.push(String(event.message)));

const data = {};
manifest.datasets.forEach((entry) => {
  data[entry.id] = status === 'ok'
    ? { status: 'ok', data: JSON.parse(fs.readFileSync(path.join(bundle, entry.file), 'utf8')) }
    : { status, data: null };
});
const watchers = [];
let params = {};
const run = (fn) => { try { fn(); } catch (error) { errors.push(String(error && error.stack || error)); } };
window.dash = {
  data: (id) => data[id] || { status: 'missing', data: null },
  onData: (fn) => { watchers.push(fn); run(fn); },
  params: () => Object.assign({}, params),
  setParams: (set) => {
    params = Object.assign({}, params, set);
    Object.keys(params).forEach((key) => { if (params[key] === null) delete params[key]; });
    watchers.forEach(run);
  },
  resetParams: () => { params = {}; watchers.forEach(run); },
  setLink: () => {},
  colors: ['#4477aa', '#cc6677', '#228833', '#aa3377'],
};
window.SVGElement.prototype.getComputedTextLength = function () { return String(this.textContent).length * 7; };
window.eval(fs.readFileSync(process.env.CR_D3, 'utf8'));
try {
  window.eval(fs.readFileSync(path.join(bundle, 'files', 'dashboard.js'), 'utf8'));
} catch (error) {
  errors.push(String(error && error.stack || error));
}

const look = () => {
  const probe = {};
  JSON.parse(selectors || '[]').forEach((selector) => {
    const found = Array.from(window.document.querySelectorAll(selector));
    probe[selector] = {
      count: found.length,
      text: found.map((el) => el.textContent.trim().replace(/\s+/g, ' ')).join(' | '),
      hidden: found.length > 0 && found.every((el) => el.hidden || !!el.closest('[hidden]')),
      own_hidden: found.length > 0 && found.every((el) => el.hidden),
    };
  });
  return probe;
};
const probe = look();
const act = (step) => {
  if (step.click) run(() => window.document.querySelector(step.click).click());
  else if (step.input) {
    run(() => {
      const field = window.document.querySelector(step.input[0]);
      field.value = step.input[1];
      field.dispatchEvent(new window.Event('input', { bubbles: true }));
    });
  } else window.dash.setParams(step);
};
const after = JSON.parse(steps || '[]').map((step) => { act(step); return look(); });
process.stdout.write(JSON.stringify({ errors, probe, steps: after }));
