// Runs the Claude dashboard page in jsdom against a bundle, for tests/test_claude_dashboard.py.
// usage: node page_harness.js <bundle dir> <status> <json list of css selectors>
// env:   CR_JSDOM = path to a jsdom install (the folder named jsdom), CR_D3 = path to d3.min.js (v7)
// status ok serves the bundle's datasets; any other status serves that status for every dataset.
// prints one JSON object: {errors: [...], probe: {selector: {count, text, hidden}}}
const fs = require('fs');
const path = require('path');

const [bundle, status, selectors] = process.argv.slice(2);
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
window.dash = {
  data: (id) => data[id] || { status: 'missing', data: null },
  onData: (fn) => { try { fn(); } catch (error) { errors.push(String(error && error.stack || error)); } },
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

const probe = {};
JSON.parse(selectors || '[]').forEach((selector) => {
  const found = Array.from(window.document.querySelectorAll(selector));
  probe[selector] = {
    count: found.length,
    text: found.map((el) => el.textContent.trim().replace(/\s+/g, ' ')).join(' | '),
    hidden: found.length > 0 && found.every((el) => el.hidden || !!el.closest('[hidden]')),
  };
});
process.stdout.write(JSON.stringify({ errors, probe }));
