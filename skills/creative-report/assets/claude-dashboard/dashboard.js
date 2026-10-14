/* The creative report as a Claude dashboard. Every number comes from a dataset computed by the report script;
   this page only formats, filters by date, sorts and draws it. Values are written as text (textContent, d3 .text()), never as markup. */
(function () {
  const root = document.querySelector('.cr');
  if (!root) return;
  const DASH = '—';
  const NO_ADS = 'n/a (no ad data in this run)';
  const NOT_VIDEO = 'n/a (not a video ad)';
  const FORMAT_NOT_KNOWN = 'n/a (format not known, so not known to be a video ad)';
  const ZERO = 0;
  const ONE = 1;
  const PERCENT_FULL = 100;  // the fixed 0 to 100 scale of a percent axis
  const FIRST_ADS = 5;  // how many ads "Do these first" shows; an arbitrary display cap
  const PAGE_SIZE = 24;  // ads shown per step on the Ads page; an arbitrary display cap
  const PARETO_ROWS = 13;  // ranked ads shown before "Show all"; an arbitrary display cap
  const ID_TAIL = 6;  // digits of the ad id shown after a name two ads share
  const TOP_LINES = 3;  // ads drawn in ink, each in its own line style, and named on the fatigue chart, largest spend first
  const NARROW = 560;  // chart width below which axis titles and end labels give way
  const OK = 'ok';
  // What a reader sees when a source is not there, one short line for each way it can fail.
  const FAILED = {
    error: 'Failed to load',
    connect: 'Could not connect to the data',
    declined: 'Access to the data was declined',
    missing: 'The data source is missing',
  };
  const isFailed = (status) => Object.prototype.hasOwnProperty.call(FAILED, status);
  // Every named format takes its own hue, the same in both themes and on every tab; grey is kept for a format not known.
  const FORMAT_SERIES = ['var(--fmt-1)', 'var(--fmt-2)', 'var(--fmt-3)', 'var(--fmt-4)', 'var(--fmt-5)', 'var(--fmt-6)', 'var(--fmt-7)'];
  // Named ads on the fatigue chart are drawn in ink, told apart by stroke, so they borrow no format's or verdict's colour.
  const HIGHLIGHT = ['', '7 4', '1.5 4'];
  const series = (rank) => FORMAT_SERIES[rank - 1] || 'var(--series-other)';
  // One colour per verdict, the same as its chip, everywhere it is drawn.
  const VERDICT_COLOUR = { scale: 'var(--v-scale-fg)', keep: 'var(--v-keep-fg)', check: 'var(--v-check-fg)', iterate: 'var(--v-iterate-fg)',
    pause: 'var(--v-kill-fg)', 'too-early': 'var(--v-early-fg)', 'cant-judge': 'var(--v-cant-fg)', none: 'var(--series-other)' };
  const FIRST_CLASSES = new Set(['pause', 'iterate', 'check', 'scale']);
  const HOLLOW = new Set(['cant-judge', 'check']); // drawn as rings on the scatter: cant-judge apart from too-early's grey, check apart from scale's blue
  const RANGE_PAGES = new Set(['overview', 'ads', 'ad', 'trends']);

  // ---------- the host's colour scheme: the logo pair follows it (the brand tokens follow it in CSS) ----------
  const scheme = () => root.classList.toggle('cr-dark', /dark/.test(getComputedStyle(root).colorScheme || ''));
  scheme();
  new MutationObserver(scheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-mode', 'class', 'style'] });
  if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', scheme);

  // ---------- data and status ----------
  const get = (id) => dash.data(id);
  const rowsOf = (id) => {
    const r = get(id);
    return r.status === OK && Array.isArray(r.data) ? r.data : [];
  };
  const statusOf = (...ids) => {
    const all = ids.map((id) => get(id).status);
    return all.find(isFailed) || (all.some((s) => s !== OK) ? 'loading' : OK);
  };
  const byKey = (rows, key) => new Map(rows.map((row) => [String(row[key]), row]));
  const fact = (name) => {
    const row = rowsOf('header').find((r) => r.fact === name);
    return row ? String(row.value) : '';
  };

  // ---------- formatting ----------
  const grouped0 = d3.format(',.0f');
  const grouped2 = d3.format(',.2f');
  const currency = () => (/^[A-Z]{3}$/.test(fact('Currency')) ? fact('Currency') : '');
  const money = (v, digits) => {
    const text = (digits ? grouped2 : grouped0)(v);
    const code = currency();
    return code ? code + ' ' + text : text + ' (account currency)';
  };
  const asKind = (kind, v) => {
    if (v === null || v === undefined || Number.isNaN(Number(v))) return 'n/a';
    const n = Number(v);
    if (kind === 'money') return money(n, true);
    if (kind === 'money0') return money(n, false);
    if (kind === 'pct') return n.toFixed(2) + '%';
    if (kind === 'share') return n.toFixed(1) + '%';
    if (kind === 'x') return n.toFixed(2) + 'x';
    if (kind === 'num') return n.toFixed(2);
    if (kind === 'int' || kind === 'count') return grouped0(n);
    return String(v);
  };
  const compact = (n) => d3.format('.3~s')(n).replace('G', 'B');
  const short = (kind, v) => {
    if (kind === 'money' || kind === 'money0') {
      const code = currency();
      const n = Number(v);
      const text = Math.abs(n) >= 10000 ? compact(n) : grouped0(n);
      return code ? code + ' ' + text : text;
    }
    if (kind === 'count' || kind === 'int') return Math.abs(Number(v)) >= 10000 ? compact(Number(v)) : grouped0(Number(v));
    return asKind(kind, v);
  };
  // An axis's ticks in one format: all compact when the top tick needs it, never "10k" beside "8,000".
  // A narrow chart leaves the currency off its ticks (bare) and names it once in the axis title instead.
  const axisFormat = (kind, top, bare) => {
    if (kind !== 'money' && kind !== 'money0' && kind !== 'count' && kind !== 'int') return (t) => short(kind, t);
    const big = Math.abs(top) >= 10000 || (bare && Math.abs(top) >= 1000);
    const code = kind === 'count' || kind === 'int' || bare ? '' : currency();
    return (t) => (code ? code + ' ' : '') + (big ? compact(t) : grouped0(t));
  };
  const KIND = { spend: 'money0', conversion_value: 'money0', tail_spend: 'money0', spend_at_stake: 'money0', cpa: 'money', cpm: 'money',
    roas: 'x', ctr: 'pct', hook_rate: 'pct', hold_rate: 'pct', cum_spend_pct: 'share', cum_basis_pct: 'share', spend_share: 'share',
    setting_pct: 'share', concentration_pct: 'share', head_share_pct: 'share', head_spend_pct: 'share', tail_spend_pct: 'share',
    ads: 'int', rank: 'int', cut: 'int', frequency: 'num' };
  const day = (iso) => new Date(iso + 'T00:00:00Z');
  const dayLabel = d3.utcFormat('%-d %b');
  const dateLabel = d3.utcFormat('%-d %b %Y');
  const reasonOf = (note) => String(note || '').replace(/^n\/a \((.*)\)$/, '$1');
  const SAFE_IMAGE = /^data:image\/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$/;
  const isSafeThumb = (value) => typeof value === 'string' && SAFE_IMAGE.test(value);
  const clip = (text, size) => (text.length > size ? text.slice(0, size - 1) + '…' : text);
  // Ads that share a name get the end of their ad id after it, so two lines or rows can be told apart.
  const distinctNames = (rows) => {
    const seen = d3.rollup(rows, (list) => list.length, (r) => r.short_label);
    return new Map(rows.map((r) => [String(r.ad_id), seen.get(r.short_label) > 1 ? r.short_label + ' (ID …' + String(r.ad_id).slice(-ID_TAIL) + ')' : r.short_label]));
  };

  // ---------- elements ----------
  const make = (tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  };
  const show = (el, text) => {
    el.classList.remove('dash-skeleton');
    el.textContent = text === null || text === undefined || text === '' ? DASH : String(text);
  };
  const wait = (el, status) => {
    el.textContent = DASH;
    el.classList.toggle('dash-skeleton', status === 'loading');
  };
  const failedLine = (el, status) => {
    el.classList.remove('dash-skeleton');
    el.replaceChildren(make('span', 'cr-failed', FAILED[status] || FAILED.error));
  };
  const blank = (el, status) => {
    el.querySelectorAll('svg, .cr-legend, .cr-tip').forEach((n) => n.remove());
    el.replaceChildren();
    el.classList.toggle('dash-skeleton', status === 'loading');
    if (isFailed(status)) failedLine(el, status);
  };
  const blankNote = (el, status) => (isFailed(status) ? failedLine(el, status) : wait(el, status));
  // Long names made of underscore tokens may break after each underscore; a date (digits and hyphens) never breaks.
  const breakable = (text) => {
    const frag = document.createDocumentFragment();
    String(text).split(/(\d[\d-]*-\d+)/).forEach((part, i) => {
      if (i % 2) { frag.append(make('span', 'cr-nowrap', part)); return; }
      part.split('_').forEach((piece, j, all) => {
        if (j) frag.append(document.createElement('wbr'));
        frag.append(document.createTextNode(piece + (j < all.length - 1 ? '_' : '')));
      });
    });
    return frag;
  };
  const marks = (selector, scope) => Array.from((scope || root).querySelectorAll(selector));
  const $ = (selector) => root.querySelector(selector);
  const say = (el, text) => {
    el.hidden = !text;
    el.textContent = text || '';
  };

  // A text mark reads its row by data-where (col=value) or data-row, and its column by data-field.
  const where = (el) => {
    const spec = el.getAttribute('data-where');
    if (!spec) return null;
    return spec.split('&').map((part) => part.split('=').map(decodeURIComponent));
  };
  const rowFor = (el, rows) => {
    const conds = where(el);
    if (conds) return rows.find((row) => conds.every(([col, val]) => String(row[col]) === val));
    const at = el.getAttribute('data-row');
    return at === null ? undefined : rows[Number(at)];
  };
  const fillMarks = (id, format, scope) => {
    const status = statusOf(id);
    const rows = rowsOf(id);
    marks('[data-source="' + id + '"][data-field]', scope).forEach((el) => {
      if (el.closest('table') || el.closest('[data-page="ad"]') && !scope) return;
      if (status !== OK) return isFailed(status) ? failedLine(el, status) : wait(el, status);
      const row = rowFor(el, rows);
      const field = el.getAttribute('data-field');
      const value = row ? row[field] : undefined;
      show(el, format ? format(field, value, row, el) : value);
    });
  };

  // The panel's own empty state, as the HTML report wrote it: why it is empty and how to get the data.
  const emptyState = (panel, holder) => {
    const why = root.querySelector('#' + holder + '-empty');
    const how = root.querySelector('#' + holder + '-how');
    const row = rowsOf('sections').find((r) => r.panel === panel);
    const empty = !!row && row.state !== 'data';
    if (why) { why.hidden = !(empty && row.why); if (empty && row.why) show(why, row.why); }
    if (how) { how.hidden = !(empty && row.how); if (empty && row.how) show(how, 'How to get it: ' + row.how); }
    return empty;
  };

  // ---------- pages and links ----------
  const pages = marks('section.cr-page');
  const tabs = $('#tabs');
  let page = 'overview';
  let backTo = 'ads';
  const draws = [];
  const redraw = () => draws.forEach((fn) => fn());
  const on = (fn) => { draws.push(fn); dash.onData(fn); };
  const visible = (id) => page === id;
  const showPage = (id, link) => {
    if (!pages.some((p) => p.id === id)) return;
    if (id === 'ad' && page !== 'ad') backTo = page;
    page = id;
    pages.forEach((p) => { p.hidden = p.id !== id; });
    // The whole-window note takes the date control's height, so the tab bar does not jump between tabs.
    // Only where the tabs and the control share one row: on a narrow page the control stacks below the tabs and no height is kept.
    const oneRow = $('#range').offsetTop === tabs.offsetTop;
    if (!$('#range').hidden && $('#range').offsetHeight) $('#range-off').style.minHeight = oneRow ? $('#range').offsetHeight + 'px' : '';
    $('#range').hidden = !RANGE_PAGES.has(id);
    $('#range-off').hidden = RANGE_PAGES.has(id);
    marks('a', tabs).forEach((a) => a.setAttribute('aria-current', String(a.getAttribute('data-page') === (id === 'ad' ? 'ads' : id))));
    if (link !== false) dash.setLink(id);
    redraw();
  };
  tabs.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-page]');
    if (!link) return;
    event.preventDefault();
    showPage(link.getAttribute('data-page'));
  });
  const openAd = (id) => {
    if (!id) return;
    dash.setParams({ ad: String(id) });
    showPage('ad');
    root.scrollIntoView({ block: 'start' });
  };
  $('#ad-back').addEventListener('click', () => { dash.setParams({ ad: null }); showPage(backTo === 'ad' ? 'ads' : backTo); });

  // ---------- the chart range: start and end params, set by the date fields or the brush ----------
  const windowDays = () => Array.from(new Set(rowsOf('daily').map((r) => r.day))).sort();
  const range = () => {
    const days = windowDays();
    const p = dash.params();
    const first = days[0] || '';
    const last = days[days.length - 1] || '';
    const iso = (v) => (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) && new Date(v).toISOString().slice(0, 10) === v ? v : null);
    const clamp = (v, fallback) => (v === null ? fallback : v < first ? first : v > last ? last : v);
    let start = clamp(iso(p.start), first);
    let end = clamp(iso(p.end), last);
    if (start > end) [start, end] = [end, start];
    return { first, last, start, end, narrow: !!first && (start !== first || end !== last) };
  };
  const inRange = (iso) => {
    const r = range();
    return !r.first || (iso >= r.start && iso <= r.end);
  };
  const startField = $('#range-start');
  const endField = $('#range-end');
  const setRange = (start, end) => {
    const r = range();
    dash.setParams({ start: start && start !== r.first ? start : null, end: end && end !== r.last ? end : null });
  };
  startField.addEventListener('change', () => {
    if (startField.value && startField.validity.valid && startField.value <= range().end) setRange(startField.value, range().end);
  });
  endField.addEventListener('change', () => {
    if (endField.value && endField.validity.valid && endField.value >= range().start) setRange(range().start, endField.value);
  });
  [startField, endField].forEach((field) => field.addEventListener('blur', () => { field.value = range()[field === startField ? 'start' : 'end']; }));
  $('#range-reset').addEventListener('click', () => dash.setParams({ start: null, end: null }));

  on(function rangeBar() {
    const r = range();
    const status = statusOf('daily');
    [startField, endField].forEach((field) => {
      field.min = r.first;
      field.max = r.last;
      field.disabled = status !== OK || !r.first;
      if (field !== document.activeElement) field.value = field === startField ? r.start : r.end;
    });
    $('#range-reset').hidden = !r.narrow;
    const words = r.narrow ? 'Showing ' + dateLabel(day(r.start)) + ' to ' + dateLabel(day(r.end)) + '.' : r.first ? 'Whole window.' : '';
    marks('[data-range-note]').forEach((el) => { el.textContent = words; });
    const whole = 'Whole window (' + fact('Window') + '), not the selected range.';
    marks('[data-whole]').forEach((el) => { el.hidden = !r.narrow; el.textContent = r.narrow ? whole : ''; });
    if (RANGE_PAGES.has(page)) brush($('#range-brush'), r);
  });

  function brush(box, r) {
    const spend = rowsOf('daily').filter((row) => row.metric === 'spend');
    if (!spend.length) return blank(box, statusOf('daily'));
    const width = Math.max(box.clientWidth, 160);
    const height = 40;
    const bottom = height - 14;
    box.querySelectorAll('svg').forEach((s) => s.remove());
    const svg = d3.select(box).append('svg').attr('width', '100%').attr('viewBox', [0, 0, width, height]).attr('role', 'img')
      .attr('aria-label', 'Spend by day; drag across it to pick the charts’ range');
    const x = d3.scaleUtc([day(r.first), d3.utcDay.offset(day(r.last), 1)], [0, width]);
    const y = d3.scaleLinear([0, d3.max(spend, (row) => row.value) || 1], [bottom, 2]);
    const step = width / Math.max(spend.length, 1);
    svg.append('g').selectAll('rect').data(spend.filter((row) => row.value !== null)).join('rect')
      .attr('x', (row) => x(day(row.day)) + step * 0.12).attr('width', Math.max(1, step * 0.76))
      .attr('y', (row) => y(row.value)).attr('height', (row) => bottom - y(row.value)).attr('rx', 1)
      .attr('fill', (row) => (inRange(row.day) ? 'var(--accent)' : 'var(--series-neutral)')).attr('fill-opacity', (row) => (inRange(row.day) ? 0.7 : 0.3));
    svg.append('text').attr('x', 0).attr('y', height - 2).attr('class', 'cr-brush-end').text(dayLabel(day(r.first)));
    svg.append('text').attr('x', width).attr('y', height - 2).attr('text-anchor', 'end').attr('class', 'cr-brush-end').text(dayLabel(day(r.last)));
    const picker = d3.brushX().extent([[ZERO, ZERO], [width, bottom]]).on('end', (event) => {
      if (!event.sourceEvent) return;
      if (!event.selection) return dash.setParams({ start: null, end: null });
      const [a, b] = event.selection.map((px) => d3.utcDay.round(x.invert(px)));
      const iso = d3.utcFormat('%Y-%m-%d');
      setRange(iso(a), iso(d3.utcDay.offset(b, -1) < a ? a : d3.utcDay.offset(b, -1)));
    });
    const g = svg.append('g').call(picker);
    if (r.narrow) g.call(picker.move, [x(day(r.start)), x(d3.utcDay.offset(day(r.end), 1))]);
  }

  // ---------- tables ----------
  const cellText = (value, note, kind) => {
    if (value === null || value === undefined) {
      const frag = document.createDocumentFragment();
      frag.append(make('span', 'cr-na', 'n/a'));
      if (note) frag.append(make('span', 'cr-sub', reasonOf(note)));
      return frag;
    }
    return document.createTextNode(kind ? asKind(kind, value) : String(value));
  };
  const fillTable = (table, id, cells, keep, list) => {
    const body = table.querySelector('tbody');
    const status = statusOf(id);
    const heads = marks('th[data-field]', table);
    const fields = heads.map((th) => th.getAttribute('data-field'));
    const key = table.getAttribute('data-row-key');
    if (status !== OK) {
      const tr = make('tr');
      const td = make('td', '', DASH);
      td.colSpan = fields.length;
      if (isFailed(status)) failedLine(td, status);
      tr.append(td);
      body.replaceChildren(tr);
      return;
    }
    const shown = list || rowsOf(id).filter((row) => !keep || keep(row));
    if (!shown.length) {
      // A table with no rows is never left to read as "nothing found": say the data was not there.
      const tr = make('tr');
      const td = make('td', 'cr-na', 'n/a (no rows in this data)');
      td.colSpan = fields.length;
      tr.append(td);
      body.replaceChildren(tr);
      return;
    }
    body.replaceChildren(...shown.map((row) => {
      const tr = make('tr');
      tr.dataset.key = String(row[key]);
      if (row.ad_id !== undefined) tr.dataset.ad = String(row.ad_id);
      fields.forEach((field, i) => {
        const td = make('td', heads[i].className);
        td.dataset.label = heads[i].textContent;
        const content = cells[field] ? cells[field](row) : cellText(row[field], row[field + '_note'], KIND[field]);
        td.append(content);
        tr.append(td);
      });
      return tr;
    }));
  };
  marks('#verdict-table, #pareto-table').forEach((table) => table.addEventListener('click', (event) => {
    const tr = event.target.closest('tr[data-ad]');
    if (tr && !event.target.closest('a, button, summary')) openAd(tr.dataset.ad);
  }));

  // ---------- charts ----------
  const tip = (box) => {
    let el = box.querySelector('.cr-tip');
    if (!el) { el = make('div', 'cr-tip'); el.hidden = true; box.append(el); }
    return {
      show(x, y, head, lines, image) {
        const text = make('div', '');
        text.append(make('div', 'cr-tip-head', head), ...lines.map((line) => {
          if (!Array.isArray(line)) return make('div', '', line);
          const row = make('div', 'cr-tip-row');
          const sw = make('span', 'cr-swatch');
          sw.style.background = line[1];
          row.append(sw, document.createTextNode(line[0]));
          return row;
        }));
        if (isSafeThumb(image)) {
          const media = make('div', 'cr-tip-media');
          const img = make('img');
          img.setAttribute('src', image);
          img.alt = '';
          media.append(img, text);
          el.replaceChildren(media);
        } else {
          el.replaceChildren(text);
        }
        el.hidden = false;
        const left = Math.max(0, Math.min(x + 16, box.clientWidth - el.offsetWidth));
        el.style.left = left + 'px';
        el.style.top = Math.max(0, y - el.offsetHeight - 8) + 'px';
      },
      hide() { el.hidden = true; },
    };
  };
  const svgIn = (box, height, minWidth) => {
    const width = Math.max(box.clientWidth, minWidth || 240);
    box.querySelectorAll('svg').forEach((s) => s.remove());
    box.classList.remove('dash-skeleton');
    const svg = d3.select(box).insert('svg', ':first-child').attr('width', minWidth && minWidth > box.clientWidth ? minWidth : '100%')
      .attr('viewBox', [0, 0, width, height]).attr('role', 'img');
    return { svg, width, height };
  };
  const tickWidth = (svg, labels) => {
    const probe = svg.append('text').attr('font-size', null);
    const widest = d3.max(labels, (text) => probe.text(text).node().getComputedTextLength()) || 0;
    probe.remove();
    return widest;
  };
  const cleanAxis = (g) => g.attr('font-size', null).attr('font-family', null);
  // A value axis from zero that ends on a labelled tick, so the top of the chart always says what it is.
  const valueAxis = (top, range) => {
    const y = d3.scaleLinear([0, top || 1], range).nice(5);
    const ticks = y.ticks(5);
    const step = ticks.length > 1 ? ticks[1] - ticks[0] : y.domain()[1];
    if (ticks[ticks.length - 1] < y.domain()[1]) y.domain([0, ticks[ticks.length - 1] + step]);
    return y;
  };
  // Line keys are drawn as a short stroke with the chart's own dash, so a dashed or dotted line has a dashed or dotted key.
  // A kind of 'stroke:<dasharray>' carries a line's exact dash.
  const STROKE_KEYS = { line: '', dash: '5 4', dotted: '1.5 4' };
  const strokeKey = (colour, dash) => {
    const svg = d3.create('svg').attr('class', 'cr-swatch cr-swatch-stroke').attr('viewBox', '0 0 22 8').attr('aria-hidden', 'true');
    svg.append('line').attr('x1', 1).attr('x2', 21).attr('y1', 4).attr('y2', 4).attr('stroke', colour).attr('stroke-width', 2.5)
      .attr('stroke-linecap', dash ? 'butt' : 'round').attr('stroke-dasharray', dash || null);
    return svg.node();
  };
  const legend = (box, items) => {
    let el = box.querySelector('.cr-legend');
    if (!el) { el = make('div', 'cr-legend'); box.append(el); }
    el.replaceChildren(...items.map(([name, colour, kind]) => {
      const item = make('span', '', name);
      const line = kind === true ? 'line' : kind;
      if (typeof line === 'string' && (line in STROKE_KEYS || line.startsWith('stroke:'))) {
        item.prepend(strokeKey(colour, line in STROKE_KEYS ? STROKE_KEYS[line] : line.slice('stroke:'.length)));
        return item;
      }
      const sw = make('span', 'cr-swatch' + (kind === 'dot' ? ' cr-dot' : kind === 'ring' ? ' cr-dot cr-ring' : ''));
      sw.style.background = kind === 'ring' ? 'transparent' : colour;
      if (kind === 'ring') sw.style.borderColor = colour;
      item.prepend(sw);
      return item;
    }));
  };
  const scaleOf = (box, width) => () => box.clientWidth / width;
  const yGrid = (svg, y, left, right, format, count) => svg.append('g').attr('class', 'cr-grid-lines').attr('transform', 'translate(' + left + ',0)')
    .call((g) => cleanAxis(g.call(d3.axisLeft(y).ticks(count || 5).tickSize(-right).tickFormat(format))));
  const yRight = (svg, y, at, format, count) => svg.append('g').attr('class', 'cr-axis cr-axis-right').attr('transform', 'translate(' + at + ',0)')
    .call((g) => cleanAxis(g.call(d3.axisRight(y).ticks(count || 5).tickSize(0).tickPadding(8).tickFormat(format))));
  const xDays = (svg, x, bottom, width) => svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(0,' + bottom + ')')
    .call((g) => cleanAxis(g.call(d3.axisBottom(x).ticks(Math.max(2, Math.floor(width / 110))).tickSizeOuter(0).tickPadding(8).tickFormat(dayLabel))));
  const axisTitle = (svg, x, text, anchor) => svg.append('text').attr('class', 'cr-axis-title').attr('x', x).attr('y', 10)
    .attr('text-anchor', anchor || 'start').text(text);
  const media = () => byKey(rowsOf('ad-media'), 'ad_id');
  const curveMeta = () => {
    const meta = new Map();
    rowsOf('age-curve').forEach((r) => { if (!meta.has(r.metric)) meta.set(r.metric, { name: r.name, kind: r.kind }); });
    return meta;
  };
  const KIND_TO = { money: 'money', x: 'x', pct: 'pct', num: 'num', money0: 'money0', count: 'count' };
  const kindOf = (metric) => (metric === 'spend' ? 'money0' : KIND_TO[(curveMeta().get(metric) || {}).kind] || KIND[metric] || 'num');
  const nameOf = (metric) => (metric === 'spend' ? 'Spend' : (curveMeta().get(metric) || {}).name || metric);
  const dailyKind = (kind) => ({ money: 'money', pct: 'pct', count: 'count', x: 'x', num: 'num' })[kind] || (kind === 'ratio' ? 'x' : 'num');
  const noData = (box) => {
    const r = range();
    box.querySelectorAll('svg, .cr-legend, .cr-tip').forEach((n) => n.remove());
    box.replaceChildren(make('p', 'cr-empty', 'n/a: no data between ' + dateLabel(day(r.start)) + ' and ' + dateLabel(day(r.end))));
  };
  const sayEmpty = (box, text) => {
    box.querySelectorAll('svg, .cr-legend, .cr-tip').forEach((n) => n.remove());
    box.replaceChildren(make('p', 'cr-empty', text));
  };

  // A key number's own days: a filled line with its first and last day named under it.
  function sparkline(box, rows, kind) {
    const status = statusOf('daily');
    if (status !== OK || !rows.length) return blank(box, status);
    const known = rows.filter((r) => r.value !== null);
    if (!known.length) return sayEmpty(box, 'n/a: no data in this range');
    box.querySelectorAll('.cr-empty, .cr-spark-ends').forEach((n) => n.remove());
    const { svg, width, height } = svgIn(box, 48, 120);
    const x = d3.scaleUtc(d3.extent(rows, (r) => day(r.day)), [3, width - 3]);
    const [lo, hi] = d3.extent(known, (r) => r.value);
    const pad = (hi - lo) * 0.1 || Math.abs(hi) * 0.1 || 1;
    const y = d3.scaleLinear([Math.max(0, lo - pad), hi + pad], [height - 3, 4]);
    const defined = (r) => r.value !== null;
    svg.append('path').attr('d', d3.area().defined(defined).x((r) => x(day(r.day))).y0(height).y1((r) => y(r.value))(rows))
      .attr('fill', 'var(--accent-soft)');
    svg.append('path').attr('d', d3.line().defined(defined).x((r) => x(day(r.day))).y((r) => y(r.value))(rows)).attr('fill', 'none')
      .attr('stroke', 'var(--accent)').attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const last = known[known.length - 1];
    svg.append('circle').attr('cx', x(day(last.day))).attr('cy', y(last.value)).attr('r', 3).attr('fill', 'var(--accent)');
    svg.attr('aria-label', rows[0].name + ' by day');
    const first = known[0];
    const ends = make('p', 'cr-spark-ends');
    const end = (r) => { const e = make('span', ''); e.append(make('i', '', dayLabel(day(r.day))), make('b', '', short(kind, r.value))); return e; };
    ends.append(end(first), end(last));
    box.append(ends);
  }

  // The overview's hero: spend bars on the left axis, the chosen measure as a line on the right axis.
  const BAR_HEADROOM = 1.6; // with a line drawn, the bars' axis runs this far past the tallest bar so the line rides above them
  function timeChart(box, rows, spend) {
    const status = statusOf('daily');
    if (status === OK && rows.length && rows.every((r) => r.value === null)) return noData(box);
    if (status !== OK || !rows.length) return blank(box, status);
    box.querySelectorAll('.cr-empty').forEach((n) => n.remove());
    const isSpend = rows[0].metric === 'spend';
    const kind = dailyKind(rows[0].kind);
    const height = 320;
    const bottom = height - 30;
    const topY = 26;
    const { svg, width } = svgIn(box, height);
    const narrow = width < NARROW;
    const yb = valueAxis(d3.max(spend, (r) => r.value) * (isSpend ? ONE : BAR_HEADROOM), [bottom, topY]);
    const ticks = narrow ? 3 : 5;
    const moneyTick = axisFormat('money0', yb.domain()[1], narrow);
    const left = tickWidth(svg, yb.ticks(ticks).map(moneyTick)) + (narrow ? 10 : 14);
    const values = rows.flatMap((r) => [r.value, r.average]).filter((v) => v !== null);
    const y = isSpend ? yb : valueAxis(d3.max(values), [bottom, topY]);
    const lineTick = isSpend ? moneyTick : axisFormat(kind, y.domain()[1], narrow);
    const right = isSpend ? 16 : tickWidth(svg, y.ticks(ticks).map(lineTick)) + (narrow ? 12 : 18);
    const unit = (k) => (narrow && (k === 'money' || k === 'money0') && currency() ? ' (' + currency() + ')' : '');
    const step = (width - left - right - 16) / Math.max(spend.length, 1);
    const x = d3.scaleUtc(d3.extent(spend.length ? spend : rows, (r) => day(r.day)), [left + 10 + step / 2, width - right - 8 - step / 2]);
    yGrid(svg, yb, left, width - left - right, moneyTick, ticks);
    if (!isSpend) yRight(svg, y, width - right, lineTick, ticks);
    xDays(svg, x, bottom, width);
    axisTitle(svg, 0, 'Spend per day' + unit('money0'));
    if (!isSpend) axisTitle(svg, width, rows[0].name + (narrow ? unit(kind) : ' (line)'), 'end');
    svg.append('g').selectAll('rect').data(spend.filter((r) => r.value !== null)).join('rect')
      .attr('x', (r) => x(day(r.day)) - step * 0.36).attr('width', Math.max(1, step * 0.72))
      .attr('y', (r) => yb(r.value)).attr('height', (r) => bottom - yb(r.value)).attr('rx', 2).attr('fill', 'var(--bars)');
    const line = (key) => d3.line().defined((r) => r[key] !== null).x((r) => x(day(r.day))).y((r) => y(r[key]));
    svg.append('path').attr('d', line('average')(rows)).attr('fill', 'none').attr('stroke', 'var(--accent)').attr('stroke-width', 2)
      .attr('stroke-dasharray', '5 4').attr('opacity', 0.7);
    svg.append('path').attr('d', line('value')(rows)).attr('fill', 'none').attr('stroke', 'var(--accent)').attr('stroke-width', 2.75)
      .attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const dot = svg.append('circle').attr('r', 4.5).attr('fill', 'var(--accent)').attr('stroke', 'var(--surface)').attr('stroke-width', 2).attr('opacity', 0);
    const rule = svg.append('line').attr('y1', topY).attr('y2', bottom).attr('stroke', 'var(--text)').attr('stroke-opacity', 0.25).attr('opacity', 0);
    const tooltip = tip(box);
    const spendOf = byKey(spend, 'day');
    const scale = scaleOf(box, width);
    svg.append('rect').attr('x', left).attr('width', width - left - right).attr('height', height).attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const at = x.invert(d3.pointer(event)[0]);
        const row = rows[d3.minIndex(rows, (r) => Math.abs(day(r.day) - at))];
        rule.attr('x1', x(day(row.day))).attr('x2', x(day(row.day))).attr('opacity', 1);
        if (row.value !== null) dot.attr('cx', x(day(row.day))).attr('cy', y(row.value)).attr('opacity', 1);
        else dot.attr('opacity', 0);
        const s = spendOf.get(row.day);
        const lines = isSpend ? [] : [['Spend: ' + (!s || s.value === null ? reasonOf(s ? s.value_note : '') : asKind('money0', s.value)), 'var(--bars)']];
        lines.push([row.name + ': ' + (row.value === null ? reasonOf(row.value_note) : asKind(kind, row.value)), 'var(--accent)'],
          'Rolling average: ' + (row.average === null ? reasonOf(row.average_note) : asKind(kind, row.average)));
        tooltip.show(x(day(row.day)) * scale(), (row.value === null ? bottom : y(row.value)) * scale(), dateLabel(day(row.day)), lines);
      })
      .on('mouseleave', () => { dot.attr('opacity', 0); rule.attr('opacity', 0); tooltip.hide(); });
    legend(box, (isSpend ? [['Spend per day', 'var(--bars)']] : [['Spend per day (left axis)', 'var(--bars)'], [rows[0].name + ' (right axis)', 'var(--accent)', 'line']])
      .concat([['Rolling average', 'var(--accent)', 'dash']]));
    svg.attr('aria-label', isSpend ? 'Spend by day with its rolling average' : 'Spend by day as bars with ' + rows[0].name + ' by day as a line');
  }

  // ---------- ad cards and the ad's image ----------
  const chip = (row) => {
    if (!row || !row.verdict) return cellText(null, row && row.verdict_note);
    return make('span', 'cr-chip cr-v-' + (row.verdict_class || 'none'), row.verdict);
  };
  const GLYPHS = [['catalog', 'cr-g-catalog'], ['collection', 'cr-g-collection'], ['carousel', 'cr-g-carousel'], ['video', 'cr-g-video'], ['image', 'cr-g-image'],
    ['static', 'cr-g-image']];
  const glyph = (format) => {
    const name = String(format || '').toLowerCase();
    const found = GLYPHS.find(([word]) => name.includes(word));
    return make('span', 'cr-glyph ' + (found ? found[1] : 'cr-g-unknown'));
  };
  const formatName = (row) => (row.is_video && !/video/i.test(String(row.format)) ? row.format + ' · video' : row.format);
  const mediaBox = (row, big, small) => {
    if (row && small && isSafeThumb(row.thumb)) {
      const ph = make('div', 'cr-ph');
      const img = make('img', 'cr-thumb');
      img.setAttribute('src', row.thumb);
      img.alt = 'Image of ' + row.short_label;
      img.loading = 'lazy';
      const words = make('div', 'cr-ph-words');
      words.append(make('span', 'cr-ph-format', formatName(row)));
      ph.append(img, words);
      return ph;
    }
    if (row && isSafeThumb(row.thumb)) {
      const box = make('div', 'cr-media');
      const img = make('img');
      img.setAttribute('src', row.thumb);
      img.alt = 'Image of ' + row.short_label;
      img.loading = 'lazy';
      box.append(img);
      if (row.is_video) box.append(make('span', 'cr-play'));
      box.append(make('span', 'cr-fmt', formatName(row)));
      return box;
    }
    // A missing image says why, in a compact strip of its own: never a blank box or a broken image.
    const ph = make('div', 'cr-ph' + (big ? ' cr-ph-big' : ''));
    const words = make('div', 'cr-ph-words');
    words.append(make('span', 'cr-ph-format', row ? formatName(row) : 'Ad'));
    if (big || !row) words.append(make('span', 'cr-ph-note', reasonOf(row ? row.thumb_note : NO_ADS)));
    ph.append(glyph(row && row.format), words);
    return ph;
  };
  const arrow = (r) => {
    if (!r || r.value === null || r.median === null || !r.better) return null;
    const better = r.better === 'higher' ? r.value > r.median : r.value < r.median;
    if (r.value === r.median) return make('span', 'cr-arrow cr-flat', '=');
    return make('span', 'cr-arrow ' + (better ? 'cr-up' : 'cr-down'), better ? '▲' : '▼');
  };
  const CARD_RATES = ['ctr', 'hook_rate', 'frequency'];
  const adCard = (row, verdict, adRows, rates, payback, compactSpend, small) => {
    const card = make('article', 'cr-ad' + (isSafeThumb(row.thumb) && !small ? '' : ' cr-ad-plain'));
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', 'Open ' + row.short_label);
    card.title = row.label;
    card.dataset.ad = row.ad_id;
    if (row.verdict_class) card.dataset.verdict = row.verdict_class;
    const body = make('div', 'cr-ad-body');
    const top = make('div', 'cr-ad-top');
    top.append(chip(row));
    if (row.low_delivery) top.append(make('span', 'cr-flag', 'Low delivery'));
    const title = make('h4', 'cr-ad-title');
    title.append(breakable(row.short_label));
    body.append(top, title);
    const stats = make('p', 'cr-ad-stats');
    const stat = (name, value) => { const s = make('span', '', name); s.prepend(make('b', '', value)); return s; };
    stats.append(stat('Spend', row.spend === null ? 'n/a' : short('money0', row.spend)));
    if (payback && verdict) stats.append(stat(payback.name, verdict[payback.metric] === null || verdict[payback.metric] === undefined ? 'n/a' : asKind(KIND[payback.metric], verdict[payback.metric])));
    if (verdict && verdict.spend_at_stake !== null && verdict.spend_at_stake !== row.spend) stats.append(stat('At stake', short('money0', verdict.spend_at_stake)));
    body.append(stats);
    const strip = make('div', 'cr-mult');
    const head = make('div', 'cr-mult-head');
    head.append(make('span', '', 'Spend by day, peak day'));
    if (row.peak_spend !== null) head.append(make('b', '', short('money0', row.peak_spend)));
    strip.append(head);
    body.append(strip);
    const rateRow = make('div', 'cr-rates');
    if (row.low_delivery) {
      rateRow.append(make('span', 'cr-rates-note', 'Too few impressions to compare its rates with other ads.'));
    } else {
      CARD_RATES.forEach((metric) => {
        const r = rates.get(metric);
        const cell = make('span', 'cr-rate');
        cell.append(make('span', 'cr-rate-name', r ? r.name : nameOf(metric)));
        const value = make('b', r && r.value === null ? 'cr-na' : '', !r ? 'n/a' : r.value === null ? (r.value_note === NOT_VIDEO ? 'not video' : 'n/a') : asKind(KIND[metric] || 'num', r.value));
        if (r && r.value === null) value.title = reasonOf(r.value_note);
        const a = arrow(r);
        if (a) value.append(a);
        cell.append(value);
        rateRow.append(cell);
      });
    }
    body.append(rateRow);
    card.append(mediaBox(row, false, small), body);
    return { card, draw: () => spendStrip(strip, adRows, compactSpend) };
  };
  // One ad's spend by day on the shared date axis; the peak in its head is the dataset's own figure.
  function spendStrip(cell, adRows, scales) {
    cell.querySelectorAll('svg, .cr-mult-na').forEach((n) => n.remove());
    const known = adRows.filter((r) => inRange(r.day) && r.spend !== null);
    if (!known.length) {
      cell.append(make('span', 'cr-mult-na', 'n/a: ' + (adRows.length ? 'no spend recorded in this range' : 'no days in this range')));
      return;
    }
    const width = Math.max(cell.clientWidth, 120);
    const height = 30;
    const svg = d3.select(cell).append('svg').attr('width', '100%').attr('viewBox', [0, 0, width, height]).attr('role', 'img').attr('aria-label', 'Spend by day');
    const x = scales.x.copy().range([1, width - 1]);
    const y = scales.spend.copy().range([height - 1, 2]);
    const step = width / Math.max(scales.days, 1);
    svg.append('line').attr('x1', 0).attr('x2', width).attr('y1', height - 0.5).attr('y2', height - 0.5).attr('stroke', 'var(--divider)');
    svg.selectAll('rect').data(known).join('rect').attr('x', (r) => x(day(r.day)) - step * 0.4).attr('width', Math.max(1.5, step * 0.8))
      .attr('y', (r) => y(r.spend)).attr('height', (r) => Math.max(1, height - 1 - y(r.spend))).attr('rx', 1).attr('fill', 'var(--bars)');
  }
  const stripScales = () => {
    const r = range();
    const rows = rowsOf('ad-daily').filter((row) => inRange(row.day));
    const spends = rows.map((row) => row.spend).filter((v) => v !== null).sort(d3.ascending);
    return { x: d3.scaleUtc([day(r.start || r.first), day(r.end || r.last)], [ZERO, ONE]), days: rows.length ? new Set(rows.map((row) => row.day)).size : 1,
      spend: d3.scaleLinear([0, d3.quantile(spends, 0.98) || 1], [ZERO, ONE]).clamp(true) };
  };
  const paybackMeta = () => {
    const meta = curveMeta().get('payback');
    if (!meta) return null;
    const metric = Object.keys(KIND).find((k) => k === meta.name.toLowerCase().replace(/ /g, '_')) || null;
    return metric ? { metric, name: meta.name } : null;
  };
  const gallery = (box, ids, small) => {
    const status = statusOf('ad-media', 'ad-daily', 'verdicts', 'ad-metrics');
    if (status !== OK) return blank(box, status);
    const media_ = media();
    const verdicts = byKey(rowsOf('verdicts'), 'ad_id');
    const daily = d3.group(rowsOf('ad-daily'), (r) => r.ad_id);
    const rates = d3.group(rowsOf('ad-metrics'), (r) => r.ad_id);
    const scales = stripScales();
    const payback = paybackMeta();
    const cards = ids.filter((id) => media_.has(id)).map((id) => adCard(media_.get(id), verdicts.get(id), daily.get(id) || [],
      byKey(rates.get(id) || [], 'metric'), payback, scales, small));
    if (!cards.length) {
      box.replaceChildren(make('p', 'cr-empty', 'n/a (no ads to show for this choice)'));
      return;
    }
    box.replaceChildren(...cards.map((c) => c.card));
    cards.forEach((c) => c.draw());
  };
  const cardOpen = (event) => {
    const card = event.target.closest('.cr-ad[data-ad]');
    if (!card) return;
    if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    openAd(card.dataset.ad);
  };
  marks('#ad-gallery, #first-ads').forEach((box) => { box.addEventListener('click', cardOpen); box.addEventListener('keydown', cardOpen); });

  // ---------- the panels ----------
  let measure = null;
  let verdictShown = 'all';
  let adsView = 'cards';
  let adsLimit = PAGE_SIZE;
  let adsQuery = '';
  let adsSort = 'stake';
  let fatigueMetric = 'payback';
  let adMetric = 'payback';
  let shareBy = 'format';
  let cumulativeBy = 'roas';
  const MIN_LINE_DAYS = 3; // fewer days with a readable running return than this read as one line, not a chart
  let paretoAll = false;

  const switcher = (box, choices, current, pick) => {
    box.replaceChildren(...choices.map(([key, name, count]) => {
      const button = make('button', '', name);
      if (count !== undefined) button.append(make('span', 'cr-count', count));
      button.type = 'button';
      button.setAttribute('aria-pressed', String(key === current));
      button.addEventListener('click', () => pick(key));
      return button;
    }));
  };

  on(function header() {
    fillMarks('header');
    const completeness = root.querySelector('.cr-completeness');
    const row = rowsOf('header').find((r) => r.fact === 'Completeness');
    // The totals check is a plain fact in the scope strip; the badge shows only when the totals fall short, which a reader must see.
    completeness.classList.toggle('cr-tone-warn', !!row && row.tone === 'warn');
    completeness.hidden = !row || row.tone !== 'warn';
    fillMarks('pareto-cut', (field, value) => (KIND[field] ? asKind(KIND[field], value) : value));
    const cut = rowsOf('pareto-cut')[0];
    if (statusOf('pareto-cut') === OK && !cut) {
      const state = rowsOf('sections').find((r) => r.panel === 'pareto');
      ['takeaway', 'pareto-lead'].forEach((id) => show(root.querySelector('#' + id), (state && state.why) || NO_ADS));
    }
    const unspent = cut && cut.no_spend_ads ? asKind('int', cut.no_spend_ads) + ' of the ' + asKind('int', cut.all_ads) + ' ads in the data had no spend, so '
      + (cut.no_spend_ads === ONE ? 'it is' : 'they are') + ' not ranked.' : '';
    say($('#lead-note'), unspent);
    say($('#no-spend-note'), unspent);
    const note = root.querySelector('#concentration-note');
    if (statusOf('pareto-cut') !== OK) blankNote(note, statusOf('pareto-cut'));
    else show(note, cut ? (cut.concentration_pct_note ? 'Spend in the top ads: ' + reasonOf(cut.concentration_pct_note)
      : 'The top ' + cut.top_n + ' ads by spend take ' + asKind('share', cut.concentration_pct) + ' of all spend (top ' + cut.top_n + ' is an arbitrary default; set your own).') : null);
    say($('#head-of'), cut ? 'of ' + asKind('int', cut.ads) + ' ranked ads (' + asKind('share', cut.ads_pct) + ')' : '');
    say($('#head-basis'), cut ? 'of all ' + cut.basis : '');
    say($('#tail-share'), cut ? (cut.tail_spend_pct === null ? reasonOf(cut.tail_spend_pct_note) : asKind('share', cut.tail_spend_pct) + ' of spend, ' + asKind('int', cut.tail_ads) + ' ads') : '');
    say($('#pareto-setting'), cut ? 'The head is the fewest top-spend ads whose cumulative share of ' + cut.basis + ' reaches ' + asKind('share', cut.setting_pct)
      + ': a common convention, not a rule. Set it from your own account when you rebuild the report.' : '');
  });

  on(function overview() {
    const status = statusOf('kpis');
    const kpisEmpty = emptyState('kpis', 'kpis');
    root.querySelector('#kpis').hidden = kpisEmpty;
    const kpis = byKey(rowsOf('kpis'), 'metric');
    const daily = rowsOf('daily').filter((r) => inRange(r.day));
    // Notes about the key numbers sit in one list under the cards, so the cards stay the same height: a change note every key number
    // shares (no prior period) is said once, and each detail note is said once with the names of the numbers it applies to.
    const notes = new Set(rowsOf('kpis').map((r) => r.change_pct_note));
    const shared = status === OK && notes.size === 1 && rowsOf('kpis').every((r) => r.change_pct === null) ? rowsOf('kpis')[0].change_pct_note : null;
    const changeNote = root.querySelector('#kpis-change-note');
    changeNote.hidden = kpisEmpty || !shared;
    if (shared) show(changeNote, 'Key numbers for the whole window. Change against a prior period: ' + reasonOf(shared) + '.');
    const sharedDetail = new Map();
    if (status === OK) d3.groups(rowsOf('kpis').filter((r) => r.detail && r.value !== null), (r) => r.detail)
      .forEach(([text, list]) => sharedDetail.set(text, list.map((r) => r.name)));
    const detailNote = root.querySelector('#kpis-detail-note');
    detailNote.hidden = kpisEmpty || !sharedDetail.size;
    detailNote.replaceChildren(...Array.from(sharedDetail, ([text, list]) => make('li', '', list.join(', ') + ': ' + text.replace(/^\((.*)\)$/, '$1'))));
    const unknown = status === OK ? rowsOf('kpis').filter((r) => r.value === null) : [];
    const naNote = root.querySelector('#kpis-na');
    naNote.hidden = kpisEmpty || !unknown.length;
    naNote.replaceChildren(...Array.from(d3.group(unknown, (r) => reasonOf(r.value_note)), ([why, list]) => make('li', '', list.map((r) => r.name).join(', ') + ': ' + why)));
    marks('.cr-kpi').forEach((tile) => {
      const row = kpis.get(tile.getAttribute('data-metric'));
      tile.classList.toggle('cr-unknown', !!row && row.value === null);
      tile.hidden = !!row && row.value === null;
      marks('[data-field]', tile).forEach((el) => {
        const field = el.getAttribute('data-field');
        if (field === 'name' || field === 'shown') {
          if (status !== OK) return blankNote(el, status);
          return show(el, row ? row[field] : null);
        }
        const value = row ? row[field] : null;
        el.hidden = status !== OK || value === null || value === undefined || value === '' || (field === 'change_pct_note' && !!shared)
          || (field === 'detail' && sharedDetail.has(value));
        if (el.hidden) return;
        if (field === 'change_pct') {
          el.className = 'cr-kpi-change cr-' + (row.change_tone || 'flat');
          return show(el, (value > 0 ? '+' : '') + Number(value).toFixed(1) + '% vs ' + row.against);
        }
        show(el, value);
      });
      const spark = tile.querySelector('.cr-spark');
      const own = daily.filter((r) => r.metric === tile.getAttribute('data-metric'));
      spark.hidden = !!row && row.value === null;
      if (visible('overview') && !spark.hidden) sparkline(spark, own, own.length ? dailyKind(own[0].kind) : 'num');
    });
    const banner = root.querySelector('#not-in-pull');
    const missing = rowsOf('notes').filter((r) => r.section === 'not-in-pull');
    banner.hidden = !missing.length && detailNote.hidden && naNote.hidden;
    root.querySelector('#not-in-pull-list').replaceChildren(...missing.map((r) => make('li', '', r.text)));

    const chart = root.querySelector('#time-chart');
    const empty = emptyState('time', 'time');
    const names = Array.from(new Map(rowsOf('daily').map((r) => [r.metric, r.name])));
    const payback = nameOf('payback');
    if (!measure || !names.some(([key]) => key === measure)) {
      const preferred = names.find(([, name]) => name === payback) || names.find(([key]) => key !== 'spend') || names[0];
      measure = preferred ? preferred[0] : null;
    }
    switcher(root.querySelector('#time-switch'), names.map(([key, name]) => [key, key === 'spend' ? 'Spend only' : name]), measure, (key) => { measure = key; overview(); });
    chart.hidden = empty;
    if (!empty && visible('overview')) timeChart(chart, daily.filter((r) => r.metric === measure), daily.filter((r) => r.metric === 'spend'));

    const needing = rowsOf('verdicts').filter((r) => FIRST_CLASSES.has(r.verdict_class));
    const first = needing.slice(0, FIRST_ADS).map((r) => r.ad_id);
    say(root.querySelector('#first-more'), needing.length > first.length ? 'Showing ' + asKind('int', first.length) + ' of the ' + asKind('int', needing.length)
      + ' ads to act on; the Ads tab lists them all.' : '');
    root.querySelector('#first').hidden = statusOf('verdicts') === OK && !first.length;
    if (visible('overview')) gallery(root.querySelector('#first-ads'), first);
  });

  dash.onData(function boardTable() {
    const empty = emptyState('board', 'board');
    const table = root.querySelector('#board-table');
    table.hidden = empty;
    const rows = rowsOf('verdict-board').filter((r) => r.ads > 0);
    const most = d3.max(rows, (r) => r.spend_at_stake) || 1;
    fillTable(table, 'verdict-board', {
      verdict: (row) => {
        const frag = document.createDocumentFragment();
        frag.append(chip(row));
        if (row.check) frag.append(make('span', 'cr-sub', 'Check first: ' + row.check));
        return frag;
      },
      spend_at_stake: (row) => {
        if (row.spend_at_stake === null) return cellText(null, row.spend_at_stake_note);
        const cell = make('span', 'cr-barcell');
        const bar = make('span', 'cr-fill');
        bar.style.width = (row.spend_at_stake / most) * PERCENT_FULL + '%';
        bar.style.background = VERDICT_COLOUR[row.verdict_class] || VERDICT_COLOUR.none;
        const track = make('span', 'cr-track');
        track.append(bar);
        cell.append(track, make('span', 'cr-barval', asKind('money0', row.spend_at_stake)));
        return cell;
      },
    }, null, statusOf('verdict-board') === OK ? rows : null);
  });
  root.querySelector('#board-table').addEventListener('click', (event) => {
    const tr = event.target.closest('tr[data-key]');
    if (!tr) return;
    verdictShown = tr.dataset.key;
    adsLimit = PAGE_SIZE;
    showPage('ads');
  });

  // ---------- the ads page ----------
  function scatter(box) {
    const status = statusOf('pareto', 'verdicts', 'kpis');
    if (status !== OK) return blank(box, status);
    const ranked = rowsOf('pareto');
    if (!ranked.length) return sayEmpty(box, 'n/a: ' + (reasonOf((rowsOf('sections').find((r) => r.panel === 'pareto') || {}).why) || 'no ad with spend in this run'));
    box.querySelectorAll('.cr-empty').forEach((n) => n.remove());
    const verdicts = byKey(rowsOf('verdicts'), 'ad_id');
    const pics = media();
    const roas = (rowsOf('kpis').find((r) => r.metric === 'roas') || {}).value;
    const height = 378;
    const strip = 34;
    const axisAt = height - 48;
    const bottom = axisAt - strip;
    const { svg, width } = svgIn(box, height);
    const valued = ranked.filter((r) => r.conversion_value !== null && r.conversion_value > 0);
    // Log domains fitted to the data, with room past the largest dot so it is never cut by the top edge.
    const pad = 1.25;
    const xLo = Math.max(ONE, d3.min(ranked, (r) => r.spend));
    const x = d3.scaleLog([xLo / pad, Math.max(xLo * pad, d3.max(ranked, (r) => r.spend) * pad)], [ZERO, ONE]).clamp(true);
    const [vLo, vHi] = valued.length ? d3.extent(valued, (r) => r.conversion_value) : [ONE, PERCENT_FULL];
    const y = d3.scaleLog([vLo / pad, vHi * pad * pad], [bottom, 22]);
    const lead = (t) => Math.round(t / Math.pow(10, Math.floor(Math.log10(t))));
    const decades = (scale) => {
      const steps = scale.ticks().filter((t) => /^[125]$/.test(String(lead(t))));
      const ones = steps.filter((t) => lead(t) === ONE);
      const found = steps.length > 6 ? (ones.length > 1 ? ones : steps.filter((t) => lead(t) !== 2)) : steps;
      return found.length > 1 ? found : scale.ticks(3);
    };
    const yTick = axisFormat('money0', y.domain()[1]);
    const xTick = axisFormat('money0', x.domain()[1]);
    const left = tickWidth(svg, decades(y).map(yTick)) + 16;
    x.range([left + 10, width - 16]);
    svg.append('g').attr('class', 'cr-grid-lines').attr('transform', 'translate(' + left + ',0)')
      .call((g) => cleanAxis(g.call(d3.axisLeft(y).tickValues(decades(y)).tickSize(-(width - left - 16)).tickFormat(yTick))));
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(0,' + axisAt + ')')
      .call((g) => cleanAxis(g.call(d3.axisBottom(x).tickValues(decades(x)).tickSizeOuter(0).tickPadding(8).tickFormat(xTick))));
    axisTitle(svg, 0, 'Purchase value (' + (currency() || 'account currency') + ', log scale)');
    svg.append('text').attr('class', 'cr-axis-title').attr('x', width - 16).attr('y', height - 4).attr('text-anchor', 'end')
      .text('Spend (' + (currency() || 'account currency') + ', log scale) →');
    svg.append('rect').attr('x', left).attr('y', bottom + 8).attr('width', width - left - 16).attr('height', strip - 12).attr('rx', 4).attr('fill', 'var(--surface-muted)');
    svg.append('text').attr('class', 'cr-axis-title').attr('x', left - 8).attr('y', bottom + 8 + (strip - 12) / 2).attr('dy', '0.35em').attr('text-anchor', 'end').text('None');
    const [x0, x1] = x.domain();
    const from = roas ? Math.max(x0, y.domain()[0] / roas) : ZERO;
    const to = roas ? Math.min(x1, y.domain()[1] / roas) : ZERO;
    if (from < to) {
      svg.append('line').attr('x1', x(from)).attr('y1', y(from * roas)).attr('x2', x(to)).attr('y2', y(to * roas))
        .attr('stroke', 'var(--text-muted)').attr('stroke-dasharray', '5 4').attr('stroke-width', 1.25);
    }
    const size = d3.scaleSqrt([ZERO, d3.max(ranked, (r) => r.spend)], [2.5, width < NARROW ? 9 : 14]);
    const cls = (r) => (verdicts.get(String(r.ad_id)) || {}).verdict_class || 'none';
    // Ads with no value spread down their strip in a fixed scatter so a crowd of them reads as a crowd, not one smear.
    const jitter = new Map(ranked.map((r, i) => [r.ad_id, ((i * 0.618) % ONE - 0.5) * (strip - 18)]));
    const yOf = (r) => (r.conversion_value !== null && r.conversion_value > 0 ? y(r.conversion_value) : bottom + 8 + (strip - 12) / 2 + jitter.get(r.ad_id));
    const ring = (r) => HOLLOW.has(cls(r));
    const dots = svg.append('g').selectAll('circle').data(ranked.slice().reverse()).join('circle').attr('class', 'cr-hit')
      .attr('cx', (r) => x(Math.max(ONE, r.spend))).attr('cy', yOf).attr('r', (r) => size(r.spend))
      .attr('fill', (r) => (ring(r) ? 'transparent' : VERDICT_COLOUR[cls(r)] || VERDICT_COLOUR.none)).attr('fill-opacity', 0.7)
      .attr('stroke', (r) => (ring(r) ? VERDICT_COLOUR[cls(r)] : 'var(--surface)')).attr('stroke-width', (r) => (ring(r) ? 1.75 : 1));
    const tooltip = tip(box);
    const scale = scaleOf(box, width);
    dots.on('mousemove', (event, r) => {
      const v = verdicts.get(String(r.ad_id)) || {};
      tooltip.show(x(Math.max(ONE, r.spend)) * scale(), yOf(r) * scale(), r.short_label, [
        'Spend: ' + asKind('money0', r.spend), 'Purchase value: ' + (r.conversion_value === null ? reasonOf(r.conversion_value_note) : asKind('money0', r.conversion_value)),
        'ROAS: ' + (v.roas === null || v.roas === undefined ? reasonOf(v.roas_note || 'n/a (no value)') : asKind('x', v.roas)),
        [v.verdict || 'No verdict', VERDICT_COLOUR[cls(r)] || VERDICT_COLOUR.none]], (pics.get(String(r.ad_id)) || {}).thumb);
    }).on('mouseleave', () => tooltip.hide()).on('click', (event, r) => openAd(r.ad_id));
    const present = new Set(ranked.map(cls));
    legend(box, rowsOf('verdict-board').filter((b) => present.has(b.verdict_class)).map((b) => [b.verdict, VERDICT_COLOUR[b.verdict_class], HOLLOW.has(b.verdict_class) ? 'ring' : 'dot'])
      .concat(roas ? [['Account ROAS ' + asKind('x', roas) + ' (dashed line)', 'var(--text-muted)', 'dash']] : []));
    svg.attr('aria-label', 'Each ad’s spend against its purchase value, coloured by verdict');
  }

  const SORTS = {
    stake: null,
    spend: (a, b) => d3.descending(a.spend === null ? -Infinity : a.spend, b.spend === null ? -Infinity : b.spend),
    name: (a, b) => d3.ascending(String(a.short_label).toLowerCase(), String(b.short_label).toLowerCase()),
  };
  const adsList = () => {
    const payback = paybackMeta();
    const keep = (row) => (verdictShown === 'all' || row.verdict_class === verdictShown)
      && (!adsQuery || String(row.label).toLowerCase().includes(adsQuery));
    const order = rowsOf('verdicts');
    const known = new Set(order.map((r) => r.ad_id));
    const all = order.concat(verdictShown === 'all' ? rowsOf('ad-media').filter((r) => !known.has(r.ad_id))
      .map((r) => Object.assign({ verdict_class: null }, r)) : []);
    let list = all.filter(keep);
    if (adsSort === 'payback' && payback) {
      const lower = payback.metric === 'cpa';
      const val = (r) => (r[payback.metric] === null || r[payback.metric] === undefined ? null : r[payback.metric]);
      list = list.slice().sort((a, b) => (val(a) === null) - (val(b) === null) || (lower ? d3.ascending(val(a), val(b)) : d3.descending(val(a), val(b))));
    } else if (SORTS[adsSort]) {
      list = list.slice().sort(SORTS[adsSort]);
    }
    return list;
  };

  on(function ads() {
    const board = rowsOf('verdict-board');
    const filter = root.querySelector('#verdict-filter');
    const allEmpty = emptyState('all-ads', 'all-ads');
    const table = root.querySelector('#verdict-table');
    table.hidden = allEmpty;
    root.querySelector('#images-note').hidden = allEmpty;
    root.querySelector('#scatter').hidden = allEmpty;
    const offered = board.filter((r) => r.ads > 0);
    if (verdictShown !== 'all' && !offered.some((r) => r.verdict_class === verdictShown)) verdictShown = 'all';
    filter.hidden = allEmpty || !offered.length;
    const pick = (key) => { verdictShown = key; adsLimit = PAGE_SIZE; ads(); };
    switcher(filter, [['all', 'All ads', asKind('int', rowsOf('ad-media').length)]].concat(offered.map((r) => [r.verdict_class, r.verdict, asKind('int', r.ads)])), verdictShown, pick);
    marks('button', filter).forEach((b, i) => { if (i > 0) b.dataset.verdict = offered[i - 1].verdict_class; });
    marks('button', root.querySelector('#ads-view')).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.view === adsView)));
    root.querySelector('#ads-view').hidden = allEmpty;
    root.querySelector('.cr-tools').hidden = allEmpty;
    const sort = root.querySelector('#ads-sort');
    const payback = paybackMeta();
    sort.querySelector('option[value="payback"]').hidden = !payback;
    if (payback) sort.querySelector('option[value="payback"]').textContent = 'Best ' + payback.name + ' first';
    sort.value = adsSort;
    const galleryBox = root.querySelector('#ad-gallery');
    galleryBox.hidden = allEmpty || adsView !== 'cards';
    root.querySelector('#ad-table-wrap').hidden = allEmpty || adsView !== 'table';
    const list = statusOf('verdicts', 'ad-media') === OK ? adsList() : null;
    const page_ = list ? list.slice(0, adsLimit) : null;
    fillTable(table, 'verdicts', {
      label: (row) => {
        const frag = document.createDocumentFragment();
        frag.append(document.createTextNode(row.short_label));
        if (row.check) frag.append(make('span', 'cr-sub', 'Check first: ' + row.check));
        return frag;
      },
      verdict: chip,
      confidence: (row) => cellText(row.confidence, row.confidence_note),
      next_step: (row) => document.createTextNode(row.next_step || ''),
    }, null, page_ ? page_.filter((r) => r.ad_name !== undefined) : null);
    const more = root.querySelector('#ads-more');
    const count = root.querySelector('#ads-count');
    if (!list || allEmpty) {
      more.hidden = true;
      say(count, '');
    } else {
      more.hidden = list.length <= adsLimit;
      more.textContent = 'Show ' + asKind('int', Math.min(PAGE_SIZE, list.length - adsLimit)) + ' more';
      say(count, list.length ? 'Showing ' + asKind('int', page_.length) + ' of ' + asKind('int', list.length) + ' ads' + (adsQuery ? ' matching “' + adsQuery + '”' : '') + '.'
        : 'No ad matches this choice.');
    }
    if (visible('ads')) {
      scatter(root.querySelector('#scatter-chart'));
      if (!galleryBox.hidden && page_) gallery(galleryBox, page_.map((r) => r.ad_id), true);
    }
  });
  root.querySelector('#ads-view').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-view]');
    if (!button) return;
    adsView = button.dataset.view;
    redraw();
  });
  root.querySelector('#ads-more').addEventListener('click', () => { adsLimit += PAGE_SIZE; redraw(); });
  root.querySelector('#ads-search').addEventListener('input', (event) => { adsQuery = event.target.value.trim().toLowerCase(); adsLimit = PAGE_SIZE; redraw(); });
  root.querySelector('#ads-sort').addEventListener('change', (event) => { adsSort = event.target.value; adsLimit = PAGE_SIZE; redraw(); });

  // ---------- one ad ----------
  const VERSUS = { roas: 'x', cpa: 'money', ctr: 'pct', cpm: 'money', hook_rate: 'pct', hold_rate: 'pct', frequency: 'num' };
  const BASIS = / \((too few [^)]*)\)$/;
  function versus(box, rows) {
    box.replaceChildren();
    const bases = new Set(rows.map((r) => (r.group.match(BASIS) || [])[1] || ''));
    const basis = bases.size === 1 ? Array.from(bases)[0] : '';
    say(root.querySelector('#ad-basis'), basis ? 'Compared with all ads: ' + basis + '.' : '');
    rows.forEach((r) => {
      const kind = VERSUS[r.metric] || KIND_TO[r.kind] || 'num';
      box.append(make('span', 'cr-vs-name', r.name));
      const value = make('span', 'cr-vs-value' + (r.value === null ? ' cr-na' : ''), r.value === null ? reasonOf(r.value_note) : asKind(kind, r.value));
      box.append(value);
      const bar = make('div', 'cr-vs-bar');
      box.append(bar);
      if (r.value_note === NOT_VIDEO) {
        bar.append(make('span', 'cr-mult-na', 'Video rates do not apply to this ad.'));
        return;
      }
      if (r.value_note === FORMAT_NOT_KNOWN) {
        bar.append(make('span', 'cr-mult-na', 'No plays recorded, and the format is not known.'));
        return;
      }
      if (r.median === null) {
        bar.append(make('span', 'cr-mult-na', reasonOf(r.median_note)));
      } else {
        const width = Math.max(bar.clientWidth, 160);
        const height = 34;
        const mid = 12;
        // The scale spans the middle half with room either side; a value past it is pinned to the end with an arrow.
        const spread = (r.p75 - r.p25) || Math.abs(r.median) * 0.5 || 1;
        const lo = r.p25 >= 0 ? Math.max(0, r.p25 - spread) : r.p25 - spread;
        const hi = r.p75 + spread;
        const x = d3.scaleLinear([lo, hi], [8, width - 8]);
        const svg = d3.select(bar).append('svg').attr('width', '100%').attr('viewBox', [0, 0, width, height]).attr('role', 'img')
          .attr('aria-label', r.name + ': this ad against the middle half of ' + r.group);
        svg.append('line').attr('x1', 8).attr('x2', width - 8).attr('y1', mid).attr('y2', mid).attr('stroke', 'var(--divider)').attr('stroke-width', 2);
        svg.append('rect').attr('x', x(r.p25)).attr('width', Math.max(2, x(r.p75) - x(r.p25))).attr('y', mid - 7).attr('height', 14).attr('rx', 3)
          .attr('fill', 'var(--band)');
        svg.append('line').attr('x1', x(r.median)).attr('x2', x(r.median)).attr('y1', mid - 9).attr('y2', mid + 9).attr('stroke', 'var(--accent)').attr('stroke-width', 2.5);
        svg.append('text').attr('class', 'cr-vs-tick').attr('x', x(r.p25)).attr('y', height - 2).attr('text-anchor', 'middle').text(asKind(kind, r.p25));
        svg.append('text').attr('class', 'cr-vs-tick').attr('x', x(r.p75)).attr('y', height - 2).attr('text-anchor', 'middle').text(asKind(kind, r.p75));
        if (r.value !== null) {
          const better = r.better === 'higher' ? r.value >= r.median : r.better === 'lower' ? r.value <= r.median : null;
          const fill = better === null ? 'var(--text-muted)' : better ? 'var(--up-fg)' : 'var(--down-fg)';
          const off = r.value < lo ? -1 : r.value > hi ? 1 : 0;
          const at = off < 0 ? 8 : off > 0 ? width - 8 : x(r.value);
          if (off) {
            svg.append('path').attr('d', d3.symbol(d3.symbolTriangle, 90)()).attr('transform', 'translate(' + at + ',' + mid + ') rotate(' + (off > 0 ? 90 : -90) + ')').attr('fill', fill);
          } else {
            svg.append('circle').attr('cx', at).attr('cy', mid).attr('r', 6).attr('stroke', 'var(--surface)').attr('stroke-width', 2).attr('fill', fill);
          }
        }
      }
      box.append(make('span', 'cr-vs-group', 'Median ' + (r.median === null ? 'n/a' : asKind(kind, r.median)) + ' across ' + (basis ? r.group.replace(BASIS, '') : r.group)
        + (r.median === null ? '' : '; the shaded bar runs from ' + asKind(kind, r.p25) + ' to ' + asKind(kind, r.p75) + '.')));
    });
  }

  const AD_TIME_LAUNCHED = 'The ad’s own line against the median and middle half of the ads launched in the window on the same day since launch (whole window).';
  function adTimeChart(box, rows, curve, metric, launched) {
    const status = statusOf('ad-daily', 'age-curve');
    if (status !== OK) return blank(box, status);
    const shown = rows.filter((r) => inRange(r.day) && r.delivery_day !== null);
    const known = shown.filter((r) => r[metric] !== null);
    if (!known.length) {
      const why = shown.length ? reasonOf(shown[shown.length - 1][metric + '_note']) : 'no delivery days in this range';
      return sayEmpty(box, 'n/a: ' + why);
    }
    box.querySelectorAll('.cr-empty').forEach((n) => n.remove());
    const kind = kindOf(metric);
    const height = 376;
    const axisY = height - 44;
    const gap = 48;
    const spendH = 70;
    const topY = 22;
    const bottom = axisY - spendH - gap;
    const { svg, width } = svgIn(box, height);
    const band = launched ? curve.filter((c) => c.median !== null && c.delivery_day >= d3.min(shown, (r) => r.delivery_day) && c.delivery_day <= d3.max(shown, (r) => r.delivery_day)) : [];
    const dayWord = launched ? 'Day ' : 'Day in window ';
    const narrow = width < NARROW;
    const values = known.map((r) => r[metric]).concat(band.flatMap((c) => [c.p25, c.p75]));
    const y = valueAxis(d3.max(values), [bottom, topY]);
    const yTick = axisFormat(kind, y.domain()[1]);
    const yb = valueAxis(d3.max(shown, (r) => r.spend) || 1, [axisY, axisY - spendH]);
    const sTick = axisFormat('money0', yb.domain()[1]);
    const left = Math.max(tickWidth(svg, y.ticks(5).map(yTick)), tickWidth(svg, yb.ticks(2).map(sTick))) + 14;
    const step = (width - left - 16) / Math.max(shown.length, 1);
    const x = d3.scaleLinear(d3.extent(shown, (r) => r.delivery_day), [left + step / 2, width - 16 - step / 2]);
    if (shown.length === 1) x.domain([shown[0].delivery_day - 1, shown[0].delivery_day + 1]);
    yGrid(svg, y, left, width - left - 16, yTick);
    yGrid(svg, yb, left, width - left - 16, sTick, 2);
    const whole = x.ticks(Math.min(shown.length, Math.max(3, Math.floor(width / (narrow ? 64 : 80))))).filter(Number.isInteger);
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(0,' + axisY + ')')
      .call((g) => cleanAxis(g.call(d3.axisBottom(x).tickValues(whole).tickPadding(8).tickFormat((t) => String(t)))));
    svg.append('text').attr('class', 'cr-axis-title').attr('x', width - 16).attr('y', height - 4).attr('text-anchor', 'end').text(launched ? 'Day since launch →' : 'Day in this window →');
    axisTitle(svg, 0, nameOf(metric));
    svg.append('text').attr('class', 'cr-axis-title').attr('x', 0).attr('y', axisY - spendH - 20).text('Spend per day');
    svg.append('g').selectAll('rect').data(shown.filter((r) => r.spend !== null)).join('rect')
      .attr('x', (r) => x(r.delivery_day) - step * 0.36).attr('width', Math.max(1, step * 0.72)).attr('y', (r) => yb(r.spend))
      .attr('height', (r) => axisY - yb(r.spend)).attr('rx', 2).attr('fill', 'var(--bars)');
    svg.append('path').attr('d', d3.area().x((c) => x(c.delivery_day)).y0((c) => y(c.p25)).y1((c) => y(c.p75))(band)).attr('fill', 'var(--band)');
    svg.append('path').attr('d', d3.line().x((c) => x(c.delivery_day)).y((c) => y(c.median))(band)).attr('fill', 'none')
      .attr('stroke', 'var(--accent)').attr('stroke-width', 2).attr('stroke-dasharray', '5 4');
    svg.append('path').attr('d', d3.line().defined((r) => r[metric] !== null).x((r) => x(r.delivery_day)).y((r) => y(r[metric]))(shown))
      .attr('fill', 'none').attr('stroke', 'var(--text)').attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    svg.append('g').selectAll('circle').data(known).join('circle').attr('cx', (r) => x(r.delivery_day)).attr('cy', (r) => y(r[metric])).attr('r', 3)
      .attr('fill', 'var(--text)');
    const tooltip = tip(box);
    const scale = scaleOf(box, width);
    const curveAt = byKey(curve, 'delivery_day');
    const rule = svg.append('line').attr('y1', topY).attr('y2', axisY).attr('stroke', 'var(--text)').attr('stroke-opacity', 0.25).attr('opacity', 0);
    svg.append('rect').attr('x', left).attr('width', width - left).attr('height', axisY).attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const at = x.invert(d3.pointer(event)[0]);
        const r = shown[d3.minIndex(shown, (s) => Math.abs(s.delivery_day - at))];
        const c = curveAt.get(String(r.delivery_day));
        rule.attr('x1', x(r.delivery_day)).attr('x2', x(r.delivery_day)).attr('opacity', 1);
        tooltip.show(x(r.delivery_day) * scale(), y(r[metric] === null ? 0 : r[metric]) * scale(), dayWord + r.delivery_day + ' · ' + dateLabel(day(r.day)), [
          ['This ad: ' + (r[metric] === null ? reasonOf(r[metric + '_note']) : asKind(kind, r[metric])), 'var(--text)'],
          launched ? ['Median of ads that day: ' + (c && c.median !== null ? asKind(kind, c.median) : reasonOf(c ? c.median_note : 'n/a (no curve)')), 'var(--accent)']
            : 'No launch-day median: this ad was running before the window began',
          ['Spend: ' + (r.spend === null ? reasonOf(r.spend_note) : asKind('money', r.spend)), 'var(--bars)']]);
      })
      .on('mouseleave', () => { rule.attr('opacity', 0); tooltip.hide(); });
    legend(box, [['This ad', 'var(--text)', 'line']].concat(launched ? [['Median of ads on the same day', 'var(--accent)', 'dash'], ['Middle half of ads', 'var(--band)']] : [])
      .concat([['Spend per day', 'var(--bars)']]));
    svg.attr('aria-label', nameOf(metric) + ' of this ad by day of delivery against the account, with its spend by day below');
  }

  on(function ad() {
    const id = dash.params().ad;
    const status = statusOf('ad-media');
    const row = media().get(String(id));
    const holder = root.querySelector('[data-page="ad"]');
    marks('[data-source="ad-media"][data-field]', holder).forEach((el) => {
      if (row) el.setAttribute('data-where', 'ad_id=' + encodeURIComponent(row.ad_id));
    });
    if (status !== OK || !row) {
      marks('[data-source="ad-media"][data-field]', holder).forEach((el) => blankNote(el, status === OK ? 'loading' : status));
      if (status === OK && visible('ad')) show(root.querySelector('#ad-title'), 'Pick an ad from the Ads page to see it here.');
      return;
    }
    fillMarks('ad-media', (field, value, r) => (field === 'reason' && value === null ? reasonOf(r.reason_note) : field === 'ad_id' ? 'Ad ID ' + value
      : field === 'launch_day_note' ? 'Days count from the window’s first day, because this ad was ' + reasonOf(value) + '.' : value), holder);
    root.querySelector('#ad-launch').hidden = !!row.launch_day;
    root.querySelector('#ad-check').hidden = !row.check;
    if (row.check) show(root.querySelector('#ad-check'), 'Check first: ' + row.check);
    const verdict = rowsOf('verdicts').find((r) => r.ad_id === row.ad_id);
    const chips = root.querySelector('#ad-chips');
    chips.replaceChildren(chip(row));
    if (verdict && verdict.confidence) chips.append(make('span', 'cr-conf', 'Confidence: ' + verdict.confidence));
    if (row.low_delivery) chips.append(make('span', 'cr-flag', 'Low delivery'));
    const stats = root.querySelector('#ad-stats');
    const payback = paybackMeta();
    const stat = (name, value) => { const s = make('div', 'cr-dstat'); s.append(make('span', 'cr-dstat-name', name), make('b', '', value)); return s; };
    const items = [['Spend', row.spend === null ? reasonOf(row.spend_note) : asKind('money0', row.spend)]];
    if (verdict && verdict.spend_at_stake !== row.spend) items.push(['Spend at stake', verdict.spend_at_stake === null ? reasonOf(verdict.spend_at_stake_note) : asKind('money0', verdict.spend_at_stake)]);
    if (verdict && payback) items.push([payback.name, verdict[payback.metric] === null ? reasonOf(verdict[payback.metric + '_note']) : asKind(KIND[payback.metric], verdict[payback.metric])]);
    items.push(['Peak day spend', row.peak_spend === null ? reasonOf(row.peak_spend_note) : asKind('money0', row.peak_spend)]);
    stats.replaceChildren(...items.map(([name, value]) => stat(name, value)));
    root.querySelector('#ad-media-box').replaceChildren(mediaBox(row, true));
    root.querySelector('#ad-detail').classList.toggle('cr-detail-plain', !isSafeThumb(row.thumb));
    if (!visible('ad')) return;
    versus(root.querySelector('#ad-versus'), rowsOf('ad-metrics').filter((r) => r.ad_id === row.ad_id));
    const metrics = ['payback', 'hook_rate', 'ctr', 'frequency'].filter((m) => row.is_video !== false || m !== 'hook_rate');
    if (!metrics.includes(adMetric)) adMetric = metrics[0];
    switcher(root.querySelector('#ad-time-switch'), metrics.map((m) => [m, nameOf(m)]), adMetric, (key) => { adMetric = key; ad(); });
    say(root.querySelector('#ad-time-h'), row.launch_day ? 'By day of delivery' : 'By day in this window');
    say(root.querySelector('#ad-time-what'), row.launch_day ? AD_TIME_LAUNCHED
      : 'This ad’s own line by day in this window.');
    adTimeChart(root.querySelector('#ad-time-chart'), rowsOf('ad-daily').filter((r) => r.ad_id === row.ad_id),
      rowsOf('age-curve').filter((c) => c.metric === adMetric), adMetric, !!row.launch_day);
  });

  // ---------- trends ----------
  function fatigueChart(box, metric) {
    const status = statusOf('ad-daily', 'age-curve', 'ad-media');
    const clipped = root.querySelector('#fatigue-clipped');
    if (status !== OK) { say(clipped, ''); return blank(box, status); }
    const launched = new Set(rowsOf('ad-media').filter((m) => m.launch_day).map((m) => m.ad_id));
    const all = rowsOf('ad-daily').filter((r) => launched.has(r.ad_id) && inRange(r.day) && r.delivery_day !== null && r[metric] !== null);
    const curve = rowsOf('age-curve').filter((c) => c.metric === metric && c.median !== null);
    if (!all.length) {
      say(clipped, '');
      return sayEmpty(box, launched.size ? 'n/a: no ad launched in the window has a ' + nameOf(metric) + ' value on a delivery day in this range'
        : 'n/a: no ad launched inside the window, so no day since launch can be read');
    }
    box.querySelectorAll('.cr-empty').forEach((n) => n.remove());
    const kind = kindOf(metric);
    const height = 380;
    const bottom = height - 30;
    const topY = 26;
    const { svg, width } = svgIn(box, height);
    const narrow = width < NARROW;
    // The axis ends where the band ends: past it too few ads remain for a median, so single lines would read as a trend.
    const lastDay = curve.length ? d3.max(curve, (c) => c.delivery_day) : d3.max(all, (r) => r.delivery_day);
    const rows = all.filter((r) => r.delivery_day <= lastDay);
    const beyond = new Set(all.filter((r) => r.delivery_day > lastDay).map((r) => r.ad_id)).size;
    const values = rows.map((r) => r[metric]).sort(d3.ascending);
    const top = Math.max(d3.quantile(values, 0.95) || 0, d3.max(curve, (c) => c.p75) || 0) || 1;
    const y = valueAxis(top, [bottom, topY]);
    const yTick = axisFormat(kind, y.domain()[1]);
    const pics = media();
    const order = rowsOf('ad-media').map((m) => m.ad_id).filter((id) => rows.some((r) => r.ad_id === id));
    const named = order.slice(0, TOP_LINES);
    const colourOf = new Map(named.map((id) => [id, 'var(--heading)']));
    const dashOf = new Map(named.map((id, i) => [id, HIGHLIGHT[i]]));
    const left = tickWidth(svg, y.ticks(5).map(yTick)) + 14;
    const right = 16;
    const x = d3.scaleLinear([1, Math.max(2, lastDay)], [left + 4, width - right]);
    yGrid(svg, y, left, width - left - right, yTick);
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(0,' + bottom + ')')
      .call((g) => cleanAxis(g.call(d3.axisBottom(x).tickValues(x.ticks(Math.max(2, Math.floor(width / 90))).filter(Number.isInteger)).tickPadding(8).tickFormat((t) => 'Day ' + t))));
    axisTitle(svg, 0, nameOf(metric));
    const clipId = 'cr-clip-fatigue';
    svg.append('clipPath').attr('id', clipId).append('rect').attr('x', left).attr('y', topY).attr('width', width - left).attr('height', bottom - topY);
    const plot = svg.append('g').attr('clip-path', 'url(#' + clipId + ')');
    plot.append('path').attr('d', d3.area().x((c) => x(c.delivery_day)).y0((c) => y(c.p25)).y1((c) => y(c.p75))(curve)).attr('fill', 'var(--band)');
    const byAd = d3.group(rows, (r) => r.ad_id);
    const line = d3.line().x((r) => x(r.delivery_day)).y((r) => y(Math.min(r[metric], y.domain()[1])));
    const faint = Array.from(byAd).filter(([id]) => !colourOf.has(id));
    // On a narrow chart every other ad is all but hidden, so the median, its band and the top spenders stay readable.
    const paths = plot.append('g').selectAll('path').data(faint).join('path').attr('d', ([, list]) => line(list))
      .attr('fill', 'none').attr('stroke', 'var(--series-neutral)').attr('stroke-opacity', narrow ? 0.04 : 0.12).attr('stroke-width', 1);
    plot.append('path').attr('d', d3.line().x((c) => x(c.delivery_day)).y((c) => y(c.median))(curve)).attr('fill', 'none')
      .attr('stroke', 'var(--accent)').attr('stroke-width', 3.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const bold = plot.append('g').selectAll('path').data(named.filter((id) => byAd.has(id)).map((id) => [id, byAd.get(id)])).join('path')
      .attr('d', ([, list]) => line(list)).attr('fill', 'none').attr('stroke', ([id]) => colourOf.get(id)).attr('stroke-dasharray', ([id]) => dashOf.get(id)).attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.6).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    // A value above the axis is marked where it leaves the chart, never cut off silently.
    const over = rows.filter((r) => r[metric] > y.domain()[1]);
    svg.append('g').selectAll('path').data(over).join('path').attr('d', d3.symbol(d3.symbolTriangle, 36)())
      .attr('transform', (r) => 'translate(' + x(r.delivery_day) + ',' + (topY - 6) + ')')
      .attr('fill', (r) => colourOf.get(r.ad_id) || 'var(--text-muted)');
    const overAds = new Set(over.map((r) => r.ad_id)).size;
    const overDays = new Set(over.map((r) => r.delivery_day)).size;
    say(clipped, [overAds ? asKind('int', over.length) + ' ad-day' + (over.length === 1 ? '' : 's') + ' above ' + short(kind, y.domain()[1]) + ' (' + asKind('int', overAds) + ' ad'
      + (overAds === 1 ? '' : 's') + '), marked ▲ at the top edge on ' + asKind('int', overDays) + ' day' + (overDays === 1 ? '' : 's')
      + ', where each line runs along the edge.' : '',
      beyond ? beyond + ' ad' + (beyond === 1 ? '' : 's') + ' delivered past day ' + lastDay + ', where too few ads remain for a median; those days are not drawn.' : '']
      .filter(Boolean).join(' '));
    const focus = plot.append('path').attr('fill', 'none').attr('stroke', 'var(--text)').attr('stroke-width', 2.5).attr('opacity', 0);
    const dot = svg.append('circle').attr('r', 4.5).attr('fill', 'var(--text)').attr('stroke', 'var(--surface)').attr('stroke-width', 2).attr('opacity', 0);
    const points = rows.map((r) => [x(r.delivery_day), y(Math.min(r[metric], y.domain()[1]))]);
    const delaunay = d3.Delaunay.from(points);
    const tooltip = tip(box);
    const scale = scaleOf(box, width);
    const curveAt = byKey(rowsOf('age-curve').filter((c) => c.metric === metric), 'delivery_day');
    let hovered = null;
    svg.append('rect').attr('class', 'cr-hit').attr('x', left).attr('width', width - left - right).attr('height', bottom).attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const [mx, my] = d3.pointer(event);
        const r = rows[delaunay.find(mx, my)];
        hovered = r.ad_id;
        paths.attr('stroke-opacity', 0.06);
        bold.attr('stroke-opacity', ([id]) => (id === hovered ? 1 : 0.3));
        focus.attr('d', line(byAd.get(hovered))).attr('stroke', colourOf.get(hovered) || 'var(--text)').attr('opacity', 1);
        dot.attr('cx', x(r.delivery_day)).attr('cy', y(Math.min(r[metric], y.domain()[1]))).attr('opacity', 1);
        const m = pics.get(hovered);
        const c = curveAt.get(String(r.delivery_day));
        tooltip.show(x(r.delivery_day) * scale(), y(Math.min(r[metric], y.domain()[1])) * scale(), m ? m.short_label : hovered, [
          'Day ' + r.delivery_day + ' (' + dayLabel(day(r.day)) + '): ' + asKind(kind, r[metric]),
          'Median that day: ' + (c && c.median !== null ? asKind(kind, c.median) : reasonOf(c ? c.median_note : '')),
          m && m.verdict ? 'Verdict: ' + m.verdict : 'No verdict', 'Click to open this ad'], m && m.thumb);
      })
      .on('mouseleave', () => {
        hovered = null;
        paths.attr('stroke-opacity', narrow ? 0.04 : 0.12);
        bold.attr('stroke-opacity', 0.6);
        focus.attr('opacity', 0);
        dot.attr('opacity', 0);
        tooltip.hide();
      })
      .on('click', () => openAd(hovered));
    const names = distinctNames(named.map((id) => pics.get(id) || { ad_id: id, short_label: id }));
    legend(box, [['Median of ads on that day', 'var(--accent)', 'line'], ['Middle half of ads', 'var(--band)']]
      .concat(named.filter((id) => byAd.has(id)).map((id) => [names.get(id), colourOf.get(id), 'stroke:' + (dashOf.get(id) || '')]))
      .concat([['Every other ad', 'var(--series-other)', 'line']]));
    svg.attr('aria-label', nameOf(metric) + ' by day of delivery for each ad launched in the window, with the account median');
  }

  function shareChart(box, dimension) {
    const status = statusOf('share-daily');
    if (status !== OK) return blank(box, status);
    const rows = rowsOf('share-daily').filter((r) => r.dimension === dimension && inRange(r.day));
    if (!rows.length) return sayEmpty(box, 'n/a: no day with spend in this range');
    box.querySelectorAll('.cr-empty').forEach((n) => n.remove());
    const groups = Array.from(new Map(rows.map((r) => [r.group, r])).values()).sort((a, b) => a.rank - b.rank);
    const colour = (g) => (dimension === 'verdict' ? VERDICT_COLOUR[g.group] || VERDICT_COLOUR.none : g.group === 'unknown' ? 'var(--series-other)' : series(g.rank));
    const days = Array.from(d3.group(rows, (r) => r.day), ([d, list]) => Object.assign({ day: d }, Object.fromEntries(list.map((r) => [r.group, r.share_pct]))))
      .sort((a, b) => d3.ascending(a.day, b.day));
    const height = 280;
    const bottom = height - 30;
    const { svg, width } = svgIn(box, height);
    const y = d3.scaleLinear([ZERO, PERCENT_FULL], [bottom, 12]);
    const left = tickWidth(svg, ['100%']) + 14;
    const x = d3.scaleUtc(d3.extent(days, (d) => day(d.day)), [left, width - 12]);
    yGrid(svg, y, left, width - left - 12, (t) => t + '%');
    xDays(svg, x, bottom, width);
    const stack = d3.stack().keys(groups.map((g) => g.group)).value((d, key) => d[key] || 0)(days);
    svg.append('g').selectAll('path').data(stack).join('path')
      .attr('d', d3.area().x((p) => x(day(p.data.day))).y0((p) => y(p[0])).y1((p) => y(p[1])))
      .attr('fill', (s) => colour(groups.find((g) => g.group === s.key))).attr('fill-opacity', 0.9)
      .attr('stroke', 'var(--surface)').attr('stroke-width', 0.75);
    const rule = svg.append('line').attr('y1', 12).attr('y2', bottom).attr('stroke', 'var(--text)').attr('stroke-width', 1).attr('opacity', 0);
    const tooltip = tip(box);
    const scale = scaleOf(box, width);
    const byDay = d3.group(rows, (r) => r.day);
    svg.append('rect').attr('x', left).attr('width', width - left).attr('height', height).attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const at = x.invert(d3.pointer(event)[0]);
        const d = days[d3.minIndex(days, (p) => Math.abs(day(p.day) - at))];
        rule.attr('x1', x(day(d.day))).attr('x2', x(day(d.day))).attr('opacity', 0.4);
        const list = (byDay.get(d.day) || []).filter((r) => r.spend > 0).sort((a, b) => b.share_pct - a.share_pct);
        tooltip.show(x(day(d.day)) * scale(), 40 * scale(), dateLabel(day(d.day)),
          list.map((r) => [r.name + ': ' + asKind('share', r.share_pct) + ' (' + short('money0', r.spend) + ')', colour(r)]));
      })
      .on('mouseleave', () => { rule.attr('opacity', 0); tooltip.hide(); });
    legend(box, groups.map((g) => [g.name, colour(g)]));
    svg.attr('aria-label', 'Share of each day’s spend by ' + dimension);
  }

  function cumulativeChart(box, mode) {
    const status = statusOf('cumulative');
    if (status !== OK) return blank(box, status);
    const rows = rowsOf('cumulative').filter((r) => inRange(r.day));
    if (!rows.length || rows.every((r) => r.spend === null)) return noData(box);
    box.querySelectorAll('.cr-empty').forEach((n) => n.remove());
    const height = 280;
    const bottom = height - 30;
    const topY = 24;
    const { svg, width } = svgIn(box, height);
    const last = rows[rows.length - 1];
    const tooltip = tip(box);
    const scale = scaleOf(box, width);
    if (mode === 'roas') {
      const known = rows.filter((r) => r.cum_roas !== null);
      if (!known.length) return sayEmpty(box, 'n/a: ' + reasonOf(last.cum_roas_note));
      if (known.length < MIN_LINE_DAYS) {
        const end = known[known.length - 1];
        return sayEmpty(box, 'Return on spend so far: ' + asKind('x', end.cum_roas) + ' on ' + dateLabel(day(end.day)) + '. Too few days with a readable value to draw a line.');
      }
      const y = valueAxis(Math.max(d3.max(known, (r) => r.cum_roas), ONE), [bottom, topY]);
      const tick = axisFormat('x', y.domain()[1]);
      const left = tickWidth(svg, y.ticks(5).map(tick)) + 14;
      const endLabel = last.cum_roas === null ? 'n/a' : asKind('x', last.cum_roas);
      const right = tickWidth(svg, [endLabel]) + 22;
      const x = d3.scaleUtc(d3.extent(rows, (r) => day(r.day)), [left + 4, width - right]);
      yGrid(svg, y, left, width - left - right, tick);
      xDays(svg, x, bottom, width);
      axisTitle(svg, 0, 'Return on spend so far');
      svg.append('line').attr('x1', left).attr('x2', width - right).attr('y1', y(ONE)).attr('y2', y(ONE)).attr('stroke', 'var(--text-muted)').attr('stroke-dasharray', '4 4');
      svg.append('text').attr('class', 'cr-axis-title').attr('x', width - right).attr('y', y(ONE) - 6).attr('text-anchor', 'end').text('Break-even ' + asKind('x', ONE));
      svg.append('path').attr('d', d3.area().defined((r) => r.cum_roas !== null).x((r) => x(day(r.day))).y0(bottom).y1((r) => y(r.cum_roas))(rows)).attr('fill', 'var(--accent-soft)');
      svg.append('path').attr('d', d3.line().defined((r) => r.cum_roas !== null).x((r) => x(day(r.day))).y((r) => y(r.cum_roas))(rows))
        .attr('fill', 'none').attr('stroke', 'var(--accent)').attr('stroke-width', 2.75).attr('stroke-linejoin', 'round');
      if (last.cum_roas !== null) svg.append('text').attr('class', 'cr-end-label').attr('x', x(day(last.day)) + 8).attr('y', y(last.cum_roas)).attr('dy', '0.35em').text(endLabel);
      const dot = svg.append('circle').attr('r', 4).attr('fill', 'var(--accent)').attr('stroke', 'var(--surface)').attr('stroke-width', 2).attr('opacity', 0);
      svg.append('rect').attr('x', left).attr('width', width - left - right).attr('height', height).attr('fill', 'transparent')
        .on('mousemove', (event) => {
          const at = x.invert(d3.pointer(event)[0]);
          const r = rows[d3.minIndex(rows, (p) => Math.abs(day(p.day) - at))];
          if (r.cum_roas !== null) dot.attr('cx', x(day(r.day))).attr('cy', y(r.cum_roas)).attr('opacity', 1); else dot.attr('opacity', 0);
          tooltip.show(x(day(r.day)) * scale(), (r.cum_roas === null ? bottom : y(r.cum_roas)) * scale(), dateLabel(day(r.day)), [
            ['Return on spend so far: ' + (r.cum_roas === null ? reasonOf(r.cum_roas_note) : asKind('x', r.cum_roas)), 'var(--accent)'],
            'Spend on ad-days with a readable return: ' + asKind('money0', r.cum_spend), 'Purchase value so far: ' + (r.cum_value === null ? reasonOf(r.cum_value_note) : asKind('money0', r.cum_value))]);
        })
        .on('mouseleave', () => { dot.attr('opacity', 0); tooltip.hide(); });
      legend(box, [['Return on spend so far', 'var(--accent)', 'line'], ['Break-even', 'var(--text-muted)', 'dash']]);
      svg.attr('aria-label', 'Return on spend summed from the first day');
      return;
    }
    if (rows.every((r) => r.cum_spend === null)) return sayEmpty(box, 'n/a: ' + reasonOf(last.cum_spend_note));
    const top = d3.max(rows, (r) => Math.max(r.cum_spend || 0, r.cum_value || 0)) || 1;
    const y = valueAxis(top, [bottom, topY]);
    const tick = axisFormat('money0', y.domain()[1]);
    const left = tickWidth(svg, y.ticks(5).map(tick)) + 14;
    const x = d3.scaleUtc(d3.extent(rows, (r) => day(r.day)), [left + 4, width - 16]);
    yGrid(svg, y, left, width - left - 16, tick);
    xDays(svg, x, bottom, width);
    axisTitle(svg, 0, 'Summed from the first day');
    const lines = [['cum_spend', 'Spend on ad-days with a readable return', 'var(--series-1)'], ['cum_value', 'Purchase value so far', 'var(--series-2)']];
    lines.forEach(([key, , colour]) => {
      svg.append('path').attr('d', d3.line().defined((r) => r[key] !== null).x((r) => x(day(r.day))).y((r) => y(r[key]))(rows))
        .attr('fill', 'none').attr('stroke', colour).attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    });
    const dots = lines.map(([, , colour]) => svg.append('circle').attr('r', 4).attr('fill', colour).attr('stroke', 'var(--surface)').attr('stroke-width', 2).attr('opacity', 0));
    svg.append('rect').attr('x', left).attr('width', width - left).attr('height', height).attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const at = x.invert(d3.pointer(event)[0]);
        const r = rows[d3.minIndex(rows, (p) => Math.abs(day(p.day) - at))];
        lines.forEach(([key], i) => {
          if (r[key] === null) dots[i].attr('opacity', 0);
          else dots[i].attr('cx', x(day(r.day))).attr('cy', y(r[key])).attr('opacity', 1);
        });
        tooltip.show(x(day(r.day)) * scale(), y(r.cum_spend) * scale(), dateLabel(day(r.day)), [
          ['Spend on ad-days with a readable return: ' + asKind('money0', r.cum_spend), 'var(--series-1)'],
          ['Purchase value so far: ' + (r.cum_value === null ? reasonOf(r.cum_value_note) : asKind('money0', r.cum_value)), 'var(--series-2)'],
          'Return on spend so far: ' + (r.cum_roas === null ? reasonOf(r.cum_roas_note) : asKind('x', r.cum_roas))]);
      })
      .on('mouseleave', () => { dots.forEach((d) => d.attr('opacity', 0)); tooltip.hide(); });
    legend(box, lines.map(([, name, colour]) => [name, colour, 'line']));
    svg.attr('aria-label', 'Spend and purchase value summed by day');
  }

  on(function trends() {
    if (!visible('trends')) return;
    const choices = ['payback', 'hook_rate', 'ctr', 'frequency'].map((m) => [m, nameOf(m)]);
    switcher(root.querySelector('#fatigue-switch'), choices, fatigueMetric, (key) => { fatigueMetric = key; trends(); });
    fatigueChart(root.querySelector('#fatigue-chart'), fatigueMetric);
    marks('button', root.querySelector('#share-switch')).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.dimension === shareBy)));
    shareChart(root.querySelector('#share-chart'), shareBy);
    marks('button', root.querySelector('#cumulative-switch')).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.cumulative === cumulativeBy)));
    cumulativeChart(root.querySelector('#cumulative-chart'), cumulativeBy);
    const inRangeRows = statusOf('cumulative') === OK ? rowsOf('cumulative').filter((r) => inRange(r.day)) : [];
    say($('#cumulative-basis'), inRangeRows.length ? inRangeRows[inRangeRows.length - 1].basis_note : '');
  });
  root.querySelector('#share-switch').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-dimension]');
    if (!button) return;
    shareBy = button.dataset.dimension;
    redraw();
  });
  root.querySelector('#cumulative-switch').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-cumulative]');
    if (!button) return;
    cumulativeBy = button.dataset.cumulative;
    redraw();
  });

  // ---------- pareto, format, white space, briefing, method ----------
  function paretoChart(box, rows, cut) {
    const status = statusOf('pareto', 'pareto-cut');
    if (status !== OK || !rows.length) return blank(box, status);
    const height = 330;
    const bottom = height - 46;
    const topY = 26;
    const { svg, width } = svgIn(box, height);
    const narrow = width < NARROW;
    const yMoney = valueAxis(d3.max(rows, (r) => r.spend) * 1.08, [bottom, topY]);
    const moneyTick = axisFormat('money0', yMoney.domain()[1]);
    const moneyTicks = narrow ? 3 : 5;
    const left = tickWidth(svg, yMoney.ticks(moneyTicks).map(moneyTick)) + (narrow ? 10 : 14);
    const right = tickWidth(svg, ['100%']) + 16;
    const x = d3.scaleBand(rows.map((r) => String(r.rank)), [left, width - right]).padding(rows.length > 60 ? 0.05 : 0.2);
    const rankStep = Math.max(ONE, Math.ceil(rows.length / Math.max(2, Math.floor((width - left - right) / 70))));
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(0,' + bottom + ')')
      .call((g) => cleanAxis(g.call(d3.axisBottom(x).tickValues(rows.filter((r) => r.rank === ONE || r.rank % rankStep === ZERO).map((r) => String(r.rank)))
        .tickSizeOuter(0).tickPadding(6))));
    svg.append('text').attr('class', 'cr-axis-title').attr('x', width - right).attr('y', height - 2).attr('text-anchor', 'end').text('Ads ranked by spend →');
    const yPct = d3.scaleLinear([ZERO, PERCENT_FULL], [bottom, topY]);
    svg.append('g').attr('class', 'cr-grid-lines').attr('transform', 'translate(' + left + ',0)')
      .call((g) => cleanAxis(g.call(d3.axisLeft(yPct).ticks(5).tickSize(-(width - left - right)).tickFormat(''))));
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(' + left + ',0)')
      .call((g) => cleanAxis(g.call(d3.axisLeft(yMoney).ticks(moneyTicks).tickSize(0).tickPadding(narrow ? 4 : 8).tickFormat(moneyTick))));
    yRight(svg, yPct, width - right, (t) => t + '%', narrow ? 3 : 5);
    axisTitle(svg, 0, narrow ? 'Spend (bars)' : 'Spend per ad (bars)');
    axisTitle(svg, width, 'Cumulative share (lines)', 'end');
    svg.append('g').selectAll('rect').data(rows).join('rect')
      .attr('x', (r) => x(String(r.rank))).attr('width', x.bandwidth()).attr('y', (r) => yMoney(r.spend))
      .attr('height', (r) => bottom - yMoney(r.spend)).attr('rx', Math.min(3, x.bandwidth() / 2))
      .attr('fill', (r) => (r.in_head ? 'var(--accent)' : 'var(--series-other)')).attr('fill-opacity', (r) => (r.in_head ? 0.75 : 0.9));
    const centre = (r) => x(String(r.rank)) + x.bandwidth() / 2;
    if (cut) {
      svg.append('line').attr('x1', left).attr('x2', width - right).attr('y1', yPct(cut.setting_pct)).attr('y2', yPct(cut.setting_pct))
        .attr('stroke', 'var(--heading)').attr('stroke-dasharray', '6 4').attr('stroke-width', 1.75);
      if (!narrow) svg.append('text').attr('class', 'cr-axis-title cr-knockout').attr('x', width - right - 6).attr('y', yPct(cut.setting_pct) + 15).attr('text-anchor', 'end')
        .text(asKind('share', cut.setting_pct) + ' of ' + cut.basis);
    }
    const lines = [['cum_spend_pct', 'Cumulative spend', 'var(--series-1)'], ['cum_basis_pct', 'Cumulative ' + (cut ? cut.basis : 'value'), 'var(--series-2)']];
    // Each curve rides on a halo in the card's colour, so it stays readable where it crosses the head's bars.
    lines.forEach(([key, , colour]) => {
      const d = d3.line().x(centre).y((r) => yPct(r[key]))(rows);
      svg.append('path').attr('d', d).attr('fill', 'none').attr('stroke', 'var(--surface)').attr('stroke-width', 6).attr('stroke-linejoin', 'round');
      svg.append('path').attr('d', d).attr('fill', 'none').attr('stroke', colour)
        .attr('stroke-width', 2.5).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    });
    const edge = cut ? rows.find((r) => r.rank === cut.cut) : null;
    if (edge) {
      const at = x(String(edge.rank)) + x.bandwidth() + x.step() * x.paddingInner() / 2;
      svg.append('line').attr('x1', at).attr('x2', at).attr('y1', topY).attr('y2', bottom).attr('stroke', 'var(--heading)').attr('stroke-width', 1.25);
      if (!narrow) svg.append('text').attr('class', 'cr-axis-title cr-knockout').attr('x', at + 6).attr('y', topY + 12).text('Head: top ' + asKind('int', cut.cut) + ' ads');
    }
    const tooltip = tip(box);
    const scale = scaleOf(box, width);
    const pics = media();
    svg.append('g').selectAll('rect').data(rows).join('rect').attr('class', 'cr-hit').attr('x', (r) => x(String(r.rank))).attr('width', Math.max(x.step(), 2))
      .attr('y', 0).attr('height', height).attr('fill', 'transparent')
      .on('mousemove', (event, r) => tooltip.show(centre(r) * scale(), yMoney(r.spend) * scale(), 'Rank ' + r.rank + ': ' + r.short_label, [
        'Spend: ' + asKind('money0', r.spend), 'Purchase value: ' + (r.conversion_value === null ? reasonOf(r.conversion_value_note) : asKind('money0', r.conversion_value)),
        ['Cumulative spend: ' + asKind('share', r.cum_spend_pct), 'var(--series-1)'],
        ['Cumulative ' + (cut ? cut.basis : 'value') + ': ' + asKind('share', r.cum_basis_pct), 'var(--series-2)']], (pics.get(String(r.ad_id)) || {}).thumb))
      .on('mouseleave', () => tooltip.hide())
      .on('click', (event, r) => openAd(r.ad_id));
    legend(box, [['Spend per ad, the head', 'var(--accent)'], ['Spend per ad, the long tail', 'var(--series-other)']].concat(lines.map(([, name, colour]) => [name, colour, 'line']))
      .concat(cut ? [[narrow ? asKind('share', cut.setting_pct) + ' of ' + cut.basis + ', the share the head must reach' : 'Share the head must reach', 'var(--heading)', 'dash']] : [])
      .concat(edge && narrow ? [['Head: top ' + asKind('int', cut.cut) + ' ads, left of this line', 'var(--heading)', 'line']] : []));
    svg.attr('aria-label', 'Ads ranked by spend with cumulative shares');
  }

  on(function pareto() {
    const rows = rowsOf('pareto');
    const chart = root.querySelector('#pareto-chart');
    const empty = emptyState('pareto', 'pareto');
    chart.hidden = empty;
    if (!empty && visible('pareto')) paretoChart(chart, rows, rowsOf('pareto-cut')[0]);
    const table = root.querySelector('#pareto-table');
    const shown = statusOf('pareto') === OK ? (paretoAll ? rows : rows.slice(0, PARETO_ROWS)) : null;
    const names = distinctNames(rows);
    fillTable(table, 'pareto', { label: (row) => document.createTextNode(names.get(String(row.ad_id))) }, null, shown && shown.length ? shown : null);
    marks('tbody tr', table).forEach((tr) => {
      const row = rows.find((r) => String(r.ad_id) === tr.dataset.key);
      tr.classList.toggle('cr-head-row', !!row && row.in_head);
    });
    const more = root.querySelector('#pareto-more');
    more.hidden = !shown || rows.length <= PARETO_ROWS;
    more.textContent = paretoAll ? 'Show the top ' + PARETO_ROWS : 'Show all ' + asKind('int', rows.length);
    say(root.querySelector('#pareto-count'), shown && rows.length ? 'Showing ' + asKind('int', shown.length) + ' of ' + asKind('int', rows.length) + ' ranked ads.' : '');
  });
  root.querySelector('#pareto-more').addEventListener('click', () => { paretoAll = !paretoAll; redraw(); });

  const GRADE = (grade) => (!grade ? 'cr-grade-none' : /best/.test(grade) ? 'cr-grade-best' : /weakest/.test(grade) ? 'cr-grade-weak' : /not graded/.test(grade) ? 'cr-grade-none' : 'cr-grade-mid');
  function formatChart(box) {
    const status = statusOf('formats');
    if (status !== OK) return blank(box, status);
    const rows = rowsOf('formats');
    if (!rows.length) return sayEmpty(box, 'n/a (no format scorecard in this run)');
    const ranks = new Map(rowsOf('share-daily').filter((d) => d.dimension === 'format').map((d) => [d.name, d.rank]));
    const roasMax = d3.max(rows, (r) => r.roas) || 1;
    const account = (rowsOf('kpis').find((r) => r.metric === 'roas') || {}).value;
    const head = make('div', 'cr-fmt-row cr-fmt-head');
    const roasHead = make('span', 'cr-fmt-scale');
    roasHead.append(make('span', '', 'ROAS'), make('span', 'cr-sub', asKind('x', ZERO) + ' to ' + asKind('x', roasMax)
      + (account === null || account === undefined ? '' : '; the tick is the account, ' + asKind('x', account))));
    head.append(make('span', '', 'Format'), make('span', '', 'Share of scored spend'), roasHead);
    box.replaceChildren(head, ...rows.map((r) => {
      const line = make('div', 'cr-fmt-row');
      const name = make('span', 'cr-fmt-name');
      const sw = make('span', 'cr-swatch');
      sw.style.background = r.format === 'unknown' || !ranks.has(r.name) ? 'var(--series-other)' : series(ranks.get(r.name));
      name.append(sw, make('span', '', r.name), make('span', 'cr-sub', asKind('int', r.ads) + ' ads'));
      const share = make('span', 'cr-barcell');
      const track = make('span', 'cr-track');
      const bar = make('span', 'cr-fill');
      bar.style.width = r.spend_share === null ? '0' : Math.min(r.spend_share, PERCENT_FULL) + '%';
      bar.style.background = sw.style.background;
      track.append(bar);
      share.append(track, make('span', 'cr-barval', r.spend_share === null ? reasonOf(r.spend_share_note) : asKind('share', r.spend_share)));
      const roas = make('span', 'cr-barcell');
      const rtrack = make('span', 'cr-track cr-track-dot');
      if (account !== null && account !== undefined && account <= roasMax) {
        const tick = make('span', 'cr-track-tick');
        tick.style.left = (account / roasMax) * PERCENT_FULL + '%';
        rtrack.append(tick);
      }
      if (r.roas !== null) {
        const dot = make('span', 'cr-gdot ' + GRADE(r.roas_grade));
        dot.style.left = (r.roas / roasMax) * PERCENT_FULL + '%';
        rtrack.append(dot);
      }
      roas.append(rtrack, make('span', 'cr-barval' + (r.roas === null ? ' cr-na' : ''), r.roas === null ? reasonOf(r.roas_note) : asKind('x', r.roas)));
      if (r.roas !== null && r.roas_grade) roas.title = r.roas_grade;
      line.append(name, share, roas);
      return line;
    }));
  }

  function heatmap(box, rows) {
    const status = statusOf('white-space');
    if (status !== OK || !rows.length) return blank(box, status);
    const concepts = Array.from(new Set(rows.map((r) => r.concept)));
    const formats = Array.from(new Set(rows.map((r) => r.format)));
    const avail = box.clientWidth || 600;
    const tilt = avail < 640;
    const probeSvg = d3.select(box).append('svg');
    const conceptW = tickWidth(probeSvg, concepts);
    const formatW = tickWidth(probeSvg, formats);
    probeSvg.remove();
    const left = Math.min(conceptW + 16, tilt ? 150 : avail * 0.35);
    const headH = tilt ? Math.min(formatW * 0.72 + 20, 120) : 34;
    const cellW = tilt ? 52 : null;
    const tail = tilt ? Math.min(formatW * 0.77, 110) : 0;
    const width = tilt ? Math.max(avail, left + formats.length * cellW + tail) : avail;
    const scrolls = width > avail;
    const scroller = box.closest('.cr-heat-scroll');
    scroller.classList.toggle('cr-heat-more', scrolls);
    scroller.parentElement.querySelectorAll('.cr-scroll-cue').forEach((n) => n.remove());
    if (scrolls) scroller.before(make('p', 'cr-muted cr-scroll-cue', 'Scroll sideways for every format →'));
    const height = 36 * concepts.length + headH + 6;
    const { svg } = svgIn(box, height, width);
    const x = d3.scaleBand(formats, [left, width - tail]).padding(0.06);
    const y = d3.scaleBand(concepts, [headH, height]).padding(0.08);
    const most = d3.max(rows, (r) => r.spend) || 1;
    const heads = svg.append('g').selectAll('text').data(formats).join('text').style('font-weight', 600).text((f) => f);
    if (tilt) heads.attr('transform', (f) => 'translate(' + (x(f) + x.bandwidth() / 2) + ',' + (headH - 8) + ') rotate(-40)').attr('text-anchor', 'start');
    else heads.attr('x', (f) => x(f) + x.bandwidth() / 2).attr('y', 20).attr('text-anchor', 'middle');
    svg.append('g').selectAll('text').data(concepts).join('text').attr('x', left - 8).attr('y', (c) => y(c) + y.bandwidth() / 2)
      .attr('dy', '0.35em').attr('text-anchor', 'end').text((c) => clip(c, tilt ? 20 : 40));
    const cells = svg.append('g').selectAll('g').data(rows).join('g').attr('transform', (r) => 'translate(' + x(r.format) + ',' + y(r.concept) + ')');
    cells.append('rect').attr('width', x.bandwidth()).attr('height', y.bandwidth()).attr('rx', 6)
      .attr('fill', (r) => (r.ads ? 'var(--accent)' : 'transparent')).attr('fill-opacity', (r) => (r.ads ? 0.18 + 0.72 * (r.spend / most) : 1))
      .attr('stroke', (r) => (r.gap ? 'var(--warning)' : r.ads ? 'none' : 'var(--divider)')).attr('stroke-width', (r) => (r.gap ? 2 : 1))
      .attr('stroke-dasharray', (r) => (r.gap ? '5 3' : r.ads ? null : '2 3'));
    cells.append('text').attr('x', x.bandwidth() / 2).attr('y', y.bandwidth() / 2).attr('dy', '0.35em').attr('text-anchor', 'middle')
      .style('font-weight', 600).style('fill', (r) => (r.ads && r.spend / most > 0.45 ? '#ffffff' : 'var(--heading)'))
      .text((r) => (r.gap ? '#' + r.gap + (r.ads ? ' · ' + r.ads : '') : r.ads ? String(r.ads) : ''));
    const tooltip = tip(box);
    const scale = () => box.clientWidth / width;
    cells.on('mousemove', (event, r) => tooltip.show((x(r.format) + x.bandwidth() / 2) * scale(), y(r.concept) * scale(), r.concept + ' in ' + r.format, [
      'Ads: ' + asKind('int', r.ads), 'Spend: ' + asKind('money0', r.spend)].concat(r.gap ? ['Gap #' + r.gap + ' in the list below'] : [])))
      .on('mouseleave', () => tooltip.hide());
    const key = make('div', 'cr-heat-key');
    const ramp = make('span', 'cr-ramp');
    key.append(make('span', '', 'Spend in the cell: ' + short('money0', ZERO)), ramp, make('span', '', short('money0', most)));
    const emptyKey = make('span', 'cr-empty-cell');
    const gapKey = make('span', 'cr-gap-cell');
    key.append(emptyKey, make('span', '', 'No ad yet'), gapKey, make('span', '', 'Numbered gap'));
    box.closest('.cr-card').querySelectorAll('.cr-heat-key').forEach((n) => n.remove());
    box.parentElement.after(key);
    svg.attr('aria-label', 'Concept by format: ads and spend');
  }

  const GAPS_SHOWN = 5; // gaps listed per reason before the rest fold behind a button
  function gapList(box) {
    const status = statusOf('gaps');
    if (status !== OK) return blank(box, status);
    const rows = rowsOf('gaps');
    if (!rows.length) { box.replaceChildren(); return; }
    const groups = Array.from(d3.group(rows, (r) => r.because));
    const intro = make('p', 'cr-lead cr-lead-card', asKind('int', rows.length) + ' gap' + (rows.length === 1 ? '' : 's') + ' worth testing, strongest first, from '
      + asKind('int', groups.length) + ' reason' + (groups.length === 1 ? '' : 's') + '.');
    box.replaceChildren(intro, ...groups.map(([because, list]) => {
      const group = make('section', 'cr-gap-group');
      group.append(make('p', 'cr-gap-why', because + '.'));
      const chips = make('div', 'cr-gap-cells');
      list.forEach((g, n) => {
        const cell = make('span', 'cr-gap-chip');
        cell.hidden = n >= GAPS_SHOWN;
        cell.append(make('b', '', '#' + g.number), document.createTextNode(' ' + g.concept + ' in ' + g.format));
        if (g.cell_ads) cell.append(make('span', 'cr-sub', 'has one ad'));
        if (!g.in_grid) cell.append(make('span', 'cr-sub', 'concept not shown in the grid above'));
        chips.append(cell);
      });
      group.append(chips);
      if (list.length > GAPS_SHOWN) {
        const more = make('button', 'cr-more', '+' + asKind('int', list.length - GAPS_SHOWN) + ' more');
        more.type = 'button';
        more.addEventListener('click', () => { marks('.cr-gap-chip', chips).forEach((c) => { c.hidden = false; }); more.remove(); });
        group.append(more);
      }
      return group;
    }));
  }

  on(function mix() {
    const formatEmpty = emptyState('format-scorecard', 'format');
    const formatTable = root.querySelector('#format-table');
    formatTable.hidden = formatEmpty;
    root.querySelector('#format-chart').hidden = formatEmpty;
    if (!formatEmpty) formatChart(root.querySelector('#format-chart'));
    const graded = (field) => (row) => {
      const frag = document.createDocumentFragment();
      frag.append(cellText(row[field], row[field + '_note'], KIND[field]));
      if (row[field] !== null && row[field + '_grade']) {
        const g = make('span', 'cr-sub cr-grade');
        g.append(make('span', 'cr-gdot-inline ' + GRADE(row[field + '_grade'])), document.createTextNode(row[field + '_grade']));
        frag.append(g);
      }
      return frag;
    };
    const cells = {};
    ['ctr', 'cpm', 'cpa', 'roas', 'hook_rate', 'hold_rate'].forEach((field) => { cells[field] = graded(field); });
    fillTable(formatTable, 'formats', cells);
    const chart = root.querySelector('#heatmap-chart');
    const empty = emptyState('heatmap', 'heatmap');
    chart.hidden = empty;
    if (!empty && visible('mix')) heatmap(chart, rowsOf('white-space'));
    const gapsEmpty = emptyState('gaps', 'gaps');
    const list = root.querySelector('#gap-list');
    list.hidden = gapsEmpty;
    if (!gapsEmpty) gapList(list);
  });

  dash.onData(function briefing() {
    const empty = emptyState('briefs', 'briefs');
    const box = root.querySelector('#brief-cards');
    box.hidden = empty;
    const judged = root.querySelector('#briefs-judged');
    const status = statusOf('briefing');
    if (status !== OK) { say(judged, ''); return blank(box, status); }
    if (empty) return;
    const rows = rowsOf('briefing');
    const same = rows.length > 1 && new Set(rows.map((r) => r.judged)).size === 1;
    const facts = (r) => String(r.details || '').split('\n').filter(Boolean).map((line) => {
      const at = line.indexOf(': ');
      return at > 0 ? [line.slice(0, at), line.slice(at + 2)] : ['', line];
    });
    const common = rows.length > 1 ? facts(rows[0]).filter(([label, text]) => label && rows.every((r) => facts(r).some(([l, t]) => l === label && t === text))) : [];
    const shared = new Set(common.map(([label]) => label));
    say(judged, [same ? 'Every brief is judged by ' + String(rows[0].judged).replace(/\.$/, '') + '.' : ''].concat(common.map(([label, text]) => label + ', for every brief: ' + text))
      .filter(Boolean).join(' '));
    if (!rows.length) { box.replaceChildren(make('p', 'cr-empty', 'n/a (no rows in this data)')); return; }
    box.replaceChildren(...rows.map((r) => {
      const card = make('article', 'cr-brief');
      const title = make('h4', 'cr-brief-title');
      title.append(breakable(r.title));
      card.append(make('p', 'cr-eyebrow', (r.kind === 'brief' ? 'Brief ' : 'Brief starter ') + r.number), title);
      const list = make('dl', 'cr-brief-facts');
      facts(r).filter(([label]) => !shared.has(label)).forEach(([label, text]) => list.append(make('dt', '', label), make('dd', '', text)));
      card.append(list);
      const refs = make('div', 'cr-brief-refs');
      refs.append(make('span', 'cr-brief-label', 'Reference ads'));
      String(r.references || '').split('; ').filter(Boolean).forEach((ref) => refs.append(make('span', 'cr-ref', ref)));
      card.append(refs);
      if (!same) {
        const j = make('p', 'cr-sub');
        j.append(make('b', '', 'Judged by: '), document.createTextNode(r.judged));
        card.append(j);
      }
      if (r.prompt) {
        const details = make('details', 'cr-prompt');
        details.append(make('summary', '', 'Prompt'), make('pre', '', r.prompt));
        card.append(details);
      }
      return card;
    }));
  });

  dash.onData(function method() {
    const status = statusOf('notes');
    [['#method-list', 'method'], ['#caveat-list', 'caveat']].forEach(([selector, section]) => {
      const list = root.querySelector(selector);
      if (status !== OK) return blank(list, status);
      list.replaceChildren(...rowsOf('notes').filter((r) => r.section === section).map((r) => make('li', '', r.text)));
    });
  });

  // ---------- the link the dashboard opened with ----------
  const named = location.hash.slice(1);
  if (named === 'ad' && !dash.params().ad) showPage('ads', false);
  else if (pages.some((p) => p.id === named)) showPage(named, false);
  else showPage('overview', false);
})();
