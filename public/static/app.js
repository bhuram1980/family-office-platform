(function () {
  function toast(msg, kind) {
    var t = document.getElementById('toast'); if (!t) return;
    t.textContent = msg; t.className = 'toast show ' + (kind || '');
    clearTimeout(t._h); t._h = setTimeout(function () { t.className = 'toast'; }, 3800);
  }
  window.toast = toast;

  var PALETTE = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#64748b', '#14b8a6'];
  function fmtTick(v) {
    var a = Math.abs(v);
    if (a >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B';
    if (a >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M';
    if (a >= 1e3) return '$' + (v / 1e3).toFixed(0) + 'K';
    return '$' + v;
  }
  function initCharts(root) {
    if (!window.Chart) return;
    Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
    Chart.defaults.font.size = 11;
    Chart.defaults.color = '#64748b';
    Chart.defaults.plugins.legend.labels.boxWidth = 10;
    (root || document).querySelectorAll('canvas[data-chart]').forEach(function (c) {
      if (c._chart) return;
      var cfg = JSON.parse(c.getAttribute('data-chart'));
      var money = cfg.money; delete cfg.money;
      var pct = cfg.pct; delete cfg.pct;
      cfg.options = cfg.options || {};
      cfg.options.maintainAspectRatio = false;
      cfg.options.responsive = true;
      var round = cfg.type === 'doughnut' || cfg.type === 'pie';
      (cfg.data.datasets || []).forEach(function (d, i) {
        if (!d.backgroundColor) d.backgroundColor = round ? PALETTE : (cfg.type === 'line' ? 'rgba(99,102,241,.08)' : PALETTE[i % PALETTE.length]);
        if (!d.borderColor && cfg.type === 'line') d.borderColor = PALETTE[i % PALETTE.length];
        if (cfg.type === 'line') { d.borderWidth = d.borderWidth || 2; d.pointRadius = d.pointRadius || 0; d.tension = d.tension == null ? .3 : d.tension; }
        if (cfg.type === 'bar') { d.borderRadius = d.borderRadius == null ? 4 : d.borderRadius; d.maxBarThickness = d.maxBarThickness || 46; }
        if (round) { d.borderWidth = 2; d.borderColor = '#fff'; }
      });
      if (round) { cfg.options.cutout = cfg.options.cutout || '58%'; cfg.options.plugins = cfg.options.plugins || {}; cfg.options.plugins.legend = cfg.options.plugins.legend || { position: 'right' }; }
      else {
        cfg.options.scales = cfg.options.scales || {};
        var y = cfg.options.indexAxis === 'y' ? 'x' : 'y';
        cfg.options.scales[y] = Object.assign({ grid: { color: '#f1f5f9' }, border: { display: false } }, cfg.options.scales[y] || {});
        var x = y === 'y' ? 'x' : 'y';
        cfg.options.scales[x] = Object.assign({ grid: { display: false } }, cfg.options.scales[x] || {});
        if (money) cfg.options.scales[y].ticks = { callback: fmtTick };
        if (pct) cfg.options.scales[y].ticks = { callback: function (v) { return v + '%'; } };
        cfg.options.plugins = cfg.options.plugins || {};
        if (cfg.options.plugins.legend === undefined) cfg.options.plugins.legend = { display: (cfg.data.datasets || []).length > 1, position: 'top', align: 'end' };
      }
      if (money) {
        cfg.options.plugins = cfg.options.plugins || {};
        cfg.options.plugins.tooltip = { callbacks: { label: function (ctx) { var v = ctx.parsed && typeof ctx.parsed === 'object' ? (cfg.options.indexAxis === 'y' ? ctx.parsed.x : ctx.parsed.y) : ctx.parsed; return (ctx.dataset.label ? ctx.dataset.label + ': ' : (ctx.label ? ctx.label + ': ' : '')) + '$' + Math.round(v).toLocaleString(); } } };
      }
      c._chart = new Chart(c, cfg);
    });
  }

  function initTabs() {
    var params = new URLSearchParams(location.search);
    document.querySelectorAll('[data-tabs]').forEach(function (bar) {
      var key = bar.getAttribute('data-tabs') || 'tab';
      var links = bar.querySelectorAll('a[data-tab]');
      var want = params.get(key) || (links[0] && links[0].getAttribute('data-tab'));
      function show(name, push) {
        links.forEach(function (a) { a.classList.toggle('on', a.getAttribute('data-tab') === name); });
        document.querySelectorAll('.tabpanel[data-group="' + key + '"]').forEach(function (p) {
          var on = p.getAttribute('data-tab') === name; p.classList.toggle('on', on);
          if (on) setTimeout(function () { p.querySelectorAll('canvas').forEach(function (c) { c._chart && c._chart.resize(); }); initCharts(p); }, 0);
        });
        if (push) { var u = new URL(location.href); u.searchParams.set(key, name); history.replaceState(null, '', u); }
      }
      links.forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); show(a.getAttribute('data-tab'), true); }); });
      show(want, false);
    });
  }

  function initSort() {
    document.querySelectorAll('table.sortable').forEach(function (t) {
      t.querySelectorAll('thead th').forEach(function (th, idx) {
        th.addEventListener('click', function () {
          var tb = t.tBodies[0]; var rows = Array.prototype.slice.call(tb.rows);
          var asc = !th.classList.contains('sorted-asc');
          t.querySelectorAll('th').forEach(function (h) { h.classList.remove('sorted-asc', 'sorted-desc'); });
          th.classList.add(asc ? 'sorted-asc' : 'sorted-desc');
          function val(r) { var c = r.cells[idx]; if (!c) return ''; var s = c.getAttribute('data-v') || c.textContent.trim(); var neg = /^\(.*\)$/.test(s); var n = parseFloat(s.replace(/[$,%x()+\s]/g, '').replace(/[KMB]$/, '')); if (!isNaN(n) && /^[\-+(]?\$?[\d,.]+/.test(s)) return neg ? -n : n; return s.toLowerCase(); }
          rows.sort(function (a, b) { var x = val(a), y = val(b); if (x < y) return asc ? -1 : 1; if (x > y) return asc ? 1 : -1; return 0; });
          rows.forEach(function (r) { tb.appendChild(r); });
        });
      });
    });
  }

  function initUi(root) {
    root = root || document;
    if (window.lucide) lucide.createIcons();
    initCharts(root);
  }

  document.addEventListener('click', function (e) {
    var dd = e.target.closest('[data-dropdown]');
    document.querySelectorAll('[data-dropdown].open').forEach(function (d) { if (d !== dd) d.classList.remove('open'); });
    if (dd && e.target.closest('button') && e.target.closest('button').parentNode === dd) dd.classList.toggle('open');
    var m = e.target.closest('[data-modal]');
    if (m) { var el = document.getElementById(m.getAttribute('data-modal')); el && el.classList.add('show'); }
    if (e.target.matches('.modal-bg') || e.target.closest('[data-close]')) { var bg = e.target.closest('.modal-bg'); bg && bg.classList.remove('show'); }
    var ch = e.target.closest('[data-filter]');
    if (ch) {
      var grp = ch.getAttribute('data-filter'), val = ch.getAttribute('data-value');
      document.querySelectorAll('[data-filter="' + grp + '"]').forEach(function (c) { c.classList.toggle('on', c === ch); });
      document.querySelectorAll('[data-' + grp + ']').forEach(function (row) {
        var vals = (row.getAttribute('data-' + grp) || '').split(' ');
        row.style.display = (val === 'all' || vals.indexOf(val) >= 0) ? '' : 'none';
      });
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('.modal-bg.show').forEach(function (m) { m.classList.remove('show'); });
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { var s = document.querySelector('[data-global-search]'); if (s) { e.preventDefault(); s.focus(); } }
  });
  document.addEventListener('htmx:afterSwap', function (e) { initUi(e.target); initSort(); });
  document.addEventListener('htmx:responseError', function (e) { toast('Request failed (' + e.detail.xhr.status + ')', 'err'); });
  document.body && document.body.addEventListener('htmx:afterRequest', function (e) {
    var m = e.detail.xhr && e.detail.xhr.getResponseHeader('HX-Toast'); if (m) toast(m);
  });

  window.addEventListener('DOMContentLoaded', function () {
    initUi(); initTabs(); initSort();
    try { JSON.parse(document.getElementById('flashes').textContent).forEach(function (f, i) { setTimeout(function () { toast(f[1], f[0] === 'error' ? 'err' : ''); }, i * 400); }); } catch (e) { }
    document.querySelectorAll('[data-clock]').forEach(function (el) {
      function tick() { el.textContent = new Date().toLocaleTimeString('en-US', { hour12: false, timeZone: 'America/New_York' }) + ' ET'; }
      tick(); setInterval(tick, 1000);
    });
  });
})();
