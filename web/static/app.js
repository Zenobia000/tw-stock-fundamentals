const API = "/api";

const state = {
  code: null,
  dashboard: null,
  radar: null,
  view: "overview",
  options: {
    revenue_basis: "latest_month",
    gross_margin_basis: "latest_quarter",
    operating_expense_basis: "four_quarter_average",
    non_operating_basis: "four_quarter_average",
    after_tax_basis: "four_quarter_average",
    payout_basis: "historical_average",
    growth_basis: "projected",
    eps_mode: "standard",
  },
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const byId = (id) => document.getElementById(id);
const nf = (digits = 2) => new Intl.NumberFormat("zh-TW", { maximumFractionDigits: digits });

function isValue(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value));
}

function fmt(value, digits = 2, suffix = "") {
  return isValue(value) ? `${nf(digits).format(Number(value))}${suffix}` : "—";
}

function pct(value, digits = 2, alreadyPercent = false) {
  return isValue(value) ? `${nf(digits).format(Number(value) * (alreadyPercent ? 1 : 100))}%` : "—";
}

function escapeHtml(value) {
  return String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

let errorTimer;
function showError(message) {
  const banner = byId("error-banner");
  banner.textContent = message;
  banner.classList.remove("hidden");
  clearTimeout(errorTimer);
  errorTimer = setTimeout(() => banner.classList.add("hidden"), 7000);
}

function setLoading(active) {
  byId("loading").classList.toggle("hidden", !active);
}

function emptyHtml(message = "待補資料源") {
  return `<div class="empty-block compact"><b>尚無可用資料</b><span>${escapeHtml(message)}</span></div>`;
}

function emptyTable(table, columns, message = "待補資料源") {
  table.innerHTML = `<tr><td colspan="${columns}"><div class="table-empty">${escapeHtml(message)}</div></td></tr>`;
}

// Canvas charts are intentionally dependency-free so the research screen works offline.
const COLORS = ["#ffb547", "#51d6d9", "#aa8bff", "#f56c88", "#8fd16a"];

function canvasFrame(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth || 320, 240);
  const height = Number(canvas.getAttribute("height")) || 200;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

function noChartData(ctx, width, height, text = "待補資料源") {
  ctx.fillStyle = "#6f7782";
  ctx.font = "12px system-ui";
  ctx.textAlign = "center";
  ctx.fillText(text, width / 2, height / 2);
}

function chartDomain(series) {
  const values = series.flatMap((item) => item.values || []).filter(isValue).map(Number);
  if (!values.length) return null;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min > 0) min = Math.min(0, min * 0.9);
  if (max < 0) max = Math.max(0, max * 0.9);
  if (min === max) { min -= 1; max += 1; }
  return { min, max };
}

function drawAxes(ctx, width, height, domain, labels, padding) {
  const { left, right, top, bottom } = padding;
  ctx.strokeStyle = "#26303a";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i += 1) {
    const y = top + ((height - top - bottom) * i) / 3;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
    const value = domain.max - ((domain.max - domain.min) * i) / 3;
    ctx.fillStyle = "#66717c"; ctx.font = "10px system-ui"; ctx.textAlign = "right";
    ctx.fillText(nf(Math.abs(value) < 10 ? 1 : 0).format(value), left - 6, y + 3);
  }
  const count = labels.length;
  const labelIndexes = [...new Set([0, Math.floor((count - 1) / 2), count - 1])];
  ctx.textAlign = "center"; ctx.fillStyle = "#66717c";
  labelIndexes.forEach((index) => {
    if (index < 0 || !labels[index]) return;
    const x = left + ((width - left - right) * index) / Math.max(count - 1, 1);
    ctx.fillText(String(labels[index]).replace(/^20/, ""), x, height - 5);
  });
}

function drawChart(canvas, series, labels = [], { bars = [], zeroBased = false, rightAxis = [] } = {}) {
  const { ctx, width, height } = canvasFrame(canvas);
  const leftDomain = chartDomain(series.filter((_, index) => !rightAxis.includes(index)));
  const rightDomain = chartDomain(series.filter((_, index) => rightAxis.includes(index)));
  const domain = leftDomain || rightDomain;
  if (!domain) { noChartData(ctx, width, height); return; }
  if (zeroBased && domain.min > 0) domain.min = 0;
  const hasDualAxis = Boolean(leftDomain && rightDomain);
  const padding = { left: 45, right: hasDualAxis ? 42 : 10, top: 10, bottom: 25 };
  drawAxes(ctx, width, height, domain, labels, padding);
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const yOf = (value, itemDomain = domain) => padding.top + ((itemDomain.max - Number(value)) / (itemDomain.max - itemDomain.min)) * plotH;
  const maxLength = Math.max(...series.map((item) => item.values.length), 1);
  const xOf = (index) => padding.left + (plotW * index) / Math.max(maxLength - 1, 1);

  if (hasDualAxis) {
    ctx.fillStyle = "#66717c"; ctx.font = "10px system-ui"; ctx.textAlign = "left";
    for (let i = 0; i <= 3; i += 1) {
      const y = padding.top + (plotH * i) / 3;
      const value = rightDomain.max - ((rightDomain.max - rightDomain.min) * i) / 3;
      ctx.fillText(nf(Math.abs(value) < 10 ? 1 : 0).format(value), width - padding.right + 6, y + 3);
    }
  }

  series.forEach((item, seriesIndex) => {
    const color = item.color || COLORS[seriesIndex % COLORS.length];
    const itemDomain = hasDualAxis && rightAxis.includes(seriesIndex) ? rightDomain : domain;
    const zeroY = yOf(0, itemDomain);
    if (bars.includes(seriesIndex)) {
      const barWidth = Math.max(2, (plotW / Math.max(maxLength, 1)) * 0.62);
      item.values.forEach((value, index) => {
        if (!isValue(value)) return;
        const y = yOf(value, itemDomain);
        ctx.fillStyle = Number(value) >= 0 ? color : "#51d6d9";
        ctx.globalAlpha = 0.78;
        ctx.fillRect(xOf(index) - barWidth / 2, Math.min(y, zeroY), barWidth, Math.max(Math.abs(zeroY - y), 1));
      });
      ctx.globalAlpha = 1;
      return;
    }
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    let started = false;
    item.values.forEach((value, index) => {
      if (!isValue(value)) { started = false; return; }
      const x = xOf(index); const y = yOf(value, itemDomain);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    });
    ctx.stroke();
  });
}

function drawCandles(canvas, priceRows) {
  const rows = chronological(priceRows, "date").slice(-80);
  const { ctx, width, height } = canvasFrame(canvas);
  const valid = rows.filter((row) => [row.open, row.high, row.low, row.close].every(isValue));
  if (!valid.length) { noChartData(ctx, width, height, "待補歷史日股價資料源"); return; }
  const domain = { min: Math.min(...valid.map((row) => Number(row.low))), max: Math.max(...valid.map((row) => Number(row.high))) };
  if (domain.min === domain.max) { domain.min -= 1; domain.max += 1; }
  const padding = { left: 45, right: 10, top: 10, bottom: 25 };
  drawAxes(ctx, width, height, domain, rows.map((row) => row.date), padding);
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const step = plotW / Math.max(rows.length, 1);
  const bodyWidth = Math.max(2, step * .62);
  const yOf = (value) => padding.top + ((domain.max - Number(value)) / (domain.max - domain.min)) * plotH;
  rows.forEach((row, index) => {
    if (![row.open, row.high, row.low, row.close].every(isValue)) return;
    const x = padding.left + step * index + step / 2;
    const rising = Number(row.close) >= Number(row.open);
    ctx.strokeStyle = rising ? "#f56c88" : "#8fd16a";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath(); ctx.moveTo(x, yOf(row.high)); ctx.lineTo(x, yOf(row.low)); ctx.stroke();
    const yOpen = yOf(row.open); const yClose = yOf(row.close);
    ctx.fillRect(x - bodyWidth / 2, Math.min(yOpen, yClose), bodyWidth, Math.max(Math.abs(yOpen - yClose), 1));
  });
}

function chronological(rows, key) {
  return [...(rows || [])].sort((a, b) => String(a[key]).localeCompare(String(b[key])));
}

function renderStockHeader(stock) {
  byId("stock-name").textContent = stock.name || stock.code;
  byId("stock-code").textContent = stock.code;
  byId("stock-market").textContent = stock.market || "市場待補";
  byId("stock-industry").textContent = stock.industry || "產業待補";
  byId("stat-price").textContent = fmt(stock.price, 2);
  byId("stat-pe").textContent = fmt(stock.pe_ratio, 2);
  byId("stat-yield").textContent = pct(stock.dividend_yield_pct, 2, true);
  byId("stat-bvps").textContent = fmt(stock.book_value_per_share, 2);
  byId("stat-mcap").textContent = fmt(stock.market_cap_millions, 0);
  byId("stat-time").textContent = (stock.stock_info_fetched_at || stock.updated_at || "—").replace("T", " ").slice(0, 16);
}

function renderCoverage(decision) {
  const coverage = decision.coverage || {};
  const parts = [
    ["月營收", coverage.revenue_months, "筆"],
    ["損益季數", coverage.income_statement_quarters, "季"],
    ["PE 樣本", coverage.pe_samples, "筆"],
    ["PE 方法", coverage.pe_method === "five_year_monthly" ? "五年月資料" : "季資料暫代", ""],
    ["詳細損益", coverage.detailed_income_statement ? "完整" : "推估中", ""],
  ];
  byId("coverage-strip").innerHTML = parts.map(([label, value, suffix]) => `<div><span>${label}</span><b>${escapeHtml(value ?? "—")}${suffix}</b></div>`).join("");
  byId("decision-warnings").innerHTML = (decision.warnings || []).map((warning) => `<div class="notice">${escapeHtml(warning)}</div>`).join("");
}

function renderDecision(decision) {
  renderCoverage(decision);
  const empty = byId("decision-empty");
  const content = byId("decision-content");
  if (!decision.available || !decision.result) {
    empty.innerHTML = `<b>目前無法執行完整估值</b><span>${escapeHtml((decision.warnings || ["資料不足"])[0])}</span>`;
    empty.classList.remove("hidden"); content.classList.add("hidden");
    byId("formula-version").textContent = "資料待補";
    return;
  }
  empty.classList.add("hidden"); content.classList.remove("hidden");
  const result = decision.result;
  byId("formula-version").textContent = result.formula_version;
  byId("metric-current-target").textContent = fmt(result.current_pe_target_price, 0);
  byId("metric-ttm-eps").textContent = fmt(result.estimated_ttm_eps, 2);
  byId("metric-current-eps").textContent = `目前 TTM ${fmt(result.current_ttm_eps, 2)} 元`;
  byId("metric-dividend").textContent = fmt(result.estimated_cash_dividend, 2);
  byId("metric-dividend-yield").textContent = `殖利率 ${pct(result.estimated_dividend_yield)}`;
  byId("metric-peg").textContent = fmt(result.peg, 3);
  byId("metric-total-score").textContent = `總報酬本益比 ${fmt(result.total_return_pe_score, 3)}`;

  const chain = [
    ["季度營收", result.estimated_quarterly_revenue],
    ["毛利", result.estimated_gross_profit, pct(result.selected_gross_margin_ratio)],
    ["營業利益", result.estimated_operating_income, `費用 ${fmt(result.selected_operating_expense, 0)}`],
    ["稅前淨利", result.estimated_pretax_income, `業外 ${fmt(result.selected_non_operating_income, 0)}`],
    ["稅後淨利", result.estimated_net_income, `保留率 ${pct(result.selected_after_tax_retention_ratio)}`],
    ["母公司淨利", result.estimated_parent_net_income, `非控制 ${fmt(result.selected_noncontrolling_income, 0)}`],
    ["季度 EPS", result.estimated_quarterly_eps, result.capital_reduction_applied ? "已做減資校正" : "一般模式"],
  ];
  byId("valuation-chain").innerHTML = chain.map(([label, value, note], index) => `<div class="chain-node"><span>${String(index + 1).padStart(2, "0")} ${label}</span><b>${fmt(value, index === 6 ? 2 : 0)}</b><small>${escapeHtml(note || "")}</small></div>${index < chain.length - 1 ? '<i aria-hidden="true">→</i>' : ""}`).join("");

  const levels = result.pe_river?.levels || {};
  const rows = [-3, -2, -1, 0, 1, 2, 3].map((step) => {
    const key = `${step >= 0 ? "+" : ""}${step}sigma`;
    const pe = levels[key];
    const target = result.pe_target_prices?.[key];
    return `<tr class="${step === 0 ? "mean-row" : ""}"><td>${step === 0 ? "平均" : `${step > 0 ? "+" : ""}${step}σ`}</td><td>${fmt(pe, 2)}</td><td>${fmt(target, 0)}</td></tr>`;
  }).join("");
  byId("pe-river-table").innerHTML = result.pe_river
    ? `<thead><tr><th>河流層級</th><th>PE</th><th>目標價</th></tr></thead><tbody>${rows}</tbody><tfoot><tr><td>母體標準差</td><td colspan="2">${fmt(result.pe_river.population_stdev, 3)}</td></tr></tfoot>`
    : `<tr><td>${emptyHtml("需補五年月 PE")}</td></tr>`;
}

function renderFundamentals(data) {
  const revenue = chronological(data.revenue, "month").slice(-36);
  drawChart(byId("chart-revenue"), [
    { values: revenue.map((row) => isValue(row.revenue) ? row.revenue / 1000 : null) },
    { values: revenue.map((row) => row.signal?.near_3m_avg ? row.signal.near_3m_avg / 1000 : null) },
  ], revenue.map((row) => row.month), { bars: [0] });
  const latestRevenue = revenue.at(-1);
  byId("revenue-caption").textContent = latestRevenue ? `${latestRevenue.month}｜${fmt(latestRevenue.revenue / 1000, 0)} 百萬` : "待補資料";

  const profits = chronological(data.profitability, "quarter").slice(-12);
  drawChart(byId("chart-profitability"), [
    { values: profits.map((row) => row.gross_margin_pct) },
    { values: profits.map((row) => row.operating_margin_pct) },
    { values: profits.map((row) => row.revenue ? row.net_income / row.revenue * 100 : null) },
  ], profits.map((row) => row.quarter));
  const epsRows = chronological(data.eps?.length ? data.eps : data.profitability, "quarter").slice(-12);
  drawChart(byId("chart-eps"), [{ values: epsRows.map((row) => row.eps) }], epsRows.map((row) => row.quarter), { bars: [0] });

  const tableRows = (data.income_statement?.length ? data.income_statement : data.profitability || []).slice(0, 12);
  const table = byId("income-table");
  if (!tableRows.length) { emptyTable(table, 8); return; }
  table.innerHTML = `<thead><tr><th>季別</th><th>營收</th><th>毛利</th><th>營業費用</th><th>營業利益</th><th>業外</th><th>母公司淨利</th><th>EPS</th></tr></thead><tbody>${tableRows.map((row) => `<tr><td>${escapeHtml(row.quarter)}</td><td>${fmt(row.revenue, 0)}</td><td>${fmt(row.gross_profit, 0)}</td><td>${fmt(row.operating_expense, 0)}</td><td>${fmt(row.operating_income, 0)}</td><td>${fmt(row.non_operating_income, 0)}</td><td>${fmt(row.parent_net_income ?? row.net_income, 0)}</td><td>${fmt(row.eps, 2)}</td></tr>`).join("")}</tbody>`;
}

function renderQuality(data) {
  const efficiency = chronological(data.efficiency, "quarter").slice(-12);
  drawChart(byId("chart-efficiency"), [
    { values: efficiency.map((row) => row.ar_days) },
    { values: efficiency.map((row) => row.inventory_days) },
    { values: efficiency.map((row) => row.operating_cycle_days) },
  ], efficiency.map((row) => row.quarter));
  const cash = chronological(data.cashflow, "quarter").slice(-12);
  drawChart(byId("chart-cashflow"), [
    { values: cash.map((row) => isValue(row.operating) ? row.operating / 1e6 : null) },
    { values: cash.map((row) => isValue(row.investing) ? row.investing / 1e6 : null) },
    { values: cash.map((row) => isValue(row.financing) ? row.financing / 1e6 : null) },
    { values: cash.map((row) => isValue(row.free_cash_flow) ? row.free_cash_flow / 1e6 : null) },
  ], cash.map((row) => row.quarter));

  const health = data.balance_sheet?.[0] || data.financial_health?.[0];
  const healthTable = byId("health-table");
  if (!health) { healthTable.innerHTML = `<tr><td>${emptyHtml()}</td></tr>`; }
  else {
    const debt = health.total_assets ? health.total_liabilities / health.total_assets : null;
    const items = [
      ["季別", health.quarter], ["總資產", fmt(health.total_assets, 0)], ["總負債", fmt(health.total_liabilities, 0)],
      ["負債比率", pct(debt)], ["股東權益", fmt(health.total_equity, 0)], ["每股淨值", fmt(health.book_value_per_share, 2)],
      ["ROE（年化）", pct(health.roe_ratio)], ["合約負債", fmt(health.contract_liabilities, 0)],
    ];
    healthTable.innerHTML = items.map(([key, value]) => `<tr><th>${key}</th><td>${escapeHtml(value)}</td></tr>`).join("");
  }

  const annualDividends = data.annual_dividends || [];
  const dividends = data.dividends || [];
  const dividendTable = byId("dividend-table");
  if (annualDividends.length) {
    dividendTable.innerHTML = `<thead><tr><th>年度</th><th>年度現金股利</th><th>發放率</th><th>殖利率</th><th>來源</th></tr></thead><tbody>${annualDividends.slice(0, 10).map((row) => `<tr><td>${row.fiscal_year}</td><td>${fmt(row.cash_dividend, 3)}</td><td>${pct(row.payout_ratio)}</td><td>${pct(row.yield_ratio)}</td><td>${escapeHtml(row.source)}</td></tr>`).join("")}</tbody>`;
  } else if (dividends.length) {
    dividendTable.innerHTML = `<thead><tr><th>年度</th><th>除息日</th><th>現金</th><th>股票</th><th>配發率</th><th>殖利率</th></tr></thead><tbody>${dividends.slice(0, 12).map((row) => `<tr><td>${row.fiscal_year}</td><td>${escapeHtml(row.ex_dividend_date)}</td><td>${fmt(row.cash_dividend, 2)}</td><td>${fmt(row.stock_dividend, 2)}</td><td>${pct(row.payout_ratio_pct, 1, true)}</td><td>${pct(row.yield_pct, 2, true)}</td></tr>`).join("")}</tbody>`;
  } else {
    emptyTable(dividendTable, 6);
  }

  const events = data.events || [];
  const reduction = data.capital_reduction;
  const reductionHtml = reduction ? `<article><time>${escapeHtml(reduction.resume_date || "日期待補")}</time><div><b>減資校正：${escapeHtml(reduction.name)}</b><p>EPS 校正因子 ${fmt(reduction.adjust_factor, 6)}；僅在模型選擇「減資校正」時套用。</p></div></article>` : "";
  const eventHtml = events.map((event) => `<article><time>${escapeHtml(event.event_date)}</time><div><b>${escapeHtml(event.title)}</b><p>${escapeHtml(event.detail || event.event_type)}</p></div></article>`).join("");
  byId("event-list").innerHTML = reductionHtml || eventHtml ? reductionHtml + eventHtml : emptyHtml("待補重大事件與減資歷史");
}

function cashflowClass(row) {
  const op = row.operating_cashflow_millions;
  const inv = row.investing_cashflow_millions;
  const fin = row.financing_cashflow_millions;
  if (![op, inv, fin].every(isValue)) return { label: "資料不足", tone: "neutral" };
  if (op > 0 && inv < 0 && fin < 0) return { label: "成熟／還債型", tone: "good" };
  if (op > 0 && inv < 0 && fin > 0) return { label: "擴張型", tone: "watch" };
  if (op < 0 && fin > 0) return { label: "籌資支撐型", tone: "risk" };
  if (op > 0 && inv > 0) return { label: "收縮／處分型", tone: "watch" };
  return { label: "混合型", tone: "neutral" };
}

function signalLabel(value) {
  const map = {
    red: ["改善", "rise"], green: ["轉弱", "fall"],
    improving: ["改善", "rise"], deteriorating: ["轉弱", "fall"],
    stable: ["持平", "neutral"], insufficient: ["待補", "neutral"],
  };
  const [text, tone] = map[value] || [value || "待補", "neutral"];
  return `<em class="signal ${tone}">${text}</em>`;
}

function renderNineGrid(data) {
  const rows = chronological(data.quarterly, "quarter");
  const labels = rows.map((row) => row.quarter);
  $$('[data-signal]').forEach((node) => { node.innerHTML = signalLabel(data.signals?.[node.dataset.signal]); });
  byId("nine-signals").innerHTML = Object.entries(data.signals || {}).map(([key, value]) => `<div><span>${escapeHtml(key.replaceAll("_", " "))}</span>${signalLabel(value)}</div>`).join("");
  drawChart(byId("ng-profit"), [
    { values: rows.map((row) => row.revenue_millions) },
    { values: rows.map((row) => isValue(row.gross_margin_ratio) ? row.gross_margin_ratio * 100 : null) },
    { values: rows.map((row) => isValue(row.operating_margin_ratio) ? row.operating_margin_ratio * 100 : null) },
  ], labels, { bars: [0], rightAxis: [1, 2] });
  drawChart(byId("ng-days"), [
    { values: rows.map((row) => row.ar_days) }, { values: rows.map((row) => row.inventory_days) }, { values: rows.map((row) => row.payable_days) },
  ], labels);
  drawChart(byId("ng-debt"), [
    { values: rows.map((row) => row.cash_and_securities) },
    { values: rows.map((row) => isValue(row.debt_ratio) ? row.debt_ratio * 100 : null) },
  ], labels, { bars: [0], rightAxis: [1] });
  drawChart(byId("ng-cash-profit"), [
    { values: rows.map((row) => isValue(row.operating_cashflow_millions) ? row.operating_cashflow_millions / 1000 : null) },
    { values: rows.map((row) => isValue(row.operating_income_millions) ? row.operating_income_millions / 1000 : null) },
    { values: rows.map((row) => isValue(row.roe_ratio) ? row.roe_ratio * 100 : null) },
  ], labels, { rightAxis: [2] });
  drawChart(byId("ng-lan"), [
    { values: rows.map((row) => isValue(row.capital_expenditure_millions) ? row.capital_expenditure_millions / 1000 : null) },
    { values: rows.map((row) => row.lan_value) },
  ], labels, { bars: [0], rightAxis: [1] });
  drawChart(byId("ng-core-eps"), [
    { values: rows.map((row) => row.core_eps) }, { values: rows.map((row) => row.non_core_eps) },
  ], labels, { bars: [0, 1] });
  const current4 = rows.slice(-4);
  const prior4 = rows.slice(-8, -4);
  drawChart(byId("ng-season-revenue"), [
    { values: current4.map((row) => row.revenue_millions) }, { values: prior4.map((row) => row.revenue_millions) },
  ], current4.map((_, index) => `Q${index + 1}`));
  drawChart(byId("ng-season-days"), [
    { values: current4.map((row) => row.operating_cycle_days) }, { values: prior4.map((row) => row.operating_cycle_days) },
  ], current4.map((_, index) => `Q${index + 1}`));

  byId("ng-cash-class").innerHTML = rows.length ? rows.slice(-4).map((row) => {
    const classification = cashflowClass(row);
    return `<div><span>${escapeHtml(row.quarter)}</span><b class="${classification.tone}">${classification.label}</b><small>營 ${fmt(row.operating_cashflow_millions, 0)}／投 ${fmt(row.investing_cashflow_millions, 0)}／融 ${fmt(row.financing_cashflow_millions, 0)}</small></div>`;
  }).join("") : emptyHtml();

  const monthly = chronological(data.monthly_revenue, "month");
  drawChart(byId("ng-bollinger"), [
    { values: monthly.map((row) => row.revenue_millions) }, { values: monthly.map((row) => row.near_3m_avg) },
    { values: monthly.map((row) => row.upper_band) }, { values: monthly.map((row) => row.lower_band) },
  ], monthly.map((row) => row.month));
  drawChart(byId("ng-contract"), [{ values: rows.map((row) => row.contract_liabilities) }], labels, { bars: [0] });
  drawCandles(byId("ng-price"), data.daily_prices || []);
}

function tableFromRows(table, rows, columns, message) {
  if (!rows?.length) { emptyTable(table, columns.length, message); return; }
  table.innerHTML = `<thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td class="${column.className ? column.className(row) : ""}">${column.format ? column.format(row[column.key], row) : escapeHtml(row[column.key])}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

function renderMarket(chips, radar) {
  const holdings = chronological(chips.holdings, "date");
  drawChart(byId("chart-holdings"), [
    { values: holdings.map((row) => row.foreign_holding_pct) },
    { values: holdings.map((row) => row.big_holder_pct) },
    { values: holdings.map((row) => row.concentration_pct) },
  ], holdings.map((row) => row.date));
  tableFromRows(byId("futures-table"), radar.futures, [
    { key: "institution", label: "身份" }, { key: "contract", label: "商品" },
    { key: "long_oi", label: "多", format: (v) => fmt(v, 0) }, { key: "short_oi", label: "空", format: (v) => fmt(v, 0) },
    { key: "net_oi", label: "淨額", format: (v) => fmt(v, 0), className: (row) => row.net_oi >= 0 ? "positive" : "negative" },
  ], "待補 TAIFEX 未平倉資料");
  tableFromRows(byId("institution-table"), chips.institutional_trading?.slice(0, 30), [
    { key: "date", label: "日期" }, { key: "institution", label: "法人" }, { key: "buy", label: "買進", format: (v) => fmt(v, 0) },
    { key: "sell", label: "賣出", format: (v) => fmt(v, 0) }, { key: "net", label: "淨額", format: (v) => fmt(v, 0) },
  ], "待補法人個股買賣超資料");
  tableFromRows(byId("margin-short-table"), chips.margin_short?.slice(0, 30), [
    { key: "date", label: "日期" }, { key: "margin_balance", label: "融資", format: (v) => fmt(v, 0) },
    { key: "short_balance", label: "融券", format: (v) => fmt(v, 0) }, { key: "short_margin_ratio", label: "券資比", format: (v) => pct(v, 2, true) },
  ], "待補融資融券資料");
  tableFromRows(byId("broker-table"), chips.broker_branches?.slice(0, 30), [
    { key: "date", label: "日期" }, { key: "branch", label: "分點" }, { key: "buy", label: "買", format: (v) => fmt(v, 0) },
    { key: "sell", label: "賣", format: (v) => fmt(v, 0) }, { key: "net", label: "淨", format: (v) => fmt(v, 0) },
  ], "待補券商分點資料");
  tableFromRows(byId("etf-table"), chips.etf_holdings?.slice(0, 30), [
    { key: "as_of_date", label: "日期" }, { key: "etf_code", label: "ETF" }, { key: "etf_name", label: "名稱" },
    { key: "holding_ratio", label: "權重", format: (v) => pct(v) },
  ], "待補 ETF 成分持股資料");
  tableFromRows(byId("market-cap-table"), radar.market_cap?.slice(0, 50), [
    { key: "rank", label: "#" }, { key: "code", label: "代碼" },
    { key: "name", label: "名稱" },
    { key: "pct_of_market", label: "大盤比重", format: (v) => pct(v, 3) },
    { key: "date", label: "資料日期" },
  ], "待補全市場流通股本與市值資料源");
  renderRanking(radar);
}

function renderRanking(radar = state.radar) {
  const category = byId("ranking-category").value;
  const rows = radar?.rankings?.[category] || [];
  tableFromRows(byId("ranking-table"), rows.slice(0, 50), [
    { key: "rank", label: "#" }, { key: "code", label: "代碼" }, { key: "name", label: "名稱" },
    { key: "value", label: "數值", format: (v) => fmt(v, 2) }, { key: "date", label: "日期" },
  ], "待補排行榜資料");
  $$("#ranking-table tbody tr").forEach((row, index) => {
    const code = rows[index]?.code;
    if (!code) return;
    row.classList.add("clickable");
    row.addEventListener("click", () => { byId("code-input").value = code; loadStock(code); });
  });
}

function renderDashboard(dashboard, radar) {
  renderStockHeader(dashboard.stock);
  renderDecision(dashboard.decision);
  renderFundamentals(dashboard.fundamentals);
  renderQuality(dashboard.financial_quality);
  renderNineGrid(dashboard.nine_grid);
  renderMarket(dashboard.chips_market, radar);
}

function optionsQuery() {
  return new URLSearchParams(state.options).toString();
}

async function loadStock(code, { modelOnly = false } = {}) {
  const normalized = String(code).trim();
  if (!normalized) return;
  setLoading(true);
  try {
    const dashboard = await fetchJson(`${API}/stocks/${encodeURIComponent(normalized)}/dashboard-v2?${optionsQuery()}`);
    if (!modelOnly || !state.dashboard) {
      state.radar = state.radar || await fetchJson(`${API}/market/radar`).catch(() => ({ futures: [], rankings: {} }));
      state.dashboard = dashboard;
      state.code = normalized;
      renderDashboard(dashboard, state.radar);
      byId("empty-state").classList.add("hidden");
      byId("stock-header").classList.remove("hidden");
      byId("workspace-nav").classList.remove("hidden");
      byId("workspace").classList.remove("hidden");
      history.replaceState(null, "", `?code=${encodeURIComponent(normalized)}&view=${state.view}`);
    } else {
      state.dashboard.decision = dashboard.decision;
      renderDecision(dashboard.decision);
    }
  } catch (error) {
    showError(`查詢失敗：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function switchView(view) {
  state.view = view;
  $$(".nav-tab").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  $$('[data-view-panel]').forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === view));
  if (state.code) history.replaceState(null, "", `?code=${encodeURIComponent(state.code)}&view=${view}`);
  requestAnimationFrame(() => { if (state.dashboard) renderDashboard(state.dashboard, state.radar || { futures: [], rankings: {} }); });
  window.scrollTo({ top: byId("workspace-nav").offsetTop - 60, behavior: "smooth" });
}

// Search and navigation
let searchTimer;
byId("code-input").addEventListener("input", () => {
  clearTimeout(searchTimer);
  const query = byId("code-input").value.trim();
  if (!query) { byId("search-results").classList.remove("show"); return; }
  searchTimer = setTimeout(async () => {
    try {
      const rows = await fetchJson(`${API}/stocks/search?q=${encodeURIComponent(query)}`);
      const box = byId("search-results");
      box.innerHTML = rows.map((row) => `<button type="button" data-code="${escapeHtml(row.code)}"><b>${escapeHtml(row.code)}</b><span>${escapeHtml(row.name)}</span><small>${escapeHtml(row.market || "")}</small></button>`).join("");
      box.classList.toggle("show", rows.length > 0);
      $$("button", box).forEach((button) => button.addEventListener("click", () => {
        byId("code-input").value = button.dataset.code; box.classList.remove("show"); loadStock(button.dataset.code);
      }));
    } catch (_) { byId("search-results").classList.remove("show"); }
  }, 180);
});

byId("search-form").addEventListener("submit", (event) => {
  event.preventDefault(); byId("search-results").classList.remove("show"); loadStock(byId("code-input").value);
});
document.addEventListener("click", (event) => { if (!byId("search-form").contains(event.target)) byId("search-results").classList.remove("show"); });
$$('.nav-tab').forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$$('[data-option]').forEach((select) => select.addEventListener("change", () => {
  state.options[select.dataset.option] = select.value;
  if (state.code) loadStock(state.code, { modelOnly: true });
}));
byId("ranking-category").addEventListener("change", () => renderRanking());

const drawer = byId("method-drawer");
byId("method-toggle").addEventListener("click", () => drawer.classList.toggle("hidden"));
byId("method-close").addEventListener("click", () => drawer.classList.add("hidden"));

function tickClock() {
  byId("clock").textContent = new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
tickClock(); setInterval(tickClock, 1000);

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (state.dashboard) renderDashboard(state.dashboard, state.radar || { futures: [], rankings: {} }); }, 150);
});

const params = new URLSearchParams(window.location.search);
const initialView = params.get("view");
if (["overview", "fundamentals", "quality", "nine-grid", "market"].includes(initialView)) switchView(initialView);
const initialCode = params.get("code");
if (initialCode) { byId("code-input").value = initialCode; loadStock(initialCode); }
