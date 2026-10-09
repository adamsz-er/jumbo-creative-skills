/* The creative report as a Claude dashboard. Every number comes from a dataset computed by the report script;
   this page only formats and draws it. Values are written as text (textContent, d3 .text()), never as markup. */
(function () {
  const root = document.querySelector('.cr');
  if (!root) return;
  const DASH = '—';
  const NO_ADS = 'n/a (no ad data in this run)';
  const ZERO = 0;
  const ONE = 1;
  const PERCENT_FULL = 100;  // the fixed 0 to 100 scale of a percent axis
  const OK = 'ok';
  // What a reader sees when a source is not there, one short line for each way it can fail.
  const FAILED = {
    error: 'Failed to load',
    connect: 'Could not connect to the data',
    declined: 'Access to the data was declined',
    missing: 'The data source is missing',
  };
  const isFailed = (status) => Object.prototype.hasOwnProperty.call(FAILED, status);

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

  // ---------- formatting ----------
  const grouped0 = d3.format(',.0f');
  const grouped2 = d3.format(',.2f');
  const currency = () => {
    const fact = rowsOf('header').find((row) => row.fact === 'Currency');
    const code = fact ? String(fact.value) : '';
    return /^[A-Z]{3}$/.test(code) ? code : '';
  };
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
    if (kind === 'int') return grouped0(n);
    return String(v);
  };
  const KIND = { spend: 'money0', conversion_value: 'money0', tail_spend: 'money0', spend_at_stake: 'money0', cpa: 'money', cpm: 'money',
    roas: 'x', ctr: 'pct', hook_rate: 'pct', hold_rate: 'pct', cum_spend_pct: 'share', cum_basis_pct: 'share', spend_share: 'share',
    setting_pct: 'share', concentration_pct: 'share', ads: 'int', rank: 'int', cut: 'int' };
  const dayLabel = d3.utcFormat('%-d %b');

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
    el.replaceChildren();
    el.classList.toggle('dash-skeleton', status === 'loading');
    if (isFailed(status)) failedLine(el, status);
  };
  const marks = (selector, scope) => Array.from((scope || root).querySelectorAll(selector));

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
  const fillMarks = (id, format) => {
    const status = statusOf(id);
    const rows = rowsOf(id);
    marks('[data-source="' + id + '"][data-field]').forEach((el) => {
      if (el.closest('table')) return;
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

  // ---------- tables ----------
  const cellText = (value, note, kind) => {
    if (value === null || value === undefined) {
      const span = make('span', 'cr-na', 'n/a');
      const frag = document.createDocumentFragment();
      frag.append(span);
      if (note) frag.append(make('span', 'cr-sub', String(note).replace(/^n\/a \((.*)\)$/, '$1')));
      return frag;
    }
    return document.createTextNode(kind ? asKind(kind, value) : String(value));
  };
  const fillTable = (table, id, cells, keep) => {
    const body = table.querySelector('tbody');
    const status = statusOf(id);
    const fields = marks('th[data-field]', table).map((th) => th.getAttribute('data-field'));
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
    const shown = rowsOf(id).filter((row) => !keep || keep(row));
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
      fields.forEach((field) => {
        const td = make('td', marks('th[data-field="' + field + '"]', table)[0].className);
        const content = cells[field] ? cells[field](row) : cellText(row[field], row[field + '_note'], KIND[field]);
        td.append(content);
        tr.append(td);
      });
      return tr;
    }));
  };

  // ---------- charts ----------
  const tip = (box) => {
    let el = box.querySelector('.cr-tip');
    if (!el) { el = make('div', 'cr-tip'); el.hidden = true; box.append(el); }
    return {
      show(x, y, head, lines) {
        el.replaceChildren(make('div', 'cr-tip-head', head), ...lines.map((line) => make('div', '', line)));
        el.hidden = false;
        const width = el.offsetWidth;
        const left = Math.max(0, Math.min(x + 16, box.clientWidth - width));
        el.style.left = left + 'px';
        el.style.top = Math.max(0, y - el.offsetHeight - 8) + 'px';
      },
      hide() { el.hidden = true; },
    };
  };
  const svgIn = (box, height) => {
    const width = Math.max(box.clientWidth, 240);
    box.querySelectorAll('svg').forEach((s) => s.remove());
    const svg = d3.select(box).insert('svg', ':first-child').attr('width', '100%').attr('viewBox', [0, 0, width, height]).attr('role', 'img');
    return { svg, width, height };
  };
  const tickWidth = (svg, labels) => {
    const probe = svg.append('text').attr('font-size', null);
    const widest = d3.max(labels, (text) => probe.text(text).node().getComputedTextLength()) || 0;
    probe.remove();
    return widest;
  };
  const cleanAxis = (g) => g.attr('font-size', null).attr('font-family', null);

  function sparkline(box, rows) {
    const status = statusOf('daily');
    if (status !== OK || !rows.length) return blank(box, status);
    const { svg, width, height } = svgIn(box, 32);
    const days = rows.map((r) => new Date(r.day));
    const x = d3.scaleUtc(d3.extent(days), [2, width - 2]);
    const values = rows.map((r) => r.value).filter((v) => v !== null);
    const y = d3.scaleLinear(d3.extent(values.length ? values : [ZERO, ONE]), [height - 3, 3]);
    const line = (key) => d3.line().defined((r) => r[key] !== null).x((r) => x(new Date(r.day))).y((r) => y(r[key]));
    svg.append('path').attr('d', line('average')(rows)).attr('fill', 'none').attr('stroke', 'var(--cds-chart-muted)').attr('stroke-width', 1.5);
    svg.append('path').attr('d', line('value')(rows)).attr('fill', 'none').attr('stroke', dash.colors[0]).attr('stroke-width', 1.5)
      .attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    svg.attr('aria-label', rows[0].name + ' by day');
  }

  function timeChart(box, rows, spend) {
    const status = statusOf('daily');
    if (status !== OK || !rows.length) return blank(box, status);
    const kind = rows[0].kind;
    const height = 288;
    const { svg, width } = svgIn(box, height);
    const days = rows.map((r) => new Date(r.day));
    const values = rows.flatMap((r) => [r.value, r.average]).filter((v) => v !== null);
    const y = d3.scaleLinear([0, d3.max(values) || 1], [height - 28, 16]).nice();
    const yLabels = y.ticks(5).map((t) => asKind(kind, t));
    const left = tickWidth(svg, yLabels) + 16;
    const x = d3.scaleUtc(d3.extent(days), [left, width - 16]);
    svg.append('g').attr('class', 'cr-grid').attr('transform', 'translate(' + left + ',0)')
      .call((g) => cleanAxis(g.call(d3.axisLeft(y).ticks(5).tickSize(-(width - left - 16)).tickFormat((t) => asKind(kind, t)))));
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(0,' + (height - 28) + ')')
      .call((g) => cleanAxis(g.call(d3.axisBottom(x).ticks(Math.max(2, Math.floor(width / 90))).tickFormat(dayLabel))));
    const bars = rows[0].metric === 'spend' ? [] : spend;
    if (bars.length) {
      const yb = d3.scaleLinear([0, d3.max(bars, (r) => r.value) || 1], [height - 28, height * 0.55]);
      const step = (width - left - 16) / Math.max(bars.length, 1);
      svg.append('g').selectAll('rect').data(bars.filter((r) => r.value !== null)).join('rect')
        .attr('x', (r) => x(new Date(r.day)) - step * 0.35).attr('width', Math.max(1, step * 0.7))
        .attr('y', (r) => yb(r.value)).attr('height', (r) => height - 28 - yb(r.value))
        .attr('rx', 2).attr('fill', 'var(--cds-chart-muted)').attr('opacity', 0.35);
    }
    const line = (key) => d3.line().defined((r) => r[key] !== null).x((r) => x(new Date(r.day))).y((r) => y(r[key]));
    svg.append('path').attr('d', line('average')(rows)).attr('fill', 'none').attr('stroke', dash.colors[0]).attr('stroke-width', 2)
      .attr('stroke-dasharray', '4 3').attr('opacity', 0.6);
    svg.append('path').attr('d', line('value')(rows)).attr('fill', 'none').attr('stroke', dash.colors[0]).attr('stroke-width', 2)
      .attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    const dot = svg.append('circle').attr('r', 4).attr('fill', dash.colors[0]).attr('opacity', 0);
    const tooltip = tip(box);
    const spendOf = byKey(spend, 'day');
    svg.append('rect').attr('x', left).attr('width', width - left).attr('height', height).attr('fill', 'transparent')
      .on('mousemove', (event) => {
        const [mx] = d3.pointer(event);
        const at = x.invert(mx);
        const row = rows[d3.minIndex(rows, (r) => Math.abs(new Date(r.day) - at))];
        if (row.value !== null) dot.attr('cx', x(new Date(row.day))).attr('cy', y(row.value)).attr('opacity', 1);
        else dot.attr('opacity', 0);
        const lines = [row.name + ': ' + (row.value === null ? row.value_note : asKind(kind, row.value)),
          'Rolling average: ' + (row.average === null ? row.average_note : asKind(kind, row.average))];
        const s = spendOf.get(row.day);
        if (bars.length && s) lines.push('Spend: ' + (s.value === null ? s.value_note : asKind('money', s.value)));
        const scale = box.clientWidth / width;
        tooltip.show(x(new Date(row.day)) * scale, y(row.value === null ? 0 : row.value), dayLabel(new Date(row.day)), lines);
      })
      .on('mouseleave', () => { dot.attr('opacity', 0); tooltip.hide(); });
    svg.attr('aria-label', rows[0].name + ' by day with a rolling average');
  }

  function paretoChart(box, rows, cut) {
    const status = statusOf('pareto', 'pareto-cut');
    if (status !== OK || !rows.length) return blank(box, status);
    const height = 288;
    const { svg, width } = svgIn(box, height);
    const yMoney = d3.scaleLinear([0, d3.max(rows, (r) => r.spend) || 1], [height - 28, 16]).nice();
    const left = tickWidth(svg, yMoney.ticks(5).map((t) => asKind('money0', t))) + 16;
    const right = tickWidth(svg, ['100%']) + 16;
    const x = d3.scaleBand(rows.map((r) => String(r.rank)), [left, width - right]).padding(0.2);
    const yPct = d3.scaleLinear([ZERO, PERCENT_FULL], [height - 28, 16]);
    svg.append('g').attr('class', 'cr-grid').attr('transform', 'translate(' + left + ',0)')
      .call((g) => cleanAxis(g.call(d3.axisLeft(yMoney).ticks(5).tickSize(-(width - left - right)).tickFormat((t) => asKind('money0', t)))));
    svg.append('g').attr('class', 'cr-axis').attr('transform', 'translate(' + (width - right) + ',0)')
      .call((g) => cleanAxis(g.call(d3.axisRight(yPct).ticks(5).tickFormat((t) => t + '%'))));
    svg.append('g').selectAll('rect').data(rows).join('rect')
      .attr('x', (r) => x(String(r.rank))).attr('width', x.bandwidth()).attr('y', (r) => yMoney(r.spend))
      .attr('height', (r) => height - 28 - yMoney(r.spend)).attr('rx', 2)
      .attr('fill', (r) => (r.in_head ? dash.colors[0] : 'var(--cds-chart-muted)'));
    const centre = (r) => x(String(r.rank)) + x.bandwidth() / 2;
    const series = [['cum_spend_pct', 'Cumulative spend', dash.colors[1]], ['cum_basis_pct', 'Cumulative ' + (cut ? cut.basis : 'value'), dash.colors[2]]];
    series.forEach(([key, , colour]) => {
      svg.append('path').attr('d', d3.line().x(centre).y((r) => yPct(r[key]))(rows)).attr('fill', 'none').attr('stroke', colour)
        .attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    });
    if (cut) {
      const edge = rows.find((r) => r.rank === cut.cut);
      if (edge) {
        svg.append('line').attr('x1', x(String(edge.rank)) + x.bandwidth() + 1).attr('x2', x(String(edge.rank)) + x.bandwidth() + 1)
          .attr('y1', 16).attr('y2', height - 28).attr('stroke', 'var(--cds-chart-reference)').attr('stroke-dasharray', '4 3');
      }
    }
    const tooltip = tip(box);
    const scale = () => box.clientWidth / width;
    svg.append('g').selectAll('rect').data(rows).join('rect').attr('x', (r) => x(String(r.rank))).attr('width', x.bandwidth())
      .attr('y', 0).attr('height', height).attr('fill', 'transparent')
      .on('mousemove', (event, r) => tooltip.show(centre(r) * scale(), yMoney(r.spend), 'Rank ' + r.rank + ': ' + r.label, [
        'Spend: ' + asKind('money0', r.spend), 'Purchase value: ' + (r.conversion_value === null ? r.conversion_value_note : asKind('money0', r.conversion_value)),
        'Cumulative spend: ' + asKind('share', r.cum_spend_pct), 'Cumulative ' + (cut ? cut.basis : 'value') + ': ' + asKind('share', r.cum_basis_pct)]))
      .on('mouseleave', () => tooltip.hide());
    let legend = box.querySelector('.cr-legend');
    if (!legend) { legend = make('div', 'cr-legend'); box.append(legend); }
    legend.replaceChildren(...[['Spend per ad (head in colour)', dash.colors[0]]].concat(series.map(([, name, colour]) => [name, colour]))
      .map(([name, colour]) => { const item = make('span', '', name); const sw = make('span', 'cr-swatch'); sw.style.background = colour; item.prepend(sw); return item; }));
    svg.attr('aria-label', 'Ads ranked by spend with cumulative shares');
  }

  function heatmap(box, rows) {
    const status = statusOf('white-space');
    if (status !== OK || !rows.length) return blank(box, status);
    const concepts = Array.from(new Set(rows.map((r) => r.concept)));
    const formats = Array.from(new Set(rows.map((r) => r.format)));
    const row = 32;
    const height = row * concepts.length + 40;
    const { svg, width } = svgIn(box, height);
    const left = Math.min(tickWidth(svg, concepts) + 16, width * 0.4);
    const x = d3.scaleBand(formats, [left, width]).padding(0.06);
    const y = d3.scaleBand(concepts, [32, height]).padding(0.06);
    const most = d3.max(rows, (r) => r.spend) || 1;
    svg.append('g').selectAll('text').data(formats).join('text').attr('x', (f) => x(f) + x.bandwidth() / 2).attr('y', 22)
      .attr('text-anchor', 'middle').text((f) => f);
    svg.append('g').selectAll('text').data(concepts).join('text').attr('x', left - 8).attr('y', (c) => y(c) + y.bandwidth() / 2)
      .attr('dy', '0.35em').attr('text-anchor', 'end').text((c) => c);
    const cells = svg.append('g').selectAll('g').data(rows).join('g').attr('transform', (r) => 'translate(' + x(r.format) + ',' + y(r.concept) + ')');
    cells.append('rect').attr('width', x.bandwidth()).attr('height', y.bandwidth()).attr('rx', 4)
      .attr('fill', (r) => (r.ads ? dash.colors[0] : 'var(--color-bg)')).attr('fill-opacity', (r) => (r.ads ? 0.11 + 0.79 * (r.spend / most) : 1))
      .attr('stroke', (r) => (r.gap ? 'var(--color-warn)' : 'var(--color-border-line)')).attr('stroke-width', (r) => (r.gap ? 2 : 1))
      .attr('stroke-dasharray', (r) => (r.gap ? '4 2' : null));
    cells.append('text').attr('x', x.bandwidth() / 2).attr('y', y.bandwidth() / 2).attr('dy', '0.35em').attr('text-anchor', 'middle')
      .style('fill', (r) => (r.ads && r.spend / most > 0.55 ? 'var(--color-bg)' : 'var(--color-fg)'))
      .text((r) => (r.gap ? '#' + r.gap + (r.ads ? ' · ' + r.ads : '') : r.ads ? String(r.ads) : ''));
    const tooltip = tip(box);
    const scale = () => box.clientWidth / width;
    cells.on('mousemove', (event, r) => tooltip.show((x(r.format) + x.bandwidth() / 2) * scale(), y(r.concept) * scale(), r.concept + ' in ' + r.format, [
      'Ads: ' + asKind('int', r.ads), 'Spend: ' + asKind('money0', r.spend)].concat(r.gap ? ['Gap #' + r.gap + ' in the list below'] : [])))
      .on('mouseleave', () => tooltip.hide());
    svg.attr('aria-label', 'Concept by format: ads and spend');
  }

  // ---------- sections ----------
  let measure = null;
  let verdictShown = 'all';

  const blankNote = (el, status) => (isFailed(status) ? failedLine(el, status) : wait(el, status));

  dash.onData(function header() {
    fillMarks('header');
    const completeness = root.querySelector('.cr-completeness');
    const row = rowsOf('header').find((r) => r.fact === 'Completeness');
    ['ok', 'warn', 'neutral'].forEach((tone) => completeness.classList.toggle('cr-tone-' + tone, !!row && row.tone === tone));
    fillMarks('pareto-cut', (field, value, r) => (KIND[field] ? asKind(KIND[field], value) : value));
    const cut = rowsOf('pareto-cut')[0];
    if (statusOf('pareto-cut') === OK && !cut) {
      const state = rowsOf('sections').find((r) => r.panel === 'pareto');
      ['takeaway', 'pareto-lead'].forEach((id) => show(root.querySelector('#' + id), (state && state.why) || NO_ADS));
    }
    const note = root.querySelector('#concentration-note');
    if (statusOf('pareto-cut') !== OK) blankNote(note, statusOf('pareto-cut'));
    else show(note, cut ? (cut.concentration_pct_note || 'The top ' + cut.top_n + ' ads by spend: an arbitrary default, set your own.') : null);
  });

  dash.onData(function overview() {
    const status = statusOf('kpis');
    const kpisEmpty = emptyState('kpis', 'kpis');
    root.querySelector('#kpis').hidden = kpisEmpty;
    const kpis = byKey(rowsOf('kpis'), 'metric');
    const daily = rowsOf('daily');
    marks('.cr-kpi').forEach((tile) => {
      const row = kpis.get(tile.getAttribute('data-metric'));
      tile.classList.toggle('cr-unknown', !!row && row.value === null);
      marks('[data-field]', tile).forEach((el) => {
        const field = el.getAttribute('data-field');
        if (field === 'name' || field === 'shown') {
          if (status !== OK) return blankNote(el, status);
          return show(el, row ? row[field] : null);
        }
        const value = row ? row[field] : null;
        el.hidden = status !== OK || value === null || value === undefined || value === '';
        if (el.hidden) return;
        if (field === 'change_pct') {
          el.className = 'cr-kpi-change cr-' + (row.change_tone || 'flat');
          return show(el, (value > 0 ? '+' : '') + Number(value).toFixed(1) + '% vs ' + row.against);
        }
        show(el, value);
      });
      const spark = tile.querySelector('.cr-spark');
      sparkline(spark, daily.filter((r) => r.metric === tile.getAttribute('data-metric')));
    });
    const banner = root.querySelector('#not-in-pull');
    const list = root.querySelector('#not-in-pull-list');
    const missing = rowsOf('notes').filter((r) => r.section === 'not-in-pull');
    banner.hidden = !missing.length;
    list.replaceChildren(...missing.map((r) => make('li', '', r.text)));

    const switcher = root.querySelector('#time-switch');
    const chart = root.querySelector('#time-chart');
    const empty = emptyState('time', 'time');
    const names = Array.from(new Map(daily.map((r) => [r.metric, r.name])));
    if (!measure || !names.some(([key]) => key === measure)) measure = names.length ? names[0][0] : null;
    switcher.replaceChildren(...names.map(([key, name]) => {
      const button = make('button', '', name);
      button.type = 'button';
      button.setAttribute('aria-pressed', String(key === measure));
      button.addEventListener('click', () => { measure = key; overview(); });
      return button;
    }));
    chart.hidden = empty;
    if (!empty) timeChart(chart, daily.filter((r) => r.metric === measure), daily.filter((r) => r.metric === 'spend'));
  });

  dash.onData(function pareto() {
    const rows = rowsOf('pareto');
    const cut = rowsOf('pareto-cut')[0];
    const chart = root.querySelector('#pareto-chart');
    const empty = emptyState('pareto', 'pareto');
    chart.hidden = empty;
    if (!empty) paretoChart(chart, rows, cut);
    const table = root.querySelector('#pareto-table');
    fillTable(table, 'pareto', {});
    marks('tbody tr', table).forEach((tr) => {
      const row = rows.find((r) => String(r.ad_id) === tr.dataset.key);
      tr.classList.toggle('cr-head-row', !!row && row.in_head);
    });
  });

  const chip = (row) => {
    if (!row.verdict) return cellText(null, row.verdict_note);
    return make('span', 'cr-chip cr-v-' + (row.verdict_class || 'none'), row.verdict);
  };

  dash.onData(function keepKill() {
    const board = rowsOf('verdict-board');
    const empty = emptyState('board', 'board');
    const boardTable = root.querySelector('#board-table');
    boardTable.hidden = empty;
    fillTable(boardTable, 'verdict-board', { verdict: chip, check: (row) => document.createTextNode(row.check || '') });
    const filter = root.querySelector('#verdict-filter');
    const allEmpty = emptyState('all-ads', 'all-ads');
    const allTable = root.querySelector('#verdict-table');
    allTable.closest('.cr-scroll').hidden = allEmpty;
    root.querySelector('#images-note').hidden = allEmpty;
    const offered = board.filter((r) => r.ads > 0);
    if (verdictShown !== 'all' && !offered.some((r) => r.verdict_class === verdictShown)) verdictShown = 'all';
    const choices = [['all', 'All ads']].concat(offered.map((r) => [r.verdict_class, r.verdict]));
    filter.hidden = allEmpty || !offered.length;
    filter.replaceChildren(...choices.map(([key, name]) => {
      const button = make('button', '', name);
      button.type = 'button';
      button.setAttribute('aria-pressed', String(key === verdictShown));
      button.addEventListener('click', () => { verdictShown = key; keepKill(); });
      return button;
    }));
    const table = allTable;
    fillTable(table, 'verdicts', {
      thumb: (row) => {
        if (!row.thumb || !/^data:image\//.test(row.thumb)) return make('span', 'cr-na', DASH);
        const img = make('img', 'cr-thumb');
        img.setAttribute('src', row.thumb);
        img.alt = 'Thumbnail of ' + row.label;
        return img;
      },
      label: (row) => {
        const frag = document.createDocumentFragment();
        frag.append(document.createTextNode(row.label));
        if (row.check) frag.append(make('span', 'cr-sub', 'Check first: ' + row.check));
        return frag;
      },
      verdict: chip,
      confidence: (row) => cellText(row.confidence, row.confidence_note),
      next_step: (row) => document.createTextNode(row.next_step || ''),
    }, (row) => verdictShown === 'all' || row.verdict_class === verdictShown);
  });

  dash.onData(function format() {
    const empty = emptyState('format-scorecard', 'format');
    const table = root.querySelector('#format-table');
    table.hidden = empty;
    const graded = (field) => (row) => {
      const frag = document.createDocumentFragment();
      frag.append(cellText(row[field], row[field + '_note'], KIND[field]));
      if (row[field] !== null && row[field + '_grade']) frag.append(make('span', 'cr-sub', row[field + '_grade']));
      return frag;
    };
    const cells = {};
    ['ctr', 'cpm', 'cpa', 'roas', 'hook_rate', 'hold_rate'].forEach((field) => { cells[field] = graded(field); });
    fillTable(table, 'formats', cells);
  });

  dash.onData(function whiteSpace() {
    const chart = root.querySelector('#heatmap-chart');
    const empty = emptyState('heatmap', 'heatmap');
    chart.hidden = empty;
    if (!empty) heatmap(chart, rowsOf('white-space'));
    const gapsEmpty = emptyState('gaps', 'gaps');
    const table = root.querySelector('#gap-table');
    table.hidden = gapsEmpty;
    fillTable(table, 'gaps', { number: (row) => document.createTextNode('#' + row.number) });
  });

  dash.onData(function briefing() {
    const empty = emptyState('briefs', 'briefs');
    const table = root.querySelector('#brief-table');
    table.hidden = empty;
    fillTable(table, 'briefing', {
      details: (row) => make('span', 'cr-pre', row.details),
      prompt: (row) => {
        if (!row.prompt) return cellText(null, row.prompt_note);
        const details = make('details', 'cr-prompt');
        details.append(make('summary', '', 'Show the prompt'), make('pre', '', row.prompt));
        return details;
      },
    });
  });

  dash.onData(function method() {
    const status = statusOf('notes');
    [['#method-list', 'method'], ['#caveat-list', 'caveat']].forEach(([selector, section]) => {
      const list = root.querySelector(selector);
      if (status !== OK) return blank(list, status);
      list.replaceChildren(...rowsOf('notes').filter((r) => r.section === section).map((r) => make('li', '', r.text)));
    });
  });

  // ---------- links ----------
  const jump = root.querySelector('#jump');
  const go = (el) => {
    el.scrollIntoView({ block: 'start' });
    dash.setLink(el.id);
    marks('a', jump).forEach((a) => a.setAttribute('aria-current', String(a.getAttribute('data-section') === el.id)));
  };
  jump.addEventListener('click', (event) => {
    const link = event.target.closest('a[data-section]');
    if (!link) return;
    event.preventDefault();
    const target = document.getElementById(link.getAttribute('data-section'));
    if (target) go(target);
  });
  const named = document.getElementById(location.hash.slice(1));
  if (named && root.contains(named)) requestAnimationFrame(() => go(named));
})();
