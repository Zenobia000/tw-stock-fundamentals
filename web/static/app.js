const API = "/api";

const els = {
  form: document.getElementById("search-form"),
  input: document.getElementById("code-input"),
  results: document.getElementById("search-results"),
  clock: document.getElementById("clock"),
  summary: document.getElementById("summary"),
  grid: document.getElementById("grid"),
  emptyState: document.getElementById("empty-state"),
  errorBanner: document.getElementById("error-banner"),
  rankingsToggle: document.getElementById("rankings-toggle"),
  rankingsView: document.getElementById("rankings-view"),
};

// ---- clock ----
function tickClock() {
  const now = new Date();
  els.clock.textContent = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}
tickClock();
setInterval(tickClock, 1000);

// ---- error banner ----
let errorTimer = null;
function showError(message) {
  els.errorBanner.textContent = message;
  els.errorBanner.classList.remove("hidden");
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => els.errorBanner.classList.add("hidden"), 6000);
}

async function fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `${resp.status} ${resp.statusText}`);
  }
  return resp.json();
}

// ---- search autocomplete ----
let searchDebounce = null;
els.input.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  const q = els.input.value.trim();
  if (!q) {
    els.results.classList.remove("show");
    return;
  }
  searchDebounce = setTimeout(async () => {
    try {
      const rows = await fetchJson(`${API}/stocks/search?q=${encodeURIComponent(q)}`);
      renderSearchResults(rows);
    } catch (e) {
      // silent: autocomplete failures shouldn't interrupt typing
    }
  }, 200);
});

function renderSearchResults(rows) {
  if (!rows.length) {
    els.results.classList.remove("show");
    return;
  }
  els.results.innerHTML = "";
  for (const row of rows) {
    const div = document.createElement("div");
    div.textContent = `${row.code}  ${row.name}  (${row.market || ""})`;
    div.addEventListener("click", () => {
      els.input.value = row.code;
      els.results.classList.remove("show");
      loadStock(row.code);
    });
    els.results.appendChild(div);
  }
  els.results.classList.add("show");
}

document.addEventListener("click", (e) => {
  if (!els.form.contains(e.target)) els.results.classList.remove("show");
});

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const code = els.input.value.trim();
  if (!code) return;
  els.results.classList.remove("show");
  loadStock(code);
});

// ---- number formatting ----
const nf = (digits = 2) => new Intl.NumberFormat("zh-TW", { maximumFractionDigits: digits });
function fmt(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return nf(digits).format(value) + suffix;
}
function fmtPct(value, digits = 2) {
  if (value === null || value === undefined) return "—";
  return nf(digits).format(value) + "%";
}

// ---- tiny canvas chart helpers (no external deps) ----
function clearCanvas(canvas) {
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const cssWidth = canvas.clientWidth || 360;
  const cssHeight = canvas.clientHeight || 140;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  return { ctx, w: cssWidth, h: cssHeight };
}

function drawBarChart(canvas, values, { color = "#ff9f0a", labels = [] } = {}) {
  const { ctx, w, h } = clearCanvas(canvas);
  if (!values.length) {
    ctx.fillStyle = "#7a7a7a";
    ctx.font = "11px Consolas";
    ctx.fillText("無資料", 8, h / 2);
    return;
  }
  const pad = 4;
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const range = max - min || 1;
  const barW = (w - pad * 2) / values.length;
  const zeroY = h - pad - ((0 - min) / range) * (h - pad * 2);

  ctx.strokeStyle = "#2a2a2a";
  ctx.beginPath();
  ctx.moveTo(0, zeroY);
  ctx.lineTo(w, zeroY);
  ctx.stroke();

  values.forEach((v, i) => {
    const x = pad + i * barW;
    const barH = (Math.abs(v) / range) * (h - pad * 2);
    const y = v >= 0 ? zeroY - barH : zeroY;
    ctx.fillStyle = v >= 0 ? color : "#4fd8e8";
    ctx.fillRect(x + 1, y, Math.max(barW - 2, 1), barH || 1);
  });
}

function drawLineChart(canvas, series, { colors = ["#ff9f0a", "#4fd8e8"] } = {}) {
  const { ctx, w, h } = clearCanvas(canvas);
  const allValues = series.flatMap((s) => s.values).filter((v) => v !== null && v !== undefined);
  if (!allValues.length) {
    ctx.fillStyle = "#7a7a7a";
    ctx.font = "11px Consolas";
    ctx.fillText("無資料", 8, h / 2);
    return;
  }
  const pad = 6;
  const max = Math.max(...allValues);
  const min = Math.min(...allValues);
  const range = max - min || 1;

  series.forEach((s, si) => {
    const values = s.values;
    const stepX = (w - pad * 2) / Math.max(values.length - 1, 1);
    ctx.strokeStyle = colors[si % colors.length];
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let started = false;
    values.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const x = pad + i * stepX;
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
  });
}

// ---- panel renderers ----
function renderRevenuePanel(rows) {
  const sorted = [...rows].sort((a, b) => (a.month > b.month ? 1 : -1));
  const recent = sorted.slice(-24);
  drawBarChart(document.getElementById("chart-revenue"), recent.map((r) => r.revenue / 1000));
  const foot = document.getElementById("foot-revenue");
  if (recent.length) {
    const latest = recent[recent.length - 1];
    foot.textContent = `最新 ${latest.month}：${fmt(latest.revenue / 1000, 0)} 百萬`;
  } else {
    foot.textContent = "尚無資料";
  }
}

function renderMarginPanel(rows) {
  const sorted = [...rows].sort((a, b) => (a.quarter > b.quarter ? 1 : -1));
  const recent = sorted.slice(-12);
  drawLineChart(document.getElementById("chart-margin"), [
    { values: recent.map((r) => r.gross_margin_pct) },
    { values: recent.map((r) => r.operating_margin_pct) },
  ]);
  const foot = document.getElementById("foot-margin");
  if (recent.length) {
    const latest = recent[recent.length - 1];
    foot.textContent = `${latest.quarter}　毛利率 ${fmtPct(latest.gross_margin_pct)}　營益率 ${fmtPct(latest.operating_margin_pct)}\n橘=毛利率 青=營益率`;
  } else {
    foot.textContent = "尚無資料";
  }
}

function renderOpexPanel(rows) {
  const sorted = [...rows].sort((a, b) => (a.quarter > b.quarter ? 1 : -1));
  const recent = sorted.slice(-12);
  drawLineChart(document.getElementById("chart-opex"), [
    { values: recent.map((r) => r.operating_cycle_days) },
  ]);
  const foot = document.getElementById("foot-opex");
  if (recent.length) {
    const latest = recent[recent.length - 1];
    foot.textContent = `${latest.quarter}　營運天數 ${fmt(latest.operating_cycle_days, 1)}　(收款 ${fmt(latest.ar_days, 1)} + 存貨 ${fmt(latest.inventory_days, 1)})\n蘭氏核心指標：越低越好`;
  } else {
    foot.textContent = "尚無資料";
  }
}

function renderEpsPanel(rows) {
  const sorted = [...rows].sort((a, b) => (a.quarter > b.quarter ? 1 : -1));
  const recent = sorted.slice(-12);
  drawBarChart(document.getElementById("chart-eps"), recent.map((r) => r.eps));
  const foot = document.getElementById("foot-eps");
  if (recent.length) {
    const latest = recent[recent.length - 1];
    foot.textContent = `最新 ${latest.quarter} EPS：${fmt(latest.eps, 2)} 元`;
  } else {
    foot.textContent = "尚無資料";
  }
}

function renderHealthTable(rows) {
  const table = document.getElementById("table-health");
  if (!rows.length) {
    table.innerHTML = "<tr><td>尚無資料</td></tr>";
    return;
  }
  const latest = rows[0];
  const debtRatio = latest.total_liabilities && latest.total_assets
    ? (latest.total_liabilities / latest.total_assets) * 100
    : null;
  const rowsHtml = [
    ["季別", latest.quarter],
    ["資產總計", fmt(latest.total_assets / 1e6, 1) + " 十億"],
    ["負債總計", fmt(latest.total_liabilities / 1e6, 1) + " 十億"],
    ["負債比率", fmtPct(debtRatio, 1)],
    ["權益總計", fmt(latest.total_equity / 1e6, 1) + " 十億"],
    ["每股淨值", fmt(latest.book_value_per_share, 2)],
    ["毛利率", fmtPct(latest.gross_margin_pct, 1)],
    ["營益率", fmtPct(latest.operating_margin_pct, 1)],
    ["淨利率", fmtPct(latest.net_margin_pct, 1)],
    ["EPS", fmt(latest.eps, 2)],
  ];
  table.innerHTML = rowsHtml.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}

function renderCashflowPanel(rows) {
  const sorted = [...rows].sort((a, b) => (a.quarter > b.quarter ? 1 : -1));
  const recent = sorted.slice(-8);
  drawBarChart(document.getElementById("chart-cashflow"), recent.map((r) => r.operating / 1e6));
  const foot = document.getElementById("foot-cashflow");
  if (recent.length) {
    const latest = recent[recent.length - 1];
    const fcf = (latest.operating || 0) + (latest.investing || 0);
    foot.textContent = `${latest.quarter}　營業現金流 ${fmt(latest.operating / 1e6, 2)} 十億\n約當自由現金流 ${fmt(fcf / 1e6, 2)} 十億`;
  } else {
    foot.textContent = "尚無資料";
  }
}

function renderDividendsTable(rows) {
  const table = document.getElementById("table-dividends");
  if (!rows.length) {
    table.innerHTML = "<tr><td>尚無資料</td></tr>";
    return;
  }
  const header = "<tr><th>年度</th><th>除息日</th><th>現金股利</th><th>殖利率</th></tr>";
  const body = rows
    .slice(0, 8)
    .map(
      (r) =>
        `<tr><td>${r.fiscal_year}</td><td>${r.ex_dividend_date || "—"}</td><td>${fmt(r.cash_dividend, 2)}</td><td>${fmtPct(r.yield_pct, 2)}</td></tr>`
    )
    .join("");
  table.innerHTML = header + body;
}

function renderChipsPanel(rows) {
  const sorted = [...rows].sort((a, b) => (a.date > b.date ? 1 : -1));
  drawLineChart(document.getElementById("chart-chips"), [
    { values: sorted.map((r) => r.foreign_holding_pct) },
    { values: sorted.map((r) => r.big_holder_pct) },
  ]);
  const foot = document.getElementById("foot-chips");
  if (sorted.length) {
    const latest = sorted[sorted.length - 1];
    foot.textContent = `${latest.date}　外資 ${fmtPct(latest.foreign_holding_pct)}　大戶 ${fmtPct(latest.big_holder_pct)}\n橘=外資籌碼 青=大戶籌碼`;
  } else {
    foot.textContent = "尚無資料";
  }
}

function renderFuturesTable(rows) {
  const table = document.getElementById("table-futures");
  if (!rows.length) {
    table.innerHTML = "<tr><td>尚無資料</td></tr>";
    return;
  }
  const header = "<tr><th>身份別</th><th>商品</th><th>多方</th><th>空方</th><th>淨額</th></tr>";
  const body = rows
    .slice(0, 9)
    .map(
      (r) =>
        `<tr><td>${r.institution}</td><td>${r.contract}</td><td>${fmt(r.long_oi, 0)}</td><td>${fmt(r.short_oi, 0)}</td><td class="${r.net_oi >= 0 ? "pos" : "neg"}">${fmt(r.net_oi, 0)}</td></tr>`
    )
    .join("");
  table.innerHTML = header + body;
}

// ---- summary bar ----
function renderSummary(stock) {
  document.getElementById("sum-name").textContent = stock.name || stock.code;
  document.getElementById("sum-code").textContent = stock.code;
  document.getElementById("sum-market").textContent = stock.market || "—";
  document.getElementById("sum-industry").textContent = stock.industry || "—";
  document.getElementById("stat-price").textContent = fmt(stock.price, 1);
  document.getElementById("stat-mcap").textContent = fmt(stock.market_cap_millions, 0);
  document.getElementById("stat-pe").textContent = fmt(stock.pe_ratio, 1);
  document.getElementById("stat-bvps").textContent = fmt(stock.book_value_per_share, 2);
  document.getElementById("stat-beta").textContent = fmt(stock.beta, 2);
  document.getElementById("stat-yield").textContent = fmtPct(stock.dividend_yield_pct, 2);
  document.getElementById("stat-capital").textContent = fmt(stock.capital_billion_twd, 1);
}

function renderDebtStat(healthRows) {
  const el = document.getElementById("stat-debt");
  if (!healthRows.length) {
    el.textContent = "—";
    return;
  }
  const latest = healthRows[0];
  if (!latest.total_liabilities || !latest.total_assets) {
    el.textContent = "—";
    return;
  }
  el.textContent = fmtPct((latest.total_liabilities / latest.total_assets) * 100, 1);
}

function renderTargetPrice(tp) {
  const bar = document.getElementById("target-price-bar");
  if (!tp) {
    bar.classList.add("hidden");
    return;
  }
  bar.classList.remove("hidden");
  document.getElementById("tp-low").textContent = fmt(tp.target_price_low, 0);
  document.getElementById("tp-mid").textContent = fmt(tp.target_price_mid, 0);
  document.getElementById("tp-high").textContent = fmt(tp.target_price_high, 0);
  const noteEl = document.getElementById("tp-note");
  if (tp.note) {
    noteEl.textContent = tp.note;
  } else {
    noteEl.textContent = `估TTM EPS ${fmt(tp.estimated_ttm_eps, 2)}　PE分位 ${fmt(tp.pe_low, 1)}/${fmt(tp.pe_mid, 1)}/${fmt(tp.pe_high, 1)}（樣本${tp.sample_size}季）`;
  }
  if (tp.capital_reduction_applied) {
    noteEl.textContent += "　⚠ 已套用減資校正";
  }
}

// ---- rankings view ----
function renderRankingsTable(rows) {
  const table = document.getElementById("table-rankings");
  if (!rows.length) {
    table.innerHTML = "<tr><td>尚無資料</td></tr>";
    return;
  }
  const header = "<tr><th>#</th><th>代碼</th><th>名稱</th><th>成交值</th><th>收盤價</th></tr>";
  const body = rows
    .map(
      (r) =>
        `<tr><td>${r.rank}</td><td data-code="${r.code}">${r.code}</td><td>${r.name}</td><td>${fmt(r.value / 1e8, 2)} 億</td><td>${fmt(r.closing_price ?? r.value, 1)}</td></tr>`
    )
    .join("");
  table.innerHTML = header + body;
  table.querySelectorAll("td[data-code]").forEach((cell) => {
    cell.addEventListener("click", () => {
      hideRankingsView();
      els.input.value = cell.dataset.code;
      loadStock(cell.dataset.code);
    });
  });
}

function showRankingsView() {
  els.rankingsToggle.classList.add("active");
  els.rankingsView.classList.remove("hidden");
  els.summary.classList.add("hidden");
  els.grid.classList.add("hidden");
  els.emptyState.classList.add("hidden");
  fetchJson(`${API}/rankings/turnover_listed`)
    .then(renderRankingsTable)
    .catch((e) => showError(`排行榜查詢失敗：${e.message}`));
}

function hideRankingsView() {
  els.rankingsToggle.classList.remove("active");
  els.rankingsView.classList.add("hidden");
  if (lastLoadedCode) {
    els.summary.classList.remove("hidden");
    els.grid.classList.remove("hidden");
  } else {
    els.emptyState.classList.remove("hidden");
  }
}

els.rankingsToggle.addEventListener("click", () => {
  if (els.rankingsView.classList.contains("hidden")) {
    showRankingsView();
  } else {
    hideRankingsView();
  }
});

// ---- main load ----
let lastLoadedCode = null;

async function loadStock(code) {
  els.emptyState.classList.add("hidden");
  try {
    const dashboard = await fetchJson(`${API}/stocks/${encodeURIComponent(code)}/dashboard`);
    lastLoadedCode = code;
    els.summary.classList.remove("hidden");
    els.grid.classList.remove("hidden");

    renderSummary(dashboard.stock);
    renderRevenuePanel(dashboard.revenue || []);
    renderMarginPanel(dashboard.margin || []);
    renderOpexPanel(dashboard.opex || []);
    renderEpsPanel(dashboard.eps || []);
    renderHealthTable(dashboard.financial_health || []);
    renderDebtStat(dashboard.financial_health || []);
    renderCashflowPanel(dashboard.cashflow || []);
    renderDividendsTable(dashboard.dividends || []);
    renderChipsPanel(dashboard.chips || []);
    renderTargetPrice(dashboard.target_price || null);

    fetchJson(`${API}/futures`)
      .then(renderFuturesTable)
      .catch(() => renderFuturesTable([]));

    history.replaceState(null, "", `?code=${encodeURIComponent(code)}`);
  } catch (e) {
    showError(`查詢失敗：${e.message}`);
    if (!els.summary.classList.contains("hidden")) return;
    els.emptyState.classList.remove("hidden");
  }
}

// ---- boot: restore code from URL if present ----
const params = new URLSearchParams(window.location.search);
const initialCode = params.get("code");
if (initialCode) {
  els.input.value = initialCode;
  loadStock(initialCode);
}
