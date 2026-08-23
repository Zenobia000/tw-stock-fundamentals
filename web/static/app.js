const API = "/api";

const state = {
  code: null,
  dashboard: null,
  radar: null,
  marketOverview: null,
  marketOverviewActive: false,
  indexComparisonActive: false,
  indexComparisonScale: "percent",
  indexComparisonRange: "30",
  indexComparisonHidden: new Set(),
  stockRankings: null,
  stockRankingsTab: "top_gainers",
  industryRankings: null,
  industryRankingsTab: "top_gainers",
  valuationBenchmark: null,
  view: "overview",
  rankingTopic: "turnover",
  rankingMarket: "listed",
  health: null,
  healthEndpoints: [],
  healthTab: "datasets",
  apiMetrics: {},
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
  return isValue(value) ? `${nf(digits).format(Number(value))}${suffix}` : "-";
}

function pct(value, digits = 2, alreadyPercent = false) {
  return isValue(value) ? `${nf(digits).format(Number(value) * (alreadyPercent ? 1 : 100))}%` : "-";
}

function signedPct(value, digits = 1) {
  return isValue(value) ? `${Number(value) >= 0 ? "+" : "-"}${pct(Math.abs(Number(value)), digits)}` : "-";
}

function escapeHtml(value) {
  return String(value ?? "-")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function fetchJson(url, options = {}) {
  const started = performance.now();
  const method = String(options.method || "GET").toUpperCase();
  const path = new URL(url, window.location.origin).pathname;
  let recorded = false;
  try {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({}));
    recordApiMetric(method, path, response.status, response.ok, performance.now() - started);
    recorded = true;
    if (!response.ok) {
      const error = new Error(body.detail || `${response.status} ${response.statusText}`);
      error.status = response.status;
      throw error;
    }
    return body;
  } catch (error) {
    if (!recorded) recordApiMetric(method, path, error.status || 0, false, performance.now() - started);
    throw error;
  }
}

function recordApiMetric(method, path, status, ok, durationMs) {
  const key = `${method} ${path}`;
  const metric = state.apiMetrics[key] || {
    method, path, count: 0, successCount: 0, errorCount: 0, totalMs: 0, lastStatus: null, lastAt: null,
  };
  metric.count += 1;
  metric.successCount += ok ? 1 : 0;
  metric.errorCount += ok ? 0 : 1;
  metric.totalMs += durationMs;
  metric.lastStatus = status;
  metric.lastAt = new Date().toISOString();
  state.apiMetrics[key] = metric;
  if (state.healthTab === "api" && state.healthEndpoints.length) renderHealthApi();
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

// 全站共用的「更多」抽屜面板 — 各卡片只負責準備 title/bodyHtml，開關與畫面
// 結構統一在這裡處理，不用每個卡片各自刻一份 modal。
function openDrawer(title, bodyHtml) {
  byId("detail-drawer-title").textContent = title;
  byId("detail-drawer-body").innerHTML = bodyHtml;
  byId("detail-drawer").classList.remove("hidden");
}
function closeDrawer() {
  byId("detail-drawer").classList.add("hidden");
}
byId("detail-drawer-close").addEventListener("click", closeDrawer);
byId("detail-drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

// Canvas charts are dependency-free and share one interaction/legend layer.
const COLORS = ["#a98256", "#6f9193", "#817991", "#9d686f", "#678473"];
const chartTooltip = document.createElement("div");
chartTooltip.className = "chart-tooltip hidden";
document.body.appendChild(chartTooltip);

function chartValue(item, value) {
  if (!isValue(value)) return "-";
  if (item.format) return item.format(Number(value));
  return fmt(value, item.digits ?? 2, item.suffix || "");
}

function updateChartLegend(canvas, series) {
  const named = series.filter((item) => item.name);
  let legend = canvas.parentElement.querySelector(`[data-chart-legend="${canvas.id}"]`);
  if (!named.length) {
    if (legend) legend.remove();
    return;
  }
  if (!legend) {
    legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.dataset.chartLegend = canvas.id;
    canvas.insertAdjacentElement("afterend", legend);
  }
  legend.innerHTML = named.map((item, index) => {
    const color = item.color || COLORS[series.indexOf(item) % COLORS.length];
    return `<span><i style="--legend-color:${color}"></i>${escapeHtml(item.name)}</span>`;
  }).join("");
}

function installChartInteraction(canvas, meta) {
  canvas._chartMeta = meta;
  if (canvas.dataset.chartInteractive) return;
  canvas.dataset.chartInteractive = "true";
  const crosshair = document.createElement("i");
  crosshair.className = "chart-crosshair hidden";
  canvas.insertAdjacentElement("afterend", crosshair);
  const show = (event) => {
    const current = canvas._chartMeta;
    if (!current?.labels?.length) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const { left, right } = current.padding;
    if (x < left || x > rect.width - right) {
      chartTooltip.classList.add("hidden");
      crosshair.classList.add("hidden");
      return;
    }
    const plotWidth = Math.max(rect.width - left - right, 1);
    const count = current.labels.length;
    const relativeX = (x - left) / plotWidth;
    const rawIndex = current.banded
      ? Math.floor(relativeX * count)
      : Math.round(relativeX * Math.max(count - 1, 1));
    const index = Math.max(0, Math.min(count - 1, rawIndex));
    const nearestX = chartX(index, count, left, plotWidth, current.banded);
    crosshair.style.left = `${canvas.offsetLeft + nearestX}px`;
    crosshair.style.top = `${canvas.offsetTop + current.padding.top}px`;
    crosshair.style.height = `${canvas.clientHeight - current.padding.top - current.padding.bottom}px`;
    crosshair.classList.remove("hidden");
    const values = current.series
      .map((item, seriesIndex) => ({ item, seriesIndex, value: item.values[index] }))
      .filter(({ value }) => isValue(value));
    if (!values.length) {
      chartTooltip.classList.add("hidden");
      return;
    }
    chartTooltip.innerHTML = `<b>${escapeHtml(current.labels[index])}</b>${values.map(({ item, seriesIndex, value }) => {
      const color = item.color || COLORS[seriesIndex % COLORS.length];
      return `<span><i style="--tooltip-color:${color}"></i><em>${escapeHtml(item.name || `數列 ${seriesIndex + 1}`)}</em><strong>${escapeHtml(chartValue(item, value))}</strong></span>`;
    }).join("")}`;
    chartTooltip.classList.remove("hidden");
    const tooltipRect = chartTooltip.getBoundingClientRect();
    chartTooltip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - tooltipRect.width - 10)}px`;
    chartTooltip.style.top = `${Math.max(10, Math.min(event.clientY + 14, window.innerHeight - tooltipRect.height - 10))}px`;
  };
  canvas.addEventListener("pointermove", show);
  canvas.addEventListener("pointerdown", show);
  canvas.addEventListener("pointerleave", () => {
    chartTooltip.classList.add("hidden");
    crosshair.classList.add("hidden");
  });
}

function canvasFrame(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(canvas.clientWidth || 320, 240);
  if (!canvas.dataset.chartHeight) {
    canvas.dataset.chartHeight = String(Number(canvas.getAttribute("height")) || 200);
  }
  const height = Number(canvas.dataset.chartHeight);
  canvas.style.height = `${height}px`;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);
  return { ctx, width, height };
}

// Canvas pixels can't be reached by CSS, so the market-overview dark cards (chart-market-index,
// chart-futures) need their own palette. Additive/opt-in only — every other chart on the site
// keeps calling drawChart()/drawAxes() with no `theme`, which defaults to the existing light
// colors below, so this doesn't touch any other view.
const CHART_THEME = {
  light: { grid: "#d0d5d3", axisText: "#58676e", noData: "#68747a", pointFill: "#f4f5f2" },
  dark: { grid: "#3d3d3d", axisText: "#999999", noData: "#999999", pointFill: "#242424" },
};

function noChartData(ctx, width, height, text = "待補資料源", theme = "light") {
  ctx.fillStyle = (CHART_THEME[theme] || CHART_THEME.light).noData;
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

function shortAxisLabel(value) {
  const text = String(value ?? "");
  const month = text.match(/^(\d{4})-(\d{2})$/);
  if (month) return `${month[1].slice(2)}/${month[2]}`;
  const quarter = text.match(/^(\d{4})Q([1-4])$/);
  if (quarter) return `${quarter[1].slice(2)}Q${quarter[2]}`;
  const date = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (date) return `${date[2]}/${date[3]}`;
  return text.replace(/^20/, "");
}

function axisValue(value) {
  const normalized = Math.abs(Number(value)) < 1e-9 ? 0 : Number(value);
  const absolute = Math.abs(normalized);
  if (absolute >= 1e9) return `${nf(1).format(normalized / 1e9)}B`;
  if (absolute >= 1e6) return `${nf(1).format(normalized / 1e6)}M`;
  if (absolute >= 1e3) return `${nf(1).format(normalized / 1e3)}K`;
  return nf(absolute < 10 ? 1 : 0).format(normalized);
}

function chartX(index, count, left, plotWidth, banded = false) {
  if (banded) return left + (plotWidth * (index + 0.5)) / Math.max(count, 1);
  return left + (plotWidth * index) / Math.max(count - 1, 1);
}

function drawAxes(ctx, width, height, domain, labels, padding, showEveryLabel = false, banded = false, axisFontSize = 11, targetLabelCount = 0, theme = "light") {
  const palette = CHART_THEME[theme] || CHART_THEME.light;
  const { left, right, top, bottom } = padding;
  const axisFont = `600 ${axisFontSize}px ui-monospace, monospace`;
  ctx.strokeStyle = palette.grid;
  ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i += 1) {
    const y = top + ((height - top - bottom) * i) / 3;
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke();
    const value = domain.max - ((domain.max - domain.min) * i) / 3;
    ctx.fillStyle = palette.axisText; ctx.font = axisFont; ctx.textAlign = "right";
    ctx.fillText(axisValue(value), left - 6, y + 3);
  }
  const count = labels.length;
  const labelIndexes = showEveryLabel
    ? labels.map((_, index) => index)
    : targetLabelCount > 0
      ? [...new Set(Array.from({ length: Math.min(targetLabelCount, count) }, (_, i) =>
          Math.round((i * (count - 1)) / Math.max(Math.min(targetLabelCount, count) - 1, 1))))]
      : [...new Set([0, Math.floor((count - 1) / 2), count - 1])];
  const rotate = showEveryLabel ? count > 8 : targetLabelCount > 0 && count > targetLabelCount;
  ctx.textAlign = "center"; ctx.fillStyle = palette.axisText; ctx.font = axisFont;
  labelIndexes.forEach((index) => {
    if (index < 0 || !labels[index]) return;
    const x = chartX(index, count, left, width - left - right, banded);
    const label = shortAxisLabel(labels[index]);
    if (rotate) {
      ctx.save();
      ctx.translate(x, height - bottom + 12);
      ctx.rotate(-Math.PI / 3);
      ctx.textAlign = "right";
      ctx.fillText(label, 0, 0);
      ctx.restore();
    } else {
      ctx.fillText(label, x, height - 5);
    }
  });
}

function drawChart(canvas, series, labels = [], { bars = [], zeroBased = false, rightAxis = [], labelCount = 0, theme = "light" } = {}) {
  const palette = CHART_THEME[theme] || CHART_THEME.light;
  const { ctx, width, height } = canvasFrame(canvas);
  const leftDomain = chartDomain(series.filter((_, index) => !rightAxis.includes(index)));
  const rightDomain = chartDomain(series.filter((_, index) => rightAxis.includes(index)));
  const domain = leftDomain || rightDomain;
  if (!domain) { noChartData(ctx, width, height, undefined, theme); return; }
  if (zeroBased && domain.min > 0) domain.min = 0;
  const hasDualAxis = Boolean(leftDomain && rightDomain);
  const compact = width < 370;
  const showEveryLabel = labels.length <= (compact ? 8 : 12);
  const banded = bars.length > 0;
  const rotatedLabels = showEveryLabel ? labels.length > 8 : labelCount > 0 && labels.length > labelCount;
  const padding = {
    left: compact ? 47 : 56,
    right: hasDualAxis ? (compact ? 42 : 50) : 14,
    top: 14,
    bottom: rotatedLabels ? 48 : 29,
  };
  const axisFontSize = compact ? 9 : 11;
  drawAxes(ctx, width, height, domain, labels, padding, showEveryLabel, banded, axisFontSize, labelCount, theme);
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const yOf = (value, itemDomain = domain) => padding.top + ((itemDomain.max - Number(value)) / (itemDomain.max - itemDomain.min)) * plotH;
  const maxLength = Math.max(...series.map((item) => item.values.length), 1);
  const xOf = (index) => chartX(index, maxLength, padding.left, plotW, banded);
  const barOrder = new Map(bars.map((seriesIndex, index) => [seriesIndex, index]));
  const barCount = Math.max(bars.length, 1);

  if (hasDualAxis) {
    ctx.fillStyle = palette.axisText; ctx.font = `600 ${axisFontSize}px ui-monospace, monospace`; ctx.textAlign = "left";
    for (let i = 0; i <= 3; i += 1) {
      const y = padding.top + (plotH * i) / 3;
      const value = rightDomain.max - ((rightDomain.max - rightDomain.min) * i) / 3;
      ctx.fillText(axisValue(value), width - padding.right + 6, y + 3);
    }
  }

  series.forEach((item, seriesIndex) => {
    const color = item.color || COLORS[seriesIndex % COLORS.length];
    const itemDomain = hasDualAxis && rightAxis.includes(seriesIndex) ? rightDomain : domain;
    const zeroY = yOf(0, itemDomain);
    if (bars.includes(seriesIndex)) {
      const groupWidth = Math.max(3, (plotW / Math.max(maxLength, 1)) * 0.72);
      const barWidth = Math.max(2, groupWidth / barCount);
      const position = barOrder.get(seriesIndex);
      item.values.forEach((value, index) => {
        if (!isValue(value)) return;
        const y = yOf(value, itemDomain);
        const barX = xOf(index) - groupWidth / 2 + barWidth * (position + 0.5);
        ctx.fillStyle = Number(value) >= 0 ? color : "#6f9193";
        ctx.globalAlpha = 0.78;
        ctx.fillRect(barX - barWidth / 2, Math.min(y, zeroY), Math.max(barWidth - 1, 1), Math.max(Math.abs(zeroY - y), 1));
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
    item.values.forEach((value, index) => {
      if (!isValue(value)) return;
      ctx.beginPath();
      ctx.arc(xOf(index), yOf(value, itemDomain), maxLength > 36 ? 1.8 : 2.8, 0, Math.PI * 2);
      ctx.fillStyle = palette.pointFill;
      ctx.fill();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  });
  updateChartLegend(canvas, series);
  installChartInteraction(canvas, { labels, series, padding, banded });
}

function drawCandles(canvas, priceRows) {
  const rows = chronological(priceRows, "date").slice(-80);
  const { ctx, width, height } = canvasFrame(canvas);
  const valid = rows.filter((row) => [row.open, row.high, row.low, row.close].every(isValue));
  if (!valid.length) { noChartData(ctx, width, height, "待補歷史日股價資料源"); return; }
  const domain = { min: Math.min(...valid.map((row) => Number(row.low))), max: Math.max(...valid.map((row) => Number(row.high))) };
  if (domain.min === domain.max) { domain.min -= 1; domain.max += 1; }
  const compact = width < 370;
  const padding = { left: compact ? 47 : 56, right: 14, top: 14, bottom: 29 };
  drawAxes(ctx, width, height, domain, rows.map((row) => row.date), padding, false, true, compact ? 9 : 11);
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const step = plotW / Math.max(rows.length, 1);
  const bodyWidth = Math.max(2, step * .62);
  const yOf = (value) => padding.top + ((domain.max - Number(value)) / (domain.max - domain.min)) * plotH;
  rows.forEach((row, index) => {
    if (![row.open, row.high, row.low, row.close].every(isValue)) return;
    const x = padding.left + step * index + step / 2;
    const rising = Number(row.close) >= Number(row.open);
    ctx.strokeStyle = rising ? "#9d686f" : "#678473";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.beginPath(); ctx.moveTo(x, yOf(row.high)); ctx.lineTo(x, yOf(row.low)); ctx.stroke();
    const yOpen = yOf(row.open); const yClose = yOf(row.close);
    ctx.fillRect(x - bodyWidth / 2, Math.min(yOpen, yClose), bodyWidth, Math.max(Math.abs(yOpen - yClose), 1));
  });
  const series = [
    { name: "開盤", values: rows.map((row) => row.open), digits: 2, color: "#a98256" },
    { name: "最高", values: rows.map((row) => row.high), digits: 2, color: "#9d686f" },
    { name: "最低", values: rows.map((row) => row.low), digits: 2, color: "#678473" },
    { name: "收盤", values: rows.map((row) => row.close), digits: 2, color: "#6f9193" },
    { name: "成交量", values: rows.map((row) => row.volume), digits: 0, color: "#817991" },
  ];
  updateChartLegend(canvas, series.slice(0, 4));
  installChartInteraction(canvas, { labels: rows.map((row) => row.date), series, padding, banded: true });
}

function chronological(rows, key) {
  return [...(rows || [])].sort((a, b) => String(a[key]).localeCompare(String(b[key])));
}

// 互動式K線圖（可滾輪縮放／拖曳平移）— 給大盤總覽「加權指數走勢」詳情抽屜的
// 日K／週K／月K 用。沿用 drawCandles 同一套畫法（wick+body、installChartInteraction
// 的 hover tooltip 直接借用「每個 OHLC 欄位當一條 series」的技巧），額外加的是
// 可視範圍（zoom/pan 只改 canvas._candleView.start/end，不重新請求資料）跟深色主題。
const CANDLESTICK_MIN_VISIBLE = 15;

function candlestickPalette(theme) {
  return theme === "dark" ? { up: "#d73d38", down: "#60b357" } : { up: "#9d686f", down: "#678473" };
}

function drawCandlestickChart(canvas, allBars, opts = {}) {
  const theme = opts.theme || "light";
  let view = canvas._candleView;
  if (!view || view.barsRef !== allBars) {
    const visible = Math.min(allBars.length, opts.defaultVisible || 60);
    view = { barsRef: allBars, start: Math.max(0, allBars.length - visible), end: Math.max(0, allBars.length - 1) };
    canvas._candleView = view;
  }
  canvas._candleRedraw = () => drawCandlestickChart(canvas, allBars, opts);

  const { ctx, width, height } = canvasFrame(canvas);
  if (!allBars?.length) { noChartData(ctx, width, height, "尚無K線資料", theme); return; }
  const start = Math.max(0, Math.min(view.start, allBars.length - 1));
  const end = Math.max(start, Math.min(view.end, allBars.length - 1));
  const bars = allBars.slice(start, end + 1);
  const valid = bars.filter((b) => [b.open, b.high, b.low, b.close].every(isValue));
  if (!valid.length) { noChartData(ctx, width, height, "尚無K線資料", theme); return; }

  const domain = { min: Math.min(...valid.map((b) => Number(b.low))), max: Math.max(...valid.map((b) => Number(b.high))) };
  if (domain.min === domain.max) { domain.min -= 1; domain.max += 1; }
  const pad = (domain.max - domain.min) * 0.05 || 1;
  domain.min -= pad; domain.max += pad;

  const compact = width < 370;
  const padding = { left: compact ? 47 : 56, right: 14, top: 14, bottom: 29 };
  drawAxes(ctx, width, height, domain, bars.map((b) => b.date), padding, false, true, compact ? 9 : 11, 6, theme);
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const step = plotW / Math.max(bars.length, 1);
  const bodyWidth = Math.max(1.5, step * .62);
  const yOf = (value) => padding.top + ((domain.max - Number(value)) / (domain.max - domain.min)) * plotH;
  const colors = candlestickPalette(theme);
  bars.forEach((bar, index) => {
    if (![bar.open, bar.high, bar.low, bar.close].every(isValue)) return;
    const x = padding.left + step * index + step / 2;
    const rising = Number(bar.close) >= Number(bar.open);
    ctx.strokeStyle = rising ? colors.up : colors.down;
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, yOf(bar.high)); ctx.lineTo(x, yOf(bar.low)); ctx.stroke();
    const yOpen = yOf(bar.open); const yClose = yOf(bar.close);
    ctx.fillRect(x - bodyWidth / 2, Math.min(yOpen, yClose), bodyWidth, Math.max(Math.abs(yOpen - yClose), 1));
  });

  installChartInteraction(canvas, {
    labels: bars.map((b) => b.date),
    series: [
      { name: "開盤", values: bars.map((b) => b.open), digits: 2 },
      { name: "最高", values: bars.map((b) => b.high), digits: 2 },
      { name: "最低", values: bars.map((b) => b.low), digits: 2 },
      { name: "收盤", values: bars.map((b) => b.close), digits: 2 },
    ],
    padding, banded: true,
  });
  installCandlestickZoomPan(canvas, allBars, padding, plotW);
}

function installCandlestickZoomPan(canvas, allBars, padding, plotW) {
  canvas._candleZoomMeta = { allBars, padding, plotW };
  if (canvas.dataset.candleZoomInteractive) return;
  canvas.dataset.candleZoomInteractive = "true";

  canvas.addEventListener("wheel", (event) => {
    const view = canvas._candleView;
    const meta = canvas._candleZoomMeta;
    if (!view || !meta) return;
    event.preventDefault();
    const total = meta.allBars.length;
    const range = view.end - view.start + 1;
    const factor = event.deltaY > 0 ? 1.15 : 1 / 1.15;
    let newRange = Math.round(range * factor);
    newRange = Math.max(CANDLESTICK_MIN_VISIBLE, Math.min(total, newRange));
    if (newRange === range) return;
    const rect = canvas.getBoundingClientRect();
    const relX = Math.min(1, Math.max(0, (event.clientX - rect.left - meta.padding.left) / meta.plotW));
    const anchorIndex = view.start + relX * range;
    let newStart = Math.round(anchorIndex - relX * newRange);
    newStart = Math.max(0, Math.min(total - newRange, newStart));
    view.start = newStart;
    view.end = newStart + newRange - 1;
    canvas._candleRedraw?.();
  }, { passive: false });

  let dragging = false;
  let dragStartX = 0;
  let dragStartView = null;
  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    dragStartX = event.clientX;
    dragStartView = { ...canvas._candleView };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const view = canvas._candleView;
    const meta = canvas._candleZoomMeta;
    const total = meta.allBars.length;
    const range = dragStartView.end - dragStartView.start + 1;
    const dx = event.clientX - dragStartX;
    const barsDelta = Math.round((-dx / meta.plotW) * range);
    let newStart = dragStartView.start + barsDelta;
    newStart = Math.max(0, Math.min(total - range, newStart));
    view.start = newStart;
    view.end = newStart + range - 1;
    canvas._candleRedraw?.();
  });
  const stopDrag = () => { dragging = false; };
  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointercancel", stopDrag);
}

// ISO 8601 週編號（週一為週首、每年第一個週四所在週為第1週）— 週K聚合用的分桶
// key，避免用「第幾個7天」這種跟自然週對不上的簡化算法。
function isoWeekKey(dateStr) {
  const d = new Date(`${dateStr}T00:00:00Z`);
  const day = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - day + 3);
  const firstThursday = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  const week = 1 + Math.round(((d - firstThursday) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7);
  return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

// 日K → 週K／月K：開＝區間第一天開盤，收＝區間最後一天收盤，高／低＝區間極值。
// dailyBars 必須已經按日期由舊到新排序（index_trend 本來就是 ASC）。
function aggregateOhlcBars(dailyBars, granularity) {
  if (granularity === "day") return dailyBars;
  const keyOf = granularity === "week" ? (b) => isoWeekKey(b.date) : (b) => b.date.slice(0, 7);
  const order = [];
  const buckets = new Map();
  for (const bar of dailyBars) {
    const key = keyOf(bar);
    if (!buckets.has(key)) { buckets.set(key, []); order.push(key); }
    buckets.get(key).push(bar);
  }
  return order.map((key) => {
    const group = buckets.get(key);
    const highs = group.map((b) => b.high).filter(isValue);
    const lows = group.map((b) => b.low).filter(isValue);
    return {
      date: key,
      open: group[0].open,
      high: highs.length ? Math.max(...highs) : null,
      low: lows.length ? Math.min(...lows) : null,
      close: group[group.length - 1].close,
    };
  });
}

// 加權指數走勢細項抽屜 — 點卡片展開，日K／週K／月K 並排切換 + 統計格（開高低收、
// 振幅、高低價差、尾盤委買委賣、漲跌／漲停跌停家數，都是已經在 overview 裡的資料，
// 不用額外打 API）。
function indexTrendToBars(trend) {
  return (trend || []).map((row) => ({
    date: row.date, open: row.open_index, high: row.high_index, low: row.low_index, close: row.close_index,
  }));
}

function indexDetailStat(label, value) {
  return `<div class="index-detail-stat"><span>${escapeHtml(label)}</span><b>${value}</b></div>`;
}

function indexDetailStatGrid(overview) {
  const ohlc = overview.index_ohlc?.twse;
  const dist = overview.stock_change_distribution;
  const orderBook = overview.market_order_book;
  if (!ohlc && !dist && !orderBook) return emptyHtml("待補加權指數統計資料");
  return `<div class="index-detail-stats">` +
    indexDetailStat("開盤", fmt(ohlc?.open_index, 0)) +
    indexDetailStat("最高", fmt(ohlc?.high_index, 0)) +
    indexDetailStat("最低", fmt(ohlc?.low_index, 0)) +
    indexDetailStat("收盤", fmt(ohlc?.close_index, 0)) +
    indexDetailStat("振幅", pct(ohlc?.amplitude_pct, 2, true)) +
    indexDetailStat("高低價差", fmt(ohlc?.high_low_spread, 2)) +
    indexDetailStat("尾盤委買(上市,張)", fmt(orderBook?.total_bid_volume, 0)) +
    indexDetailStat("尾盤委賣(上市,張)", fmt(orderBook?.total_ask_volume, 0)) +
    indexDetailStat("上漲家數", fmt(dist?.up_count, 0)) +
    indexDetailStat("下跌家數", fmt(dist?.down_count, 0)) +
    indexDetailStat("漲停家數", fmt(dist?.limit_up_count, 0)) +
    indexDetailStat("跌停家數", fmt(dist?.limit_down_count, 0)) +
    `</div>`;
}

const INDEX_DETAIL_TABS = [
  { key: "day", label: "日K" },
  { key: "week", label: "週K" },
  { key: "month", label: "月K" },
];

function renderIndexDetailChart(overview, granularity) {
  const canvas = byId("index-detail-candlestick");
  if (!canvas) return;
  canvas._candleView = null; // 換週期要重設可視範圍，不能沿用上一個週期的 index 範圍
  const dailyBars = indexTrendToBars(overview.index_trend);
  const bars = aggregateOhlcBars(dailyBars, granularity);
  const visible = granularity === "day" ? 60 : granularity === "week" ? 52 : 24;
  drawCandlestickChart(canvas, bars, { defaultVisible: visible });
}

function openIndexDetailDrawer() {
  const overview = state.marketOverview;
  if (!overview) return;
  openDrawer("加權指數走勢細項", `
    <div class="mode-switch" id="index-detail-tabs" role="group" aria-label="K線週期">
      ${INDEX_DETAIL_TABS.map((t, i) => `<button class="${i === 0 ? "active" : ""}" data-index-detail-tab="${t.key}" type="button">${t.label}</button>`).join("")}
    </div>
    <canvas id="index-detail-candlestick" class="chart" height="280"></canvas>
    <p class="source-note">滾輪縮放，拖曳平移。開高低收來自 TWSE 官方 MI_5MINS_HIST；週K／月K 由日線聚合（開＝區間首日開盤，收＝區間末日收盤，高／低＝區間極值）。</p>
    ${indexDetailStatGrid(overview)}
  `);
  renderIndexDetailChart(overview, "day");
  $$('#index-detail-tabs [data-index-detail-tab]').forEach((button) => button.addEventListener("click", () => {
    $$('#index-detail-tabs [data-index-detail-tab]').forEach((item) => item.classList.toggle("active", item === button));
    renderIndexDetailChart(overview, button.dataset.indexDetailTab);
  }));
}

// 三張指數迷你卡（加權指數／櫃買指數／台指期貨）點進去的分流 — 三者資料完整度
// 不同，不能共用同一支渲染函式硬套：加權指數有官方開高低（見上），台指期貨有
// 官方日盤／夜盤開高低（下面用日盤畫K線），櫃買指數目前只有收盤指數，只能先
// 給收盤趨勢線 + 明講缺口，不能假裝成K線圖。
function openIndexCardDrawer(key) {
  if (key === "twse") { openIndexDetailDrawer(); return; }
  if (key === "futures") { openFuturesDetailDrawer(); return; }
  if (key === "otc") { openOtcDetailDrawer(); return; }
}

function futuresSeriesToBars(series) {
  return (series || []).map((row) => ({ date: row.date, open: row.open, high: row.high, low: row.low, close: row.close }));
}

function renderFuturesDetailChart(overview, granularity) {
  const canvas = byId("futures-detail-candlestick");
  if (!canvas) return;
  canvas._candleView = null;
  const dailyBars = futuresSeriesToBars(overview.index_ohlc?.futures_series);
  const bars = aggregateOhlcBars(dailyBars, granularity);
  const visible = granularity === "day" ? 60 : granularity === "week" ? 52 : 24;
  drawCandlestickChart(canvas, bars, { defaultVisible: visible });
}

function openFuturesDetailDrawer() {
  const overview = state.marketOverview;
  if (!overview) return;
  const latest = latestFuturesQuote(overview.index_ohlc?.futures);
  const stats = latest
    ? `<div class="index-detail-stats">` +
      indexDetailStat("最新盤別", latest.session === "night" ? "夜盤" : "日盤") +
      indexDetailStat("收盤", fmt(latest.close, 0)) +
      indexDetailStat("結算價", fmt(latest.settlement_price, 0)) +
      indexDetailStat("漲跌幅", `${Number(latest.change_pct) >= 0 ? "+" : ""}${pct(latest.change_pct, 2, true)}`) +
      `</div>`
    : emptyHtml("待補台指期貨統計資料");
  openDrawer("台指期貨走勢細項", `
    <div class="mode-switch" id="futures-detail-tabs" role="group" aria-label="K線週期">
      ${INDEX_DETAIL_TABS.map((t, i) => `<button class="${i === 0 ? "active" : ""}" data-futures-detail-tab="${t.key}" type="button">${t.label}</button>`).join("")}
    </div>
    <canvas id="futures-detail-candlestick" class="chart" height="280"></canvas>
    <p class="source-note">滾輪縮放，拖曳平移。只畫日盤 K 棒（不含夜盤），來源 TAIFEX 官方期貨每日交易行情；週K／月K 由日線聚合。</p>
    ${stats}
  `);
  renderFuturesDetailChart(overview, "day");
  $$('#futures-detail-tabs [data-futures-detail-tab]').forEach((button) => button.addEventListener("click", () => {
    $$('#futures-detail-tabs [data-futures-detail-tab]').forEach((item) => item.classList.toggle("active", item === button));
    renderFuturesDetailChart(overview, button.dataset.futuresDetailTab);
  }));
}

function openOtcDetailDrawer() {
  const overview = state.marketOverview;
  if (!overview) return;
  const trend = overview.index_ohlc?.otc_trend || [];
  openDrawer("櫃買指數走勢細項", `
    <canvas id="otc-detail-chart" class="chart" height="240"></canvas>
    <p class="source-note">櫃買指數目前只有官方收盤指數（TWSE MI_INDEX），還沒有逐日開高低來源，暫時只能畫收盤趨勢線，不是K線圖——等找到 TPEx 對應的開高低端點後再升級，不能用收盤價回推假造開高低。</p>
  `);
  drawChart(byId("otc-detail-chart"), [
    { name: "櫃買指數", values: trend.map((row) => row.close_index), digits: 2 },
  ], trend.map((row) => row.date), { labelCount: 8 });
}

// 三指數對照（獨立頁面，不是抽屜——使用者要求要有更大畫面塞疊圖+矩陣表）。
// 三個來源的絕對量級差很多（加權指數/台指期貨約4萬點、櫃買指數約400點），
// 疊在同一張線性軸上櫃買指數會貼底看不到，所以核心是「百分比」模式：
// 每條線各自以可視範圍內第一個有資料的交易日收盤價為基準（=0%），不是三者
// 對齊到同一天的絕對水準。log 模式只套用在原始值（一般/log），百分比模式
// 本身量級已經可比，不需要 log。
const INDEX_COMPARISON_SERIES = [
  { key: "twse", name: "加權指數" },
  { key: "otc", name: "櫃買指數" },
  { key: "futures", name: "台指期貨(日盤)" },
];
const INDEX_COMPARISON_RANGE_DAYS = { "30": 30, "90": 90, "180": 180 };
const INDEX_COMPARISON_HORIZONS = [
  { key: "1d", label: "今日", days: 1 },
  { key: "1w", label: "1週", days: 5 },
  { key: "1m", label: "1月", days: 20 },
  { key: "3m", label: "3月", days: 60 },
];

function alignedIndexSeries(overview) {
  return {
    twse: chronological(overview.index_trend || [], "date")
      .map((r) => ({ date: r.date, close: r.close_index })),
    otc: chronological(overview.index_ohlc?.otc_trend || [], "date")
      .map((r) => ({ date: r.date, close: r.close_index })),
    futures: chronological(overview.index_ohlc?.futures_series || [], "date")
      .map((r) => ({ date: r.date, close: r.close })),
  };
}

function filterSeriesByRange(rows, range) {
  if (range === "all" || !rows.length) return rows;
  const days = INDEX_COMPARISON_RANGE_DAYS[range] || 30;
  const cutoff = new Date(rows[rows.length - 1].date);
  cutoff.setDate(cutoff.getDate() - days);
  const cutoffIso = cutoff.toISOString().slice(0, 10);
  return rows.filter((r) => r.date >= cutoffIso);
}

function formatSignedPercent(value, digits = 2) {
  if (!isValue(value)) return "-";
  const num = Number(value);
  return `${num >= 0 ? "+" : ""}${nf(digits).format(num)}%`;
}

function tradingDayReturn(rows, daysBack) {
  if (rows.length < daysBack + 1) return null;
  const latest = rows[rows.length - 1].close;
  const base = rows[rows.length - 1 - daysBack].close;
  if (!isValue(latest) || !isValue(base) || Number(base) === 0) return null;
  return (Number(latest) / Number(base) - 1) * 100;
}

// 通用多線疊圖，跟既有 drawChart() 分開實作（不共用）：這裡需要 log 軸與
// 「隱藏個別數列」，drawChart() 是全站共用的既有函式，改它風險外溢到其他
// 圖表；獨立一份只給這個對照頁用，範圍可控。
function drawMultiLineChart(canvas, series, labels, opts = {}) {
  const theme = opts.theme || "light";
  const palette = CHART_THEME[theme] || CHART_THEME.light;
  const { ctx, width, height } = canvasFrame(canvas);
  const hidden = opts.hidden || new Set();
  const scale = opts.scale === "log" ? "log" : "linear";
  const toDomainSpace = scale === "log" ? (v) => Math.log10(v) : (v) => v;
  const fromDomainSpace = scale === "log" ? (v) => Math.pow(10, v) : (v) => v;

  const visible = series.filter((_, index) => !hidden.has(index));
  const rawValues = visible.flatMap((item) => item.values || [])
    .filter((v) => isValue(v) && (scale !== "log" || Number(v) > 0)).map(Number);
  if (!rawValues.length) { noChartData(ctx, width, height, undefined, theme); return; }

  let min = Math.min(...rawValues.map(toDomainSpace));
  let max = Math.max(...rawValues.map(toDomainSpace));
  if (min === max) {
    const bump = scale === "log" ? 0.05 : Math.max(Math.abs(min) * 0.1, 1);
    min -= bump; max += bump;
  }
  const pad = (max - min) * 0.06 || 1;
  const domain = { min: min - pad, max: max + pad };

  const compact = width < 370;
  const showEveryLabel = labels.length <= (compact ? 8 : 12);
  const targetLabelCount = opts.labelCount || 8;
  const rotatedLabels = showEveryLabel ? labels.length > 8 : labels.length > targetLabelCount;
  const padding = { left: compact ? 50 : 62, right: 14, top: 14, bottom: rotatedLabels ? 48 : 29 };
  const axisFontSize = compact ? 9 : 11;
  const axisFont = `600 ${axisFontSize}px ui-monospace, monospace`;
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  ctx.strokeStyle = palette.grid; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i += 1) {
    const y = padding.top + (plotH * i) / 3;
    ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(width - padding.right, y); ctx.stroke();
    const realValue = fromDomainSpace(domain.max - ((domain.max - domain.min) * i) / 3);
    ctx.fillStyle = palette.axisText; ctx.font = axisFont; ctx.textAlign = "right";
    const label = opts.suffix === "%" ? `${nf(1).format(realValue)}%` : axisValue(realValue);
    ctx.fillText(label, padding.left - 6, y + 3);
  }

  const count = labels.length;
  const labelIndexes = showEveryLabel
    ? labels.map((_, index) => index)
    : [...new Set(Array.from({ length: Math.min(targetLabelCount, count) }, (_, i) =>
        Math.round((i * (count - 1)) / Math.max(Math.min(targetLabelCount, count) - 1, 1))))];
  ctx.textAlign = "center"; ctx.fillStyle = palette.axisText; ctx.font = axisFont;
  labelIndexes.forEach((index) => {
    if (index < 0 || !labels[index]) return;
    const x = chartX(index, count, padding.left, plotW, false);
    const label = shortAxisLabel(labels[index]);
    if (rotatedLabels) {
      ctx.save(); ctx.translate(x, height - padding.bottom + 12); ctx.rotate(-Math.PI / 3);
      ctx.textAlign = "right"; ctx.fillText(label, 0, 0); ctx.restore();
    } else {
      ctx.fillText(label, x, height - 5);
    }
  });

  const maxLength = Math.max(...series.map((item) => item.values.length), 1);
  const xOf = (index) => chartX(index, maxLength, padding.left, plotW, false);
  const yOf = (value) => padding.top + ((domain.max - toDomainSpace(Number(value))) / (domain.max - domain.min)) * plotH;

  if (opts.emphasizeZero && domain.min < 0 && domain.max > 0) {
    const zeroY = yOf(0);
    ctx.save();
    ctx.strokeStyle = palette.axisText; ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padding.left, zeroY); ctx.lineTo(width - padding.right, zeroY); ctx.stroke();
    ctx.restore();
  }

  series.forEach((item, seriesIndex) => {
    if (hidden.has(seriesIndex)) return;
    const color = item.color || COLORS[seriesIndex % COLORS.length];
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    let started = false;
    item.values.forEach((value, index) => {
      if (!isValue(value) || (scale === "log" && Number(value) <= 0)) { started = false; return; }
      const x = xOf(index); const y = yOf(value);
      if (!started) { ctx.moveTo(x, y); started = true; } else { ctx.lineTo(x, y); }
    });
    ctx.stroke();
  });

  installChartInteraction(canvas, { labels, series: visible, padding, banded: false });
}

function renderIndexComparisonLegend(series) {
  const el = byId("index-comparison-legend");
  if (!el) return;
  el.innerHTML = series.map((item, index) => {
    const isHidden = state.indexComparisonHidden.has(index);
    return `<button type="button" class="${isHidden ? "hidden-series" : ""}" data-comparison-legend-index="${index}"><i style="--legend-color:${item.color}"></i>${escapeHtml(item.name)}</button>`;
  }).join("");
  $$('#index-comparison-legend [data-comparison-legend-index]').forEach((button) => button.addEventListener("click", () => {
    const index = Number(button.dataset.comparisonLegendIndex);
    if (state.indexComparisonHidden.has(index)) state.indexComparisonHidden.delete(index);
    else state.indexComparisonHidden.add(index);
    renderIndexComparison(state.marketOverview);
  }));
}

function renderIndexComparisonMatrix(aligned) {
  const table = byId("index-comparison-matrix");
  if (!table) return;
  const thead = `<thead><tr><th>指數</th>${INDEX_COMPARISON_HORIZONS.map((h) => `<th>${h.label}</th>`).join("")}</tr></thead>`;
  const rows = INDEX_COMPARISON_SERIES.map(({ key, name }) => {
    const cells = INDEX_COMPARISON_HORIZONS.map((h) => {
      const value = tradingDayReturn(aligned[key], h.days);
      const cls = isValue(value) ? (value >= 0 ? "positive" : "negative") : "";
      return `<td class="${cls}">${formatSignedPercent(value)}</td>`;
    }).join("");
    return `<tr><td>${escapeHtml(name)}</td>${cells}</tr>`;
  }).join("");
  table.innerHTML = `${thead}<tbody>${rows}</tbody>`;
}

function renderIndexComparison(overview) {
  if (!overview) return;
  const aligned = alignedIndexSeries(overview);
  const filtered = {
    twse: filterSeriesByRange(aligned.twse, state.indexComparisonRange),
    otc: filterSeriesByRange(aligned.otc, state.indexComparisonRange),
    futures: filterSeriesByRange(aligned.futures, state.indexComparisonRange),
  };
  const dateSet = new Set();
  INDEX_COMPARISON_SERIES.forEach(({ key }) => filtered[key].forEach((r) => dateSet.add(r.date)));
  const labels = [...dateSet].sort();

  const scale = state.indexComparisonScale;
  const series = INDEX_COMPARISON_SERIES.map(({ key, name }, index) => {
    const byDate = new Map(filtered[key].map((r) => [r.date, r.close]));
    let values = labels.map((date) => (byDate.has(date) && isValue(byDate.get(date)) ? Number(byDate.get(date)) : null));
    if (scale === "percent") {
      const baseIndex = values.findIndex(isValue);
      const base = baseIndex >= 0 ? values[baseIndex] : null;
      values = values.map((v) => (isValue(v) && isValue(base) ? ((v / base) - 1) * 100 : null));
    }
    return {
      name, values, color: COLORS[index % COLORS.length],
      digits: scale === "percent" ? 2 : 0,
      suffix: scale === "percent" ? "%" : "",
    };
  });

  drawMultiLineChart(byId("chart-index-comparison"), series, labels, {
    scale: scale === "log" ? "log" : "linear",
    hidden: state.indexComparisonHidden,
    suffix: scale === "percent" ? "%" : "",
    emphasizeZero: scale === "percent",
    labelCount: 8,
  });
  renderIndexComparisonLegend(series);
  renderIndexComparisonMatrix(aligned);

  const scaleLabel = scale === "percent" ? "百分比（相對強弱）" : scale === "log" ? "Log" : "一般";
  byId("index-comparison-meta").textContent = `資料至 ${labels[labels.length - 1] || "待補"}｜Y軸：${scaleLabel}`;
}

function renderStockHeader(stock, freshness = {}, valuationBenchmark = {}) {
  byId("stock-name").textContent = stock.name || stock.code;
  byId("stock-code").textContent = stock.code;
  byId("stock-market").textContent = stock.market || "市場待補";
  byId("stock-industry").textContent = stock.industry || "產業待補";
  byId("stat-price").textContent = fmt(stock.price, 2);
  byId("stat-pe").textContent = fmt(stock.pe_ratio, 2);
  byId("stat-yield").textContent = pct(stock.dividend_yield_pct, 2, true);
  byId("stat-pe-note").innerHTML = `${deltaChip(valuationBenchmark.pe_vs_market_pct)} 大盤中位數 ${fmt(valuationBenchmark.market_pe_median, 2)}`;
  byId("stat-yield-note").innerHTML = `${deltaChip(valuationBenchmark.yield_vs_market_pct)} 大盤中位數 ${pct(valuationBenchmark.market_yield_median, 2, true)}`;
  byId("stat-bvps").textContent = fmt(stock.book_value_per_share, 2);
  byId("stat-mcap").textContent = fmt(stock.market_cap_millions, 0);
  byId("stat-time").textContent = freshness.market_date || "待補行情";
  byId("fresh-market").textContent = freshness.market_date || "待補";
  byId("fresh-revenue").textContent = freshness.revenue_month || "待補";
  byId("fresh-financial").textContent = freshness.financial_quarter || "待補";
  byId("fresh-chips").textContent = freshness.chips_date || "待補";
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
  byId("coverage-strip").innerHTML = parts.map(([label, value, suffix]) => `<div><span>${label}</span><b>${escapeHtml(value ?? "-")}${suffix}</b></div>`).join("");
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
  byId("metric-current-target-note").innerHTML = `${deltaChip(result.current_target_upside_pct)} 現況 TTM PE × 預估 TTM EPS`;
  byId("metric-ttm-eps").textContent = fmt(result.estimated_ttm_eps, 2);
  byId("metric-current-eps").textContent = `目前 TTM ${fmt(result.current_ttm_eps, 2)} 元`;
  byId("metric-dividend").textContent = fmt(result.estimated_cash_dividend, 2);
  byId("metric-dividend-yield").textContent = `殖利率 ${pct(result.estimated_dividend_yield)}`;
  byId("metric-peg").textContent = fmt(result.peg, 3);
  byId("metric-total-score").innerHTML = `${pegBadge(result.peg)} 總報酬本益比 ${fmt(result.total_return_pe_score, 3)}`;

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
    const upside = result.pe_target_upside_pct?.[key];
    return `<tr class="${step === 0 ? "mean-row" : ""}"><td>${step === 0 ? "平均" : `${step > 0 ? "+" : ""}${step}σ`}</td><td>${fmt(pe, 2)}</td><td>${fmt(target, 0)}</td><td>${deltaChip(upside)}</td></tr>`;
  }).join("");
  byId("pe-river-table").innerHTML = result.pe_river
    ? `<thead><tr><th>河流層級</th><th>PE</th><th>目標價</th><th>距現價</th></tr></thead><tbody>${rows}</tbody><tfoot><tr><td>母體標準差</td><td colspan="3">${fmt(result.pe_river.population_stdev, 3)}</td></tr></tfoot>`
    : `<tr><td>${emptyHtml("需補五年月 PE")}</td></tr>`;
}

function renderFundamentals(data) {
  const revenue = chronological(data.revenue, "month").slice(-24);
  drawChart(byId("chart-revenue"), [
    { name: "單月營收", values: revenue.map((row) => isValue(row.revenue) ? row.revenue / 1000 : null), digits: 0, suffix: " 百萬" },
    { name: "近 3 月平均", values: revenue.map((row) => row.signal?.near_3m ? row.signal.near_3m / 3000 : null), digits: 0, suffix: " 百萬" },
    { name: "近 12 月平均", values: revenue.map((row) => row.signal?.near_12m ? row.signal.near_12m / 12000 : null), digits: 0, suffix: " 百萬" },
  ], revenue.map((row) => row.month), { bars: [0] });
  const latestRevenue = revenue.at(-1);
  byId("revenue-caption").textContent = latestRevenue ? `${latestRevenue.month}｜${fmt(latestRevenue.revenue / 1000, 0)} 百萬` : "待補資料";

  const profits = chronological(data.profitability, "quarter").slice(-12);
  drawChart(byId("chart-profitability"), [
    { name: "毛利率", values: profits.map((row) => row.gross_margin_pct), digits: 2, suffix: "%" },
    { name: "營益率", values: profits.map((row) => row.operating_margin_pct), digits: 2, suffix: "%" },
    { name: "淨利率", values: profits.map((row) => row.revenue ? row.net_income / row.revenue * 100 : null), digits: 2, suffix: "%" },
  ], profits.map((row) => row.quarter));
  const epsRows = chronological(data.eps?.length ? data.eps : data.profitability, "quarter").slice(-12);
  drawChart(byId("chart-eps"), [{ name: "單季 EPS", values: epsRows.map((row) => row.eps), digits: 2, suffix: " 元" }], epsRows.map((row) => row.quarter), { bars: [0] });

  const revenueTable = byId("revenue-table");
  const revenueRows = [...revenue].reverse();
  revenueTable.innerHTML = `<thead><tr><th>月份</th><th>單月營收</th><th>3M 月均</th><th>12M 月均</th><th>3M YoY</th><th>12M YoY</th><th>動能</th></tr></thead><tbody>${revenueRows.map((row) => `<tr><td>${escapeHtml(row.month)}</td><td>${fmt(row.revenue / 1000, 0)}</td><td>${fmt(row.signal?.near_3m ? row.signal.near_3m / 3000 : null, 0)}</td><td>${fmt(row.signal?.near_12m ? row.signal.near_12m / 12000 : null, 0)}</td><td>${pct(row.signal?.near_3m_yoy)}</td><td>${pct(row.signal?.near_12m_yoy)}</td><td>${escapeHtml(row.signal?.yoy_trend || "資料累積中")}</td></tr>`).join("")}</tbody>`;

  const tableRows = (data.income_statement?.length ? data.income_statement : data.profitability || []).slice(0, 12);
  const table = byId("income-table");
  if (!tableRows.length) { emptyTable(table, 8); return; }
  table.innerHTML = `<thead><tr><th>季別</th><th>營收</th><th>毛利</th><th>營業費用</th><th>營業利益</th><th>業外</th><th>母公司淨利</th><th>EPS</th></tr></thead><tbody>${tableRows.map((row) => `<tr><td>${escapeHtml(row.quarter)}</td><td>${fmt(row.revenue, 0)}</td><td>${fmt(row.gross_profit, 0)}</td><td>${fmt(row.operating_expense, 0)}</td><td>${fmt(row.operating_income, 0)}</td><td>${fmt(row.non_operating_income, 0)}</td><td>${fmt(row.parent_net_income ?? row.net_income, 0)}</td><td>${fmt(row.eps, 2)}</td></tr>`).join("")}</tbody>`;
}

function renderQuality(data, governance) {
  const efficiency = chronological(data.efficiency, "quarter").slice(-12);
  drawChart(byId("chart-efficiency"), [
    { name: "應收天數", values: efficiency.map((row) => row.ar_days), digits: 1, suffix: " 天" },
    { name: "存貨天數", values: efficiency.map((row) => row.inventory_days), digits: 1, suffix: " 天" },
    { name: "營運週期", values: efficiency.map((row) => row.operating_cycle_days), digits: 1, suffix: " 天" },
  ], efficiency.map((row) => row.quarter));
  const cash = chronological(data.cashflow, "quarter").slice(-12);
  drawChart(byId("chart-cashflow"), [
    { name: "營業現金流", values: cash.map((row) => isValue(row.operating) ? row.operating / 1e6 : null), digits: 1, suffix: " 十億" },
    { name: "投資現金流", values: cash.map((row) => isValue(row.investing) ? row.investing / 1e6 : null), digits: 1, suffix: " 十億" },
    { name: "融資現金流", values: cash.map((row) => isValue(row.financing) ? row.financing / 1e6 : null), digits: 1, suffix: " 十億" },
    { name: "自由現金流", values: cash.map((row) => isValue(row.free_cash_flow) ? row.free_cash_flow / 1e6 : null), digits: 1, suffix: " 十億" },
  ], cash.map((row) => row.quarter));

  const health = data.balance_sheet?.[0] || data.financial_health?.[0];
  const healthTable = byId("health-table");
  if (!health) { healthTable.innerHTML = `<tr><td>${emptyHtml()}</td></tr>`; }
  else {
    const debt = health.total_assets ? health.total_liabilities / health.total_assets : null;
    const items = [
      ["季別", health.quarter], ["總資產", fmt(health.total_assets, 0)], ["總負債", fmt(health.total_liabilities, 0)],
      ["負債比率", pct(debt)], ["股東權益", fmt(health.total_equity, 0)], ["每股淨值", fmt(health.book_value_per_share, 2)],
      ["ROE（年化）", pct(health.roe_ratio)],
      [`合約負債${infoTip("客戶已預付但公司尚未認列營收的訂單金額（如預收貨款），常被視為未來營收的先行指標。")}`, fmt(health.contract_liabilities, 0)],
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
  const reductionHtml = reduction ? `<article><time>${escapeHtml(reduction.resume_date || "日期待補")}</time><div><b>減資恢復交易：${escapeHtml(reduction.name)}</b><p>${escapeHtml(reduction.reason || "減資公告")}｜停止交易 ${escapeHtml(reduction.stop_date || "待補")}｜換股率 ${pct(reduction.exchange_ratio)}｜EPS 校正值 ${pct(reduction.adjust_factor)}；僅在模型選擇「減資校正」時套用。</p></div></article>` : "";
  const eventHtml = events.map((event) => `<article><time>${escapeHtml(event.event_date)}</time><div><b>${escapeHtml(event.title)}</b><p>${escapeHtml(event.detail || event.event_type)}</p></div></article>`).join("");
  byId("event-list").innerHTML = reductionHtml || eventHtml ? reductionHtml + eventHtml : emptyHtml("待補重大事件與減資歷史");

  const boardHoldings = governance?.board_holdings || [];
  const boardTable = byId("board-holdings-table");
  if (boardHoldings.length) {
    boardTable.innerHTML = `<thead><tr><th>職稱</th><th>姓名</th><th>目前持股</th><th>設質股數</th><th>設質比例</th></tr></thead><tbody>${boardHoldings.map((row) => `<tr><td>${escapeHtml(row.title)}</td><td>${escapeHtml(row.person_name)}</td><td>${fmt(row.shares_held, 0)}</td><td>${fmt(row.pledged_shares, 0)}</td><td>${row.pledged_ratio > 0 ? `⚠ ${pct(row.pledged_ratio)}` : pct(row.pledged_ratio)}</td></tr>`).join("")}</tbody>`;
  } else {
    emptyTable(boardTable, 5, "待補董監事持股資料");
  }

  const majorShareholders = governance?.major_shareholders || [];
  const shareholderHtml = majorShareholders.map((row) => `<article><div><b>${escapeHtml(row.shareholder_name)}</b><p>持股逾 10%｜資料日 ${escapeHtml(row.as_of_date)}</p></div></article>`).join("");
  byId("major-shareholders-list").innerHTML = shareholderHtml || emptyHtml("待補大股東資料");
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

// PEG 判讀：<1 視為低估（沿用 rise=紅、表示對決策有利的既有慣例）、1-2 合理、>2 偏貴。
function pegBadge(peg) {
  if (!isValue(peg)) return `<em class="signal neutral">待補</em>`;
  const [text, tone] = Number(peg) < 1 ? ["低估", "rise"] : Number(peg) <= 2 ? ["合理", "neutral"] : ["偏貴", "fall"];
  return `<em class="signal ${tone}">${text}</em>`;
}

function seasonalSeriesName(year, label, values) {
  let latest = -1;
  values.forEach((value, index) => { if (isValue(value)) latest = index; });
  const base = year ? `${year} ${label}` : label;
  if (latest < 0) return `${base} · 待公布`;
  return latest < 3 ? `${base} · 至 Q${latest + 1}` : base;
}

function renderNineGrid(data) {
  const rows = chronological(data.quarterly, "quarter");
  const labels = rows.map((row) => row.quarter);
  $$('[data-signal]').forEach((node) => { node.innerHTML = signalLabel(data.signals?.[node.dataset.signal]); });
  byId("nine-signals").innerHTML = Object.entries(data.signals || {}).map(([key, value]) => `<div><span>${escapeHtml(key.replaceAll("_", " "))}</span>${signalLabel(value)}</div>`).join("");
  drawChart(byId("ng-profit"), [
    { name: "營收", values: rows.map((row) => row.revenue_millions), digits: 0, suffix: " 百萬" },
    { name: "毛利率", values: rows.map((row) => isValue(row.gross_margin_ratio) ? row.gross_margin_ratio * 100 : null), digits: 1, suffix: "%" },
    { name: "營益率", values: rows.map((row) => isValue(row.operating_margin_ratio) ? row.operating_margin_ratio * 100 : null), digits: 1, suffix: "%" },
  ], labels, { bars: [0], rightAxis: [1, 2] });
  drawChart(byId("ng-days"), [
    { name: "應收", values: rows.map((row) => row.ar_days), digits: 1, suffix: " 天" },
    { name: "存貨", values: rows.map((row) => row.inventory_days), digits: 1, suffix: " 天" },
    { name: "應付", values: rows.map((row) => row.payable_days), digits: 1, suffix: " 天" },
  ], labels);
  drawChart(byId("ng-debt"), [
    { name: "營業現金流", values: rows.map((row) => isValue(row.operating_cashflow_millions) ? row.operating_cashflow_millions / 1000 : null), digits: 1, suffix: " 十億" },
    { name: "自由現金流", values: rows.map((row) => isValue(row.free_cash_flow_millions) ? row.free_cash_flow_millions / 1000 : null), digits: 1, suffix: " 十億" },
    { name: "負債比", values: rows.map((row) => isValue(row.debt_ratio) ? row.debt_ratio * 100 : null), digits: 1, suffix: "%" },
  ], labels, { bars: [0, 1], rightAxis: [2] });
  drawChart(byId("ng-cash-profit"), [
    { name: "營業現金流", values: rows.map((row) => isValue(row.operating_cashflow_millions) ? row.operating_cashflow_millions / 1000 : null), digits: 1, suffix: " 十億" },
    { name: "營業利益", values: rows.map((row) => isValue(row.operating_income_millions) ? row.operating_income_millions / 1000 : null), digits: 1, suffix: " 十億" },
    { name: "ROE", values: rows.map((row) => isValue(row.roe_ratio) ? row.roe_ratio * 100 : null), digits: 1, suffix: "%" },
  ], labels, { bars: [0, 1], rightAxis: [2] });
  drawChart(byId("ng-lan"), [
    { name: "資本支出", values: rows.map((row) => isValue(row.capital_expenditure_millions) ? row.capital_expenditure_millions / 1000 : null), digits: 1, suffix: " 十億" },
    { name: "翁氏價值", values: rows.map((row) => row.lan_value), digits: 4 },
  ], labels, { bars: [0], rightAxis: [1] });
  drawChart(byId("ng-core-eps"), [
    { name: "本業 EPS", values: rows.map((row) => row.core_eps), digits: 2, suffix: " 元" },
    { name: "業外 EPS", values: rows.map((row) => row.non_core_eps), digits: 2, suffix: " 元" },
    { name: "本業比率", values: rows.map((row) => isValue(row.core_business_ratio) ? row.core_business_ratio * 100 : null), digits: 1, suffix: "%" },
  ], labels, { bars: [0, 1], rightAxis: [2] });
  const years = [...new Set(rows.map((row) => Number(String(row.quarter).slice(0, 4))))].filter(Number.isFinite).sort((a, b) => a - b);
  const currentYear = years.at(-1);
  const priorYear = currentYear - 1;
  const byYearQuarter = new Map(rows.map((row) => [row.quarter, row]));
  const current4 = [1, 2, 3, 4].map((quarter) => byYearQuarter.get(`${currentYear}Q${quarter}`));
  const prior4 = [1, 2, 3, 4].map((quarter) => byYearQuarter.get(`${priorYear}Q${quarter}`));
  const currentRevenue = current4.map((row) => row?.revenue_millions);
  const priorRevenue = prior4.map((row) => row?.revenue_millions);
  drawChart(byId("ng-season-revenue"), [
    { name: seasonalSeriesName(currentYear, "本期", currentRevenue), values: currentRevenue, digits: 0, suffix: " 百萬" },
    { name: seasonalSeriesName(priorYear, "去年同期", priorRevenue), values: priorRevenue, digits: 0, suffix: " 百萬" },
  ], ["Q1", "Q2", "Q3", "Q4"], { bars: [0, 1] });
  const currentDays = current4.map((row) => row?.operating_cycle_days);
  const priorDays = prior4.map((row) => row?.operating_cycle_days);
  drawChart(byId("ng-season-days"), [
    { name: seasonalSeriesName(currentYear, "本期", currentDays), values: currentDays, digits: 1, suffix: " 天" },
    { name: seasonalSeriesName(priorYear, "去年同期", priorDays), values: priorDays, digits: 1, suffix: " 天" },
  ], ["Q1", "Q2", "Q3", "Q4"]);

  const recentYear = rows.slice(-4);
  const recentYearTotal = (key) => recentYear.length === 4 && recentYear.every((row) => isValue(row[key]))
    ? recentYear.reduce((total, row) => total + Number(row[key]), 0)
    : null;
  drawChart(byId("ng-cash-class"), [{
    name: "近四季合計",
    values: [
      recentYearTotal("operating_cashflow_millions"),
      recentYearTotal("investing_cashflow_millions"),
      recentYearTotal("financing_cashflow_millions"),
      recentYearTotal("free_cash_flow_millions"),
    ],
    digits: 0,
    suffix: " 百萬",
  }], ["營業", "投資", "融資", "自由"], { bars: [0] });

  const monthly = chronological(data.monthly_revenue, "month");
  drawChart(byId("ng-bollinger"), [
    { name: "月營收", values: monthly.map((row) => row.revenue_millions), digits: 0, suffix: " 百萬" },
    { name: "3M 均線", values: monthly.map((row) => row.near_3m_avg), digits: 0, suffix: " 百萬" },
    { name: "上軌", values: monthly.map((row) => row.upper_band), digits: 0, suffix: " 百萬" },
    { name: "下軌", values: monthly.map((row) => row.lower_band), digits: 0, suffix: " 百萬" },
  ], monthly.map((row) => row.month), { bars: [0] });
  drawChart(byId("ng-contract"), [{ name: "合約負債", values: rows.map((row) => row.contract_liabilities), digits: 0, suffix: " 百萬" }], labels, { bars: [0] });
  drawCandles(byId("ng-price"), data.daily_prices || []);
}

function tableFromRows(table, rows, columns, message) {
  if (!rows?.length) { emptyTable(table, columns.length, message); return; }
  table.innerHTML = `<thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td class="${column.className ? column.className(row) : ""}">${column.format ? column.format(row[column.key], row) : escapeHtml(row[column.key])}</td>`).join("")}</tr>`).join("")}</tbody>`;
}

// 法人買賣超原始資料是逐筆 (date, institution, net) 長表；轉成寬表 (date, 外資, 投信, 自營商)
// 才能一眼比較同一天三大法人的狀態，不用逐列找同一個日期。
function institutionNetClass(key) {
  return (row) => (row[key] == null ? "" : row[key] >= 0 ? "positive" : "negative");
}

function pivotInstitutionRows(rows) {
  const byDate = new Map();
  for (const row of rows || []) {
    if (!byDate.has(row.date)) byDate.set(row.date, { date: row.date });
    byDate.get(row.date)[row.institution] = row.net;
  }
  return [...byDate.values()].sort((a, b) => (a.date < b.date ? 1 : -1));
}

function renderMarket(chips, radar) {
  const holdings = chronological(chips.holdings, "date");
  drawChart(byId("chart-holdings"), [
    { name: "外資持股", values: holdings.map((row) => row.foreign_holding_pct), digits: 2, suffix: "%" },
    { name: "大戶持股", values: holdings.map((row) => row.big_holder_pct), digits: 2, suffix: "%" },
    { name: "籌碼集中度", values: holdings.map((row) => row.concentration_pct), digits: 2, suffix: "%" },
  ], holdings.map((row) => row.date));
  const institutionRows = chronological(chips.institutional_trading, "date").slice(-42);
  const institutions = ["外資", "投信", "自營商"];
  const institutionDates = [...new Set(institutionRows.map((row) => row.date))];
  const institutionValues = new Map(institutionRows.map((row) => [`${row.date}:${row.institution}`, row.net]));
  drawChart(byId("chart-institution"), institutions.map((institution) => ({
    name: institution,
    values: institutionDates.map((date) => institutionValues.get(`${date}:${institution}`) ?? null),
    digits: 0,
    suffix: " 張",
  })), institutionDates, { bars: [0, 1, 2] });

  const marginRows = chronological(chips.margin_short, "date").slice(-20);
  drawChart(byId("chart-margin-short"), [
    { name: "融資餘額", values: marginRows.map((row) => row.margin_balance), digits: 0, suffix: " 張" },
    { name: "融券餘額", values: marginRows.map((row) => row.short_balance), digits: 0, suffix: " 張" },
    { name: "券資比", values: marginRows.map((row) => row.short_margin_ratio), digits: 2, suffix: "%" },
  ], marginRows.map((row) => row.date), { rightAxis: [2], labelCount: 10 });

  const etfLatestDate = chips.etf_holdings?.[0]?.as_of_date;
  const etfRows = (chips.etf_holdings || []).filter((row) => row.as_of_date === etfLatestDate).slice(0, 12);
  drawChart(byId("chart-etf"), [{
    name: "持股權重",
    values: etfRows.map((row) => isValue(row.holding_ratio) ? row.holding_ratio * 100 : null),
    digits: 2,
    suffix: "%",
  }], etfRows.map((row) => row.etf_code), { bars: [0] });
  byId("etf-caption").textContent = etfRows.length
    ? `${etfLatestDate}｜${etfRows.length} 檔 ETF`
    : "目前資料源未查到持有此股票的 ETF";

  tableFromRows(byId("institution-table"), pivotInstitutionRows(chips.institutional_trading).slice(0, 30), [
    { key: "date", label: "日期" },
    { key: "外資", label: "外資", format: (v) => fmt(v, 0), className: institutionNetClass("外資") },
    { key: "投信", label: "投信", format: (v) => fmt(v, 0), className: institutionNetClass("投信") },
    { key: "自營商", label: "自營商", format: (v) => fmt(v, 0), className: institutionNetClass("自營商") },
  ], "待補法人個股買賣超資料");
  tableFromRows(byId("margin-short-table"), chips.margin_short?.slice(0, 30), [
    { key: "date", label: "日期" }, { key: "margin_balance", label: "融資", format: (v) => fmt(v, 0) },
    { key: "short_balance", label: "融券", format: (v) => fmt(v, 0) }, { key: "short_margin_ratio", label: "券資比", format: (v) => pct(v, 2, true) },
  ], "待補融資融券資料");
  tableFromRows(byId("broker-table"), chips.broker_branches?.slice(0, 30), [
    { key: "date", label: "日期" }, { key: "branch", label: "分點" }, { key: "buy", label: "買", format: (v) => fmt(v, 0) },
    { key: "sell", label: "賣", format: (v) => fmt(v, 0) }, { key: "net", label: "淨", format: (v) => fmt(v, 0) },
  ], "待補券商分點資料");
  tableFromRows(byId("etf-table"), etfRows, [
    { key: "as_of_date", label: "日期" }, { key: "etf_code", label: "ETF" }, { key: "etf_name", label: "名稱" },
    { key: "holding_ratio", label: "權重", format: (v) => pct(v) },
  ], "目前資料源未查到持有此股票的 ETF；不以 0 代替");
  renderRanking(radar);
  renderMarketSnapshotCard(state.marketOverview);
}

// 大盤層級的三大法人買賣超原始資料是「市場×法人」長表（含外資/投信/自營商的
// 各種子分類與合計列，例如 TWSE 沒有「自營商合計」列，只有自行買賣/避險兩列）。
// 畫面改成籌碼K線式的「上市／上櫃」雙欄對照表，列固定為 外資/投信/自營商 三列 —
// 這裡是把同一份 rows 依 institution 語意分組相加，不是新的資料來源或欄位。
const INSTITUTIONAL_PIVOT_ROWS = [
  { label: "外資", match: (name) => name.includes("外資及陸資") && name.includes("不含") },
  { label: "投信", match: (name) => name === "投信" },
  { label: "自營商", match: (name) => name.startsWith("自營商(") },
];

function pivotInstitutionalNet(rows, market, match) {
  const matched = rows.filter((row) => row.market === market && match(row.institution));
  if (!matched.length) return null;
  return matched.reduce((sum, row) => sum + (isValue(row.net_amount) ? Number(row.net_amount) : 0), 0);
}

function institutionalNetCell(value) {
  if (!isValue(value)) return `<td>-</td>`;
  const netClass = Number(value) >= 0 ? "positive" : "negative";
  return `<td class="${netClass}">${fmt(Number(value) / 1e8, 2)} 億</td>`;
}

function renderMarketInstitutionalTable(rows) {
  const table = byId("market-institutional-table");
  const dateNote = byId("market-institutional-date");
  if (!rows?.length) {
    emptyTable(table, 3, "待補大盤三大法人買賣超資料");
    if (dateNote) dateNote.textContent = "上市／上櫃各自最新一天";
    return;
  }
  const body = INSTITUTIONAL_PIVOT_ROWS.map(({ label, match }) => {
    const twse = pivotInstitutionalNet(rows, "TWSE", match);
    const tpex = pivotInstitutionalNet(rows, "TPEX", match);
    return `<tr><td>${escapeHtml(label)}</td>${institutionalNetCell(twse)}${institutionalNetCell(tpex)}</tr>`;
  }).join("");
  table.innerHTML = `<thead><tr><th></th><th>上市</th><th>上櫃</th></tr></thead><tbody>${body}</tbody>`;
  if (dateNote) {
    const twseDate = rows.find((row) => row.market === "TWSE")?.date;
    const tpexDate = rows.find((row) => row.market === "TPEX")?.date;
    dateNote.textContent = twseDate || tpexDate ? `上市 ${twseDate || "-"}／上櫃 ${tpexDate || "-"}` : "上市／上櫃各自最新一天";
  }
}

function renderMarketMarginTable(rows) {
  tableFromRows(byId("market-margin-table"), rows, [
    { key: "market", label: "市場" },
    { key: "margin_balance", label: "融資餘額", format: (v) => fmt(v, 0) },
    { key: "short_balance", label: "融券餘額", format: (v) => fmt(v, 0) },
    { key: "date", label: "資料日" },
  ], "待補大盤融資融券資料");
}

function renderMarketFutures(rows) {
  const institutions = ["外資", "投信", "自營商"];
  const contracts = [...new Set(rows.map((row) => row.contract))];
  const values = new Map(rows.map((row) => [`${row.contract}:${row.institution}`, row.net_oi]));
  drawChart(byId("chart-futures"), institutions.map((institution) => ({
    name: institution,
    values: contracts.map((contract) => values.get(`${contract}:${institution}`) ?? null),
    digits: 0,
    suffix: " 口",
  })), contracts, { bars: [0, 1, 2] });
  tableFromRows(byId("futures-table"), rows, [
    { key: "institution", label: "身份" }, { key: "contract", label: "商品" },
    { key: "long_oi", label: "多", format: (v) => fmt(v, 0) }, { key: "short_oi", label: "空", format: (v) => fmt(v, 0) },
    { key: "net_oi", label: "淨額", format: (v) => fmt(v, 0), className: (row) => row.net_oi >= 0 ? "positive" : "negative" },
  ], "待補 TAIFEX 未平倉資料");
}

function renderFuturesLargeTrader(rows) {
  tableFromRows(byId("futures-large-trader-table"), rows, [
    { key: "trader_group", label: "身份" }, { key: "contract", label: "商品" },
    { key: "long_oi", label: "多方", format: (v) => fmt(v, 0) }, { key: "short_oi", label: "空方", format: (v) => fmt(v, 0) },
    { key: "net_oi", label: "淨額", format: (v) => fmt(v, 0), className: (row) => isValue(row.net_oi) ? (row.net_oi >= 0 ? "positive" : "negative") : "" },
    { key: "date", label: "資料日" },
  ], "待補 TAIFEX 大額交易人未沖銷部位資料");
}

function renderFuturesPriceTable(rows) {
  tableFromRows(byId("futures-price-table"), rows, [
    { key: "contract", label: "商品" },
    { key: "session", label: "盤別", format: (v) => v === "day" ? "日盤" : v === "night" ? "夜盤" : escapeHtml(v) },
    { key: "open", label: "開", format: (v) => fmt(v, 0) },
    { key: "high", label: "高", format: (v) => fmt(v, 0) },
    { key: "low", label: "低", format: (v) => fmt(v, 0) },
    { key: "close", label: "收", format: (v) => fmt(v, 0) },
    { key: "settlement_price", label: "結算價", format: (v) => fmt(v, 0) },
    {
      key: "change_pct", label: "漲跌%",
      format: (v) => isValue(v) ? `${Number(v) >= 0 ? "+" : ""}${pct(v, 2, true)}` : "-",
      className: (row) => isValue(row.change_pct) ? (row.change_pct >= 0 ? "positive" : "negative") : "",
    },
    { key: "date", label: "資料日" },
  ], "待補 TAIFEX 期貨每日行情資料");
}

// TWSE MI_INDEX has no official open/high/low for the index itself (known gap, see
// docs/specs/market-daily-digest-contract.md §3.2) — those stay "-" via fmt(), never 0.
function indexOhlcBlock(label, data) {
  if (!data) return `<div class="ohlc-block"><b>${escapeHtml(label)}</b><div class="ohlc-row"><span>資料</span><em>-</em></div></div>`;
  const changeClass = isValue(data.change_pct) ? (data.change_pct >= 0 ? "positive" : "negative") : "";
  const changeText = isValue(data.change_pct) ? `${Number(data.change_pct) >= 0 ? "+" : ""}${pct(data.change_pct, 2, true)}` : "-";
  return `<div class="ohlc-block"><b>${escapeHtml(label)}</b>` +
    `<div class="ohlc-row"><span>開</span><em>${fmt(data.open_index, 0)}</em></div>` +
    `<div class="ohlc-row"><span>高</span><em>${fmt(data.high_index, 0)}</em></div>` +
    `<div class="ohlc-row"><span>低</span><em>${fmt(data.low_index, 0)}</em></div>` +
    `<div class="ohlc-row"><span>收</span><em>${fmt(data.close_index, 0)}</em></div>` +
    `<div class="ohlc-row"><span>漲跌</span><em class="${changeClass}">${changeText}</em></div>` +
    `<small>${escapeHtml(data.date || "-")}</small></div>`;
}

function renderIndexOhlc(ohlc) {
  const strip = byId("index-ohlc-strip");
  if (!strip) return;
  strip.innerHTML = indexOhlcBlock("加權指數", ohlc?.twse) + indexOhlcBlock("櫃買指數", ohlc?.otc);
  renderFuturesPriceTable(ohlc?.futures || []);
}

// 台指期貨沒有單一「最新報價」欄位，只有日盤／夜盤兩列 OHLC（見
// docs/specs/market-daily-digest-contract.md §3.2）。夜盤收盤時間比日盤晚，
// 用夜盤代表「目前最新」比較貼近參考截圖「台指電子盤」卡片的意圖；當天還沒有
// 夜盤資料就退回日盤。
function latestFuturesQuote(rows) {
  if (!rows?.length) return null;
  return rows.find((row) => row.session === "night") || rows.find((row) => row.session === "day") || rows[0];
}

// 頂部 3 張指數卡片：加權指數／櫃買指數／台指期貨。三者都只有「漲跌幅」而沒有
// 「漲跌點數」欄位（index_ohlc.twse/otc 固定回傳 change_pct，futures_price_daily
// 也只有 change_pct，見同一份契約），所以卡片只顯示 ％，不倒推點數避免四捨五入
// 誤差跟官方公告的點數對不上。
function marketIndexCardHtml(name, value, changePct, key) {
  const hasChange = isValue(changePct);
  const changeClass = hasChange ? (Number(changePct) >= 0 ? "positive" : "negative") : "neutral";
  const arrow = hasChange ? (Number(changePct) >= 0 ? "▲" : "▼") : "";
  const changeText = hasChange ? `${arrow}${pct(Math.abs(Number(changePct)), 2, true)}` : "-";
  return `<button type="button" class="mkt-index-card" data-index-card="${key}">` +
    `<span class="mkt-index-name">${escapeHtml(name)}</span>` +
    `<strong class="mkt-index-value">${fmt(value, 0)}</strong>` +
    `<span class="mkt-index-delta ${changeClass}">${changeText}</span>` +
    `<small class="mkt-index-drill">細項 ▸</small>` +
    `</button>`;
}

function renderMarketIndexCards(overview) {
  const container = byId("market-index-cards");
  if (!container) return;
  const latestIndex = (overview.index_trend || []).at(-1);
  const otc = overview.index_ohlc?.otc;
  const futuresQuote = latestFuturesQuote(overview.index_ohlc?.futures);
  container.innerHTML = [
    marketIndexCardHtml("加權指數", latestIndex?.close_index, latestIndex?.change_pct, "twse"),
    marketIndexCardHtml("櫃買指數", otc?.close_index, otc?.change_pct, "otc"),
    marketIndexCardHtml("台指期貨", futuresQuote?.close, futuresQuote?.change_pct, "futures"),
  ].join("");
  $$('#market-index-cards [data-index-card]').forEach((button) => button.addEventListener("click", () => {
    openIndexCardDrawer(button.dataset.indexCard);
  }));
}

const SYNC_SIGNAL_META = {
  GREEN: { label: "同步", cls: "state-green" },
  YELLOW: { label: "部分背離", cls: "state-yellow" },
  RED: { label: "明顯背離", cls: "state-red" },
};

// Plain-language conclusion for the hero banner. Tone is always "留意" (never
// "應該／建議") per contract §4.4 — this reports an objective sync/diverge fact,
// not a buy/sell call.
function syncSignalText(sync) {
  const spotText = sync.spot_direction === "BUY" ? "現貨買超" : sync.spot_direction === "SELL" ? "現貨賣超" : "現貨方向不明";
  const futuresText = sync.futures_direction === "INCREASING" ? "期貨淨多單增加" : sync.futures_direction === "DECREASING" ? "期貨淨空單增加" : "期貨方向不明";
  if (sync.margin_signal === "法人-散戶對做警訊") {
    return `外資${spotText}同時融資大增，留意法人與散戶對做、現貨拉高出貨的可能性。`;
  }
  if (sync.margin_signal === "築底訊號") {
    return `外資${spotText}同時融資大減，留意浮額出清後的築底訊號。`;
  }
  if (sync.spot_futures_status === "SYNCED") {
    return `外資${spotText}同時${futuresText}，方向一致，留意趨勢是否延續。`;
  }
  if (sync.spot_futures_status === "DIVERGED") {
    return `外資${spotText}但${futuresText}方向不一致，留意現貨與期貨籌碼出現背離。`;
  }
  return "留意大盤現貨、期貨與融資籌碼的同步度變化。";
}

function renderSyncSignal(sync) {
  const badge = byId("sync-signal-badge");
  const label = byId("sync-signal-label");
  const text = byId("sync-signal-text");
  const dateNote = byId("sync-signal-date");
  const facts = byId("sync-signal-facts");
  if (!badge) return;
  if (!sync) {
    badge.className = "sync-badge state-unknown";
    label.textContent = "讀取中";
    text.textContent = "大盤同步度資料讀取中…";
    if (dateNote) dateNote.textContent = "";
    facts.innerHTML = "";
    return;
  }
  if (dateNote) dateNote.textContent = sync.date ? `資料日 ${sync.date}（非即時，收盤後批次計算）` : "";
  if (sync.insufficient_data) {
    badge.className = "sync-badge state-unknown";
    label.textContent = "資料不足";
    text.textContent = "大盤法人／融資融券歷史資料目前累積天數不足，還算不出「相較前一日」的同步度，這不是已判讀出的一般狀態，留意暫時無法給結論。";
  } else {
    const meta = SYNC_SIGNAL_META[sync.signal] || SYNC_SIGNAL_META.YELLOW;
    badge.className = `sync-badge ${meta.cls}`;
    label.textContent = meta.label;
    text.textContent = syncSignalText(sync);
  }
  facts.innerHTML = [
    marketSnapshotItem("現貨方向", sync.spot_direction === "BUY" ? "買超" : sync.spot_direction === "SELL" ? "賣超" : "-"),
    marketSnapshotItem("期貨方向", sync.futures_direction === "INCREASING" ? "淨多單增加" : sync.futures_direction === "DECREASING" ? "淨空單增加" : "-"),
    marketSnapshotItem("現貨期貨", sync.spot_futures_status === "SYNCED" ? "同步" : sync.spot_futures_status === "DIVERGED" ? "背離" : "-"),
    marketSnapshotItem("融資變動", isValue(sync.margin_change_pct) ? pct(sync.margin_change_pct, 2, true) : "-"),
    marketSnapshotItem("融資訊號", sync.margin_signal || "-"),
    marketSnapshotItem("大戶多空一致", sync.large_trader_agree === true ? "一致" : sync.large_trader_agree === false ? "不一致" : "資料待補"),
  ].join("");
}

// 熱門排行 — 台灣前100大成分股（stock_universe_top100）當日五個排行維度，
// 取代舊版「同步燈號驅動」的選股候選清單。首頁只顯示前 5 名，「更多」抽屜
// 顯示同一份資料的完整排行（limit_up/limit_down 本來就只有真的漲跌停的股票，
// 天生就短，不需要額外截斷）。
const STOCK_RANKINGS_INLINE_N = 5;
const STOCK_RANKINGS_TABS = [
  { key: "top_gainers", label: "強勢股" },
  { key: "top_losers", label: "弱勢股" },
  { key: "top_volume", label: "成交量" },
  { key: "limit_up", label: "漲停" },
  { key: "limit_down", label: "跌停" },
];

function stockRankingRow(row) {
  const cls = Number(row.change_pct) >= 0 ? "positive" : "negative";
  const sign = Number(row.change_pct) >= 0 ? "+" : "";
  return `<tr><td>${escapeHtml(row.code)}</td><td>${escapeHtml(row.name)}</td>` +
    `<td>${fmt(row.close, 2)}</td>` +
    `<td class="${cls}">${sign}${pct(row.change_pct, 2, true)}</td>` +
    `<td>${fmt(row.volume, 0)}</td></tr>`;
}

function stockRankingsTableHtml(rows) {
  if (!rows?.length) return `<tr><td colspan="5"><div class="table-empty">今日無符合資料</div></td></tr>`;
  return rows.map(stockRankingRow).join("");
}

function renderStockRankings(data) {
  const table = byId("stock-rankings-table");
  const dateNote = byId("stock-rankings-date");
  const moreButton = byId("stock-rankings-more");
  if (!table) return;
  state.stockRankings = data;
  if (dateNote) {
    dateNote.textContent = data?.universe_date
      ? `台灣前100大成分股（${data.universe_date}，共 ${fmt(data.universe_size, 0)} 檔），不含目標價或買賣建議`
      : "台灣前100大成分股，不含目標價或買賣建議";
  }
  const activeTab = state.stockRankingsTab || STOCK_RANKINGS_TABS[0].key;
  const rows = data?.[activeTab] || [];
  table.innerHTML = `<thead><tr><th>代碼</th><th>名稱</th><th>現價</th><th>漲跌幅</th><th>成交量(張)</th></tr></thead>` +
    `<tbody>${stockRankingsTableHtml(rows.slice(0, STOCK_RANKINGS_INLINE_N))}</tbody>`;
  if (moreButton) moreButton.classList.toggle("hidden", rows.length <= STOCK_RANKINGS_INLINE_N);
}

function openStockRankingsDrawer() {
  const data = state.stockRankings;
  const activeTab = state.stockRankingsTab || STOCK_RANKINGS_TABS[0].key;
  const tabMeta = STOCK_RANKINGS_TABS.find((t) => t.key === activeTab);
  const rows = data?.[activeTab] || [];
  openDrawer(`熱門排行 · ${tabMeta.label}（共 ${rows.length} 檔）`, `
    <table class="data-table"><thead><tr><th>代碼</th><th>名稱</th><th>現價</th><th>漲跌幅</th><th>成交量(張)</th></tr></thead>
    <tbody>${stockRankingsTableHtml(rows)}</tbody></table>
  `);
}

// 長條圖的 fill 是實色（不是大面積色塊），只需要紅漲/綠跌兩態，不需要舊版方塊熱力圖
// 那種 3 階透明度分層（那是為了在大面積色塊上做強度漸層設計的，細長條上會顯得很淡、
// 看不清楚），維持紅=買超/漲、綠=賣超/跌的全站色彩慣例（跟 .positive/.negative 一致）。
function flowHeatClass(value) {
  if (!isValue(value)) return "is-empty";
  return Number(value) >= 0 ? "is-gain" : "is-loss";
}

// 橫向長條圖，不是方塊熱力圖——原本用 flexbox flex-grow 排 tile 想模擬「面積＝成交值」，
// 但 flexbox 是一維排版，flex-wrap 換行後每一行各自重新分配寬度比例，行與行之間的比例
// 基準不一致，加上先前為了讓中文產業名不被截斷而加的 min-width 下限，實際視覺上大小
// 差異遠小於真實成交值的差異（使用者反饋「面積沒有如實地呈現」，這是真的，不是誤會）。
// 長條圖用 width:X% 直接對應 turnover/maxTurnover，是唯一能保證線性比例、不受版面
// 換行影響的做法；文字標籤放在固定寬度欄位，不會被長條長度擠壓。
// 顏色 = change_pct 正負與相對強度（紅漲／綠跌，見 flowHeatClass）。net_amount（三大
// 法人買賣超張數）是輔助數字，不是顏色/長度依據——大部分產業沒有法人資料（null，不是
// 0），存在性判斷只能看 turnover，不能看 net_amount。
function renderIndustryFlowTreemap(rows) {
  const container = byId("industry-flow-treemap");
  const meta = byId("industry-flow-meta");
  if (!container) return;
  const data = (rows || []).filter((row) => isValue(row.turnover) && Number(row.turnover) > 0);
  state.industryFlowRows = data;
  if (!data.length) {
    container.innerHTML = emptyHtml("尚無產業資金流向資料（依成交金額）");
    if (meta) meta.textContent = "";
    return;
  }
  const maxTurnover = Math.max(...data.map((row) => Number(row.turnover)), 1);
  if (meta) {
    meta.textContent = `資料日 ${data[0]?.date || "-"}｜長條＝成交金額（線性比例）｜顏色＝漲跌方向（紅漲／綠跌）｜另列三大法人買賣超張數，"－"代表該產業無法人資料｜點擊任一產業看成分股`;
  }
  container.innerHTML = data.map((row, i) => {
    const width = Math.max((Number(row.turnover) / maxTurnover) * 100, 1).toFixed(2);
    const heat = flowHeatClass(row.change_pct);
    const changeText = isValue(row.change_pct) ? `${Number(row.change_pct) >= 0 ? "+" : ""}${pct(row.change_pct, 2, true)}` : "－";
    const turnoverText = `${fmt(Number(row.turnover) / 1e8, 2)} 億`;
    const netText = isValue(row.net_amount) ? `${fmt(row.net_amount, 0)} 張` : "－";
    const tip = `${row.industry}｜漲跌幅 ${changeText}｜成交值 ${turnoverText}｜買賣超 ${netText}｜成分股 ${fmt(row.member_count, 0)} 檔｜${row.date}`;
    return `<div class="flow-bar-row" data-flow-idx="${i}" title="${escapeHtml(tip)}">` +
      `<span class="flow-bar-label">${escapeHtml(row.industry)}</span>` +
      `<div class="flow-bar-track"><div class="flow-bar-fill ${heat}" style="width:${width}%;"></div></div>` +
      `<span class="flow-bar-pct ${heat}">${changeText}</span>` +
      `<span class="flow-bar-turnover">${turnoverText}</span>` +
      `<span class="flow-bar-net">${netText}</span>` +
      `<span class="flow-bar-members">${fmt(row.member_count, 0)} 檔</span>` +
      `</div>`;
  }).join("");
}

function industryFlowMembersRows(members) {
  if (!members?.length) return `<tr><td colspan="5"><div class="table-empty">尚無成分股資料</div></td></tr>`;
  return members.map((m) => {
    const cls = Number(m.change_pct) >= 0 ? "positive" : "negative";
    const sign = Number(m.change_pct) >= 0 ? "+" : "";
    return `<tr><td>${escapeHtml(m.code)}</td><td>${escapeHtml(m.name)}</td>` +
      `<td class="${cls}">${sign}${pct(m.change_pct, 2, true)}</td>` +
      `<td>${fmt(Number(m.turnover) / 1e8, 2)} 億</td>` +
      `<td>${fmt(m.close, 2)}</td></tr>`;
  }).join("");
}

function openIndustryFlowDrawer(row) {
  const members = row?.members || [];
  openDrawer(`產業成分股 · ${row.industry}（共 ${members.length} 檔）`, `
    <table class="data-table"><thead><tr><th>代碼</th><th>名稱</th><th>漲跌幅</th><th>成交值</th><th>收盤價</th></tr></thead>
    <tbody>${industryFlowMembersRows(members)}</tbody></table>
  `);
}

byId("industry-flow-treemap")?.addEventListener("click", (event) => {
  const tile = event.target.closest(".flow-bar-row[data-flow-idx]");
  if (!tile) return;
  const row = state.industryFlowRows?.[Number(tile.dataset.flowIdx)];
  if (row) openIndustryFlowDrawer(row);
});

// 產業排行（漲幅／跌幅／成交量／成交金額）— 取代「產業資金流向」原本唯一的
// treemap 視角，treemap 收進下方 <details> 摺疊區塊，不刪除只降階。
const INDUSTRY_RANKINGS_INLINE_N = 6;
const INDUSTRY_RANKINGS_TABS = [
  { key: "top_gainers", all: "all_by_gainers", label: "漲幅", unit: "change_pct" },
  { key: "top_losers", all: "all_by_losers", label: "跌幅", unit: "change_pct" },
  { key: "top_volume", all: "all_by_volume", label: "成交量", unit: "volume" },
  { key: "top_turnover", all: "all_by_turnover", label: "成交金額", unit: "turnover" },
];

function industryRankingValue(row, unit) {
  if (unit === "change_pct") {
    const cls = Number(row.change_pct) >= 0 ? "positive" : "negative";
    const sign = Number(row.change_pct) >= 0 ? "+" : "";
    return `<span class="${cls}">${sign}${pct(row.change_pct, 2, true)}</span>`;
  }
  if (unit === "volume") return `${fmt(row.volume, 0)} 張`;
  return `${fmt(Number(row.turnover) / 1e8, 2)} 億`;
}

function industryRankingRows(rows, unit) {
  if (!rows?.length) return emptyHtml("今日無產業排行資料");
  return rows.map((row, i) => `<div class="industry-ranking-row">` +
    `<span class="industry-ranking-rank">${i + 1}</span>` +
    `<span class="industry-ranking-name">${escapeHtml(row.industry)}<small>${fmt(row.member_count, 0)} 檔成分股</small></span>` +
    `<span class="industry-ranking-value">${industryRankingValue(row, unit)}</span></div>`).join("");
}

function renderIndustryRankings(data) {
  const listEl = byId("industry-rankings-list");
  const meta = byId("industry-rankings-meta");
  const moreButton = byId("industry-rankings-more");
  if (!listEl) return;
  state.industryRankings = data;
  const activeTab = state.industryRankingsTab || INDUSTRY_RANKINGS_TABS[0].key;
  const tabMeta = INDUSTRY_RANKINGS_TABS.find((t) => t.key === activeTab);
  const rows = data?.[activeTab] || [];
  listEl.innerHTML = industryRankingRows(rows.slice(0, INDUSTRY_RANKINGS_INLINE_N), tabMeta.unit);
  if (meta) meta.textContent = data?.date ? `資料日 ${data.date}｜依 stock_industry_chain 產業分組` : "";
  if (moreButton) moreButton.classList.toggle("hidden", rows.length <= INDUSTRY_RANKINGS_INLINE_N);
}

function openIndustryRankingsDrawer() {
  const data = state.industryRankings;
  const activeTab = state.industryRankingsTab || INDUSTRY_RANKINGS_TABS[0].key;
  const tabMeta = INDUSTRY_RANKINGS_TABS.find((t) => t.key === activeTab);
  const rows = data?.[tabMeta.all] || [];
  openDrawer(`產業排行 · ${tabMeta.label}（共 ${rows.length} 個產業）`, `
    <div class="industry-ranking-list">${industryRankingRows(rows, tabMeta.unit)}</div>
  `);
}

// 加權指數貢獻排行 — 依市值占比反推的估算值（見 index_contribution 契約），不是交易所
// 官方逐筆貢獻數字，所以卡頭 meta 文字跟 title tooltip 都要講明「估算」。
function contributionRows(list, positive) {
  if (!list?.length) {
    return `<tr><td colspan="3"><div class="table-empty">今日無${positive ? "正" : "負"}貢獻資料</div></td></tr>`;
  }
  return list.map((row, i) => {
    const cls = Number(row.contribution_pts) >= 0 ? "positive" : "negative";
    const sign = Number(row.contribution_pts) >= 0 ? "+" : "";
    return `<tr><td class="contribution-rank">${i + 1}</td>` +
      `<td class="contribution-name"><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.code)}</span></td>` +
      `<td class="contribution-pts ${cls}">${sign}${fmt(row.contribution_pts, 2)}</td></tr>`;
  }).join("");
}

const INDEX_CONTRIBUTION_INLINE_N = 5;

function renderIndexContribution(data) {
  const posTable = byId("index-contribution-positive");
  const negTable = byId("index-contribution-negative");
  const meta = byId("index-contribution-meta");
  const moreButton = byId("index-contribution-more");
  if (!posTable || !negTable) return;
  posTable.innerHTML = `<tbody>${contributionRows(data?.top_positive?.slice(0, INDEX_CONTRIBUTION_INLINE_N), true)}</tbody>`;
  negTable.innerHTML = `<tbody>${contributionRows(data?.top_negative?.slice(0, INDEX_CONTRIBUTION_INLINE_N), false)}</tbody>`;
  if (meta) {
    meta.textContent = data
      ? `權重資料日 ${data.weight_data_date || "-"}｜估算值，依市值占比推算，非官方精確數字`
      : "待補加權指數貢獻排行資料";
  }
  if (moreButton) {
    const hasMore = (data?.top_positive?.length || 0) > INDEX_CONTRIBUTION_INLINE_N
      || (data?.top_negative?.length || 0) > INDEX_CONTRIBUTION_INLINE_N;
    moreButton.classList.toggle("hidden", !hasMore);
  }
}

function openIndexContributionDrawer() {
  const data = state.marketOverview?.index_contribution;
  if (!data) return;
  openDrawer("加權指數貢獻排行（前 20 名）", `
    <div class="contribution-columns">
      <div><div class="contribution-head gain">正貢獻</div><table class="data-table contribution-table"><tbody>${contributionRows(data.top_positive, true)}</tbody></table></div>
      <div><div class="contribution-head loss">負貢獻</div><table class="data-table contribution-table"><tbody>${contributionRows(data.top_negative, false)}</tbody></table></div>
    </div>
  `);
}

// 個股漲跌分佈 — 11 桶區間長條圖 + 漲停/跌停統計卡。月新高／月新低目前資料庫累積天數
// 不足以計算（見 market-daily-digest 契約），這裡故意不生 0，也不整卡拿掉，改用
// "資料累積中" + title tooltip 明講原因，避免使用者誤以為當天真的 0 檔創新高/新低。
function changeStatTile(label, valueHtml, valueClass, note, clickKey) {
  return `<div class="change-stat-tile${clickKey ? " clickable" : ""}"${clickKey ? ` data-drill="${clickKey}"` : ""}>` +
    `<span>${escapeHtml(label)}</span>` +
    `<strong class="${valueClass}">${valueHtml}</strong>` +
    (note ? `<small title="${escapeHtml(note)}">${escapeHtml(note)}</small>` : "") +
    `</div>`;
}

// 漲停/跌停個股清單 — 每檔股票同時帶 industry（FinMind 細產業，可能多筆）跟
// official_sector（TWSE 官方產業別，固定一個），兩個分類系統分開顯示，不合併。
function taggedStockRow(row) {
  const cls = Number(row.change_pct) >= 0 ? "positive" : "negative";
  const sign = Number(row.change_pct) >= 0 ? "+" : "";
  const industryText = row.industry?.length ? row.industry.join("、") : "無細產業標籤";
  return `<tr><td>${escapeHtml(row.code)}</td><td>${escapeHtml(row.name)}</td>` +
    `<td class="${cls}">${sign}${pct(row.change_pct, 2, true)}</td>` +
    `<td>${escapeHtml(row.official_sector || "-")}</td>` +
    `<td>${escapeHtml(industryText)}</td></tr>`;
}

const CHANGE_DISTRIBUTION_DRILL_META = {
  limit_up: { field: "limit_up_stocks", label: "漲停" },
  limit_down: { field: "limit_down_stocks", label: "跌停" },
  monthly_high: { field: "monthly_high_stocks", label: "股價月新高" },
  monthly_low: { field: "monthly_low_stocks", label: "股價月新低" },
};

function openChangeDistributionDrawer(key) {
  const data = state.marketOverview?.stock_change_distribution;
  const meta = CHANGE_DISTRIBUTION_DRILL_META[key];
  if (!meta) return;
  const rows = data?.[meta.field];
  const body = rows?.length
    ? `<table class="data-table"><thead><tr><th>代碼</th><th>名稱</th><th>漲跌幅</th><th>官方產業別</th><th>細產業</th></tr></thead>` +
      `<tbody>${rows.map(taggedStockRow).join("")}</tbody></table>`
    : emptyHtml(`今日無${meta.label}個股`);
  openDrawer(`${meta.label}個股（共 ${rows?.length || 0} 檔）`, body);
}

// index 5 是 "0%" 那一桶；離中心越遠（>5%／<-5% 那兩端）heat-tier 越深，
// 手法照抄 flowHeatClass／industry-treemap 的 gain-heat/loss-heat/heat-tier-N。
function changeBucketHeat(index, count) {
  if (!count) return "";
  if (index === 5) return "neutral-bar";
  const distance = Math.abs(index - 5);
  const tier = distance >= 4 ? 3 : distance >= 2 ? 2 : 1;
  return index < 5 ? `gain-heat heat-tier-${tier}` : `loss-heat heat-tier-${tier}`;
}

function renderStockChangeDistribution(data) {
  const dateNote = byId("stock-change-distribution-date");
  const statsEl = byId("stock-change-stats");
  const bucketsEl = byId("stock-change-buckets");
  const summaryEl = byId("stock-change-summary");
  if (!statsEl || !bucketsEl) return;
  if (!data) {
    if (dateNote) dateNote.textContent = "資料讀取中…";
    statsEl.innerHTML = emptyHtml("待補個股漲跌分佈資料");
    bucketsEl.innerHTML = "";
    if (summaryEl) summaryEl.innerHTML = "";
    return;
  }
  if (dateNote) dateNote.textContent = `資料日 ${data.date || "-"}`;
  const newHighNote = "資料庫目前累積的歷史交易日還不夠計算「股價月新高」（需要近 20 個交易日），需要更多交易日歷史才能提供，不是 0 檔";
  const newLowNote = "資料庫目前累積的歷史交易日還不夠計算「股價月新低」（需要近 20 個交易日），需要更多交易日歷史才能提供，不是 0 檔";
  const monthlyHighReady = data.monthly_high_count !== null && data.monthly_high_count !== undefined;
  const monthlyLowReady = data.monthly_low_count !== null && data.monthly_low_count !== undefined;
  statsEl.innerHTML = [
    changeStatTile("漲停", fmt(data.limit_up_count, 0), "positive", null, data.limit_up_count > 0 ? "limit_up" : null),
    monthlyHighReady
      ? changeStatTile("股價月新高", fmt(data.monthly_high_count, 0), "positive", null, data.monthly_high_count > 0 ? "monthly_high" : null)
      : changeStatTile("股價月新高", "資料累積中", "pending", newHighNote),
    monthlyLowReady
      ? changeStatTile("股價月新低", fmt(data.monthly_low_count, 0), "negative", null, data.monthly_low_count > 0 ? "monthly_low" : null)
      : changeStatTile("股價月新低", "資料累積中", "pending", newLowNote),
    changeStatTile("跌停", fmt(data.limit_down_count, 0), "negative", null, data.limit_down_count > 0 ? "limit_down" : null),
  ].join("");
  $$("#stock-change-stats .change-stat-tile.clickable").forEach((tile) => {
    tile.addEventListener("click", () => openChangeDistributionDrawer(tile.dataset.drill));
  });
  const buckets = data.buckets || [];
  const maxCount = Math.max(...buckets.map((b) => Number(b.count) || 0), 1);
  bucketsEl.innerHTML = buckets.map((b, i) => {
    const count = Number(b.count) || 0;
    const heightPct = Math.max((count / maxCount) * 100, count > 0 ? 3 : 0);
    const heat = changeBucketHeat(i, count);
    return `<div class="change-bucket" title="${escapeHtml(b.label)}：${fmt(b.count, 0)} 檔">` +
      `<span class="change-bucket-count">${fmt(b.count, 0)}</span>` +
      `<div class="change-bucket-bar ${heat}" style="height:${heightPct}%;"></div>` +
      `<small>${escapeHtml(b.label)}</small></div>`;
  }).join("");
  if (summaryEl) {
    summaryEl.innerHTML = `<span class="positive">▲ ${fmt(data.up_count, 0)} 檔上漲</span>` +
      `<span class="change-flat">平盤 ${fmt(data.flat_count, 0)} 檔</span>` +
      `<span class="negative">▼ ${fmt(data.down_count, 0)} 檔下跌</span>`;
  }
}

// 類股成交金額比重分佈 — 橫向長條圖，用 --mkt-accent（比重語意）跟 .positive/.negative
// 的漲跌語意分開，呼應既有排版「面積/顏色分工要單一」的原則。
function renderIndustryTurnoverShare(rows) {
  const container = byId("industry-turnover-bars");
  if (!container) return;
  const data = rows || [];
  if (!data.length) {
    container.innerHTML = emptyHtml("待補類股成交金額比重資料");
    return;
  }
  const maxPct = Math.max(...data.map((row) => Number(row.pct_of_total) || 0), 1);
  container.innerHTML = data.map((row) => {
    const width = Math.max(((Number(row.pct_of_total) || 0) / maxPct) * 100, 2);
    const tip = `${row.industry}｜成交金額 ${fmt(row.turnover, 0)} 元｜占大盤 ${pct(row.pct_of_total, 2, true)}｜成分股 ${fmt(row.member_count, 0)} 檔`;
    return `<div class="turnover-bar-row" title="${escapeHtml(tip)}">` +
      `<span class="turnover-bar-label">${escapeHtml(row.industry)}</span>` +
      `<div class="turnover-bar-track"><div class="turnover-bar-fill" style="width:${width}%;"></div></div>` +
      `<span class="turnover-bar-pct">${pct(row.pct_of_total, 2, true)}</span></div>`;
  }).join("");
}

// 大盤委買委賣小卡 — 這不是即時累積委託，是「收盤前最後一次揭示」的加總，且只有
// TWSE（上市）有這個欄位（TPEX 官方端點沒有揭示量），文字必須把兩件事都講清楚，
// 不能讓人誤以為是即時或全市場數字。
function renderMarketOrderBook(data) {
  const el = byId("market-order-book");
  if (!el) return;
  if (!data) { el.innerHTML = ""; return; }
  const tip = "上市（TWSE）收盤前最後一次揭示的委買委賣張數加總，不是即時委託、也不是全日累積委託量；上櫃官方端點沒有揭示量欄位，故不含上櫃";
  el.innerHTML = `<span class="order-book-label" title="${escapeHtml(tip)}">尾盤最後揭示委買委賣（上市，張）</span>` +
    `<span class="order-book-figures"><b class="positive">委買 ${fmt(data.total_bid_volume, 0)}</b><b class="negative">委賣 ${fmt(data.total_ask_volume, 0)}</b></span>` +
    `<small>資料日 ${data.date || "-"}</small>`;
}

function renderMarketOverview(overview) {
  state.marketOverview = overview;
  const trend = overview.index_trend || [];
  drawChart(byId("chart-market-index"), [
    { name: "加權指數", values: trend.map((row) => row.close_index), digits: 0 },
  ], trend.map((row) => row.date), { labelCount: 8 });
  renderMarketIndexCards(overview);
  renderIndexOhlc(overview.index_ohlc);
  renderMarketOrderBook(overview.market_order_book);
  renderIndexContribution(overview.index_contribution);
  renderStockChangeDistribution(overview.stock_change_distribution);
  renderMarketInstitutionalTable(overview.institutional_trading);
  renderMarketMarginTable(overview.margin_short);
  renderMarketFutures(overview.futures || []);
  renderFuturesLargeTrader(overview.futures_large_trader || []);
  renderIndustryTurnoverShare(overview.industry_turnover_share);
  renderSyncSignal(overview.sync_signal);
  renderStockRankings(overview.stock_rankings);
  renderIndustryRankings(overview.industry_rankings);
  renderIndustryFlowTreemap(overview.industry_capital_flow);
  renderSectorMomentum(overview.sector_momentum);
  renderMarketSnapshotCard(overview);
}

// 市值占大盤比重降到第二層 — 資料本身不常變，收進「更多」抽屜，不佔
// market-overview-grid 版面。
function openMarketCapShareDrawer() {
  const rows = state.marketOverview?.market_cap?.slice(0, 50) || [];
  const table = document.createElement("table");
  table.className = "data-table";
  tableFromRows(table, rows, [
    { key: "rank", label: "#" }, { key: "code", label: "代碼" },
    { key: "name", label: "名稱" },
    { key: "pct_of_market", label: "大盤比重", format: (v) => pct(v, 3) },
    { key: "date", label: "資料日期" },
  ], "待補全市場流通股本與市值資料源");
  openDrawer("市值占大盤比重（全市場前 50 名）", table.outerHTML);
}

function marketSnapshotItem(label, value) {
  return `<div><span>${escapeHtml(label)}</span><b>${value}</b></div>`;
}

function renderMarketSnapshotCard(overview) {
  const body = byId("market-snapshot-body");
  if (!body) return;
  if (!overview) { body.innerHTML = emptyHtml("大盤資料讀取中"); return; }
  const trend = overview.index_trend || [];
  const latestIndex = trend.at(-1);
  const twseInstitutional = (overview.institutional_trading || []).find(
    (row) => row.market === "TWSE" && row.institution === "合計",
  );
  const twseMargin = (overview.margin_short || []).find((row) => row.market === "TWSE");
  // change_pct 已經是百分比數值（例如 0.65 代表 0.65%），不是要再乘 100 的小數，
  // 不能沿用 signedPct（它假設輸入是小數），這裡直接用 pct(..., alreadyPercent=true)。
  const indexChangeText = latestIndex && isValue(latestIndex.change_pct)
    ? `${Number(latestIndex.change_pct) >= 0 ? "+" : ""}${pct(latestIndex.change_pct, 2, true)}`
    : "-";
  body.innerHTML = [
    marketSnapshotItem(
      "加權指數",
      latestIndex ? `${fmt(latestIndex.close_index, 0)}（${indexChangeText}）` : "-",
    ),
    marketSnapshotItem(
      "三大法人合計買賣超(上市)",
      twseInstitutional && isValue(twseInstitutional.net_amount)
        ? `${fmt(Number(twseInstitutional.net_amount) / 1e8, 2)} 億`
        : "-",
    ),
    marketSnapshotItem(
      "融資餘額(上市)",
      twseMargin ? `${fmt(twseMargin.margin_balance, 0)} 張` : "-",
    ),
  ].join("");
}

let marketOverviewLoaded = false;
async function loadMarketOverview() {
  try {
    const overview = await fetchJson(`${API}/market/overview`);
    renderMarketOverview(overview);
    if (state.indexComparisonActive) renderIndexComparison(overview);
  } catch (error) {
    showError(`大盤總覽載入失敗：${error.message}`);
  }
}

function showMarketOverviewTab() {
  if (state.indexComparisonActive) hideIndexComparisonTab();
  byId("empty-state").classList.add("hidden");
  byId("stock-header").classList.add("hidden");
  byId("freshness-rail").classList.add("hidden");
  byId("workspace-nav").classList.add("hidden");
  byId("workspace").classList.add("hidden");
  byId("refresh-button").classList.add("hidden");
  byId("market-overview-panel").classList.remove("hidden");
  byId("market-overview-tab").classList.add("active");
  byId("market-overview-tab").setAttribute("aria-pressed", "true");
  state.marketOverviewActive = true;
  history.replaceState(null, "", state.code
    ? `?code=${encodeURIComponent(state.code)}&view=${state.view}&panel=market-overview`
    : "?panel=market-overview");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function hideMarketOverviewTab() {
  byId("market-overview-panel").classList.add("hidden");
  byId("market-overview-tab").classList.remove("active");
  byId("market-overview-tab").setAttribute("aria-pressed", "false");
  state.marketOverviewActive = false;
  if (state.code) {
    byId("stock-header").classList.remove("hidden");
    byId("freshness-rail").classList.remove("hidden");
    byId("workspace-nav").classList.remove("hidden");
    byId("workspace").classList.remove("hidden");
    byId("refresh-button").classList.remove("hidden");
    history.replaceState(null, "", `?code=${encodeURIComponent(state.code)}&view=${state.view}`);
  } else {
    byId("empty-state").classList.remove("hidden");
    history.replaceState(null, "", "/");
  }
}

function showIndexComparisonTab() {
  if (state.marketOverviewActive) hideMarketOverviewTab();
  byId("empty-state").classList.add("hidden");
  byId("stock-header").classList.add("hidden");
  byId("freshness-rail").classList.add("hidden");
  byId("workspace-nav").classList.add("hidden");
  byId("workspace").classList.add("hidden");
  byId("refresh-button").classList.add("hidden");
  byId("index-comparison-panel").classList.remove("hidden");
  byId("index-comparison-tab").classList.add("active");
  byId("index-comparison-tab").setAttribute("aria-pressed", "true");
  state.indexComparisonActive = true;
  history.replaceState(null, "", state.code
    ? `?code=${encodeURIComponent(state.code)}&view=${state.view}&panel=index-comparison`
    : "?panel=index-comparison");
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (state.marketOverview) renderIndexComparison(state.marketOverview);
}

function hideIndexComparisonTab() {
  byId("index-comparison-panel").classList.add("hidden");
  byId("index-comparison-tab").classList.remove("active");
  byId("index-comparison-tab").setAttribute("aria-pressed", "false");
  state.indexComparisonActive = false;
  if (state.code) {
    byId("stock-header").classList.remove("hidden");
    byId("freshness-rail").classList.remove("hidden");
    byId("workspace-nav").classList.remove("hidden");
    byId("workspace").classList.remove("hidden");
    byId("refresh-button").classList.remove("hidden");
    history.replaceState(null, "", `?code=${encodeURIComponent(state.code)}&view=${state.view}`);
  } else {
    byId("empty-state").classList.remove("hidden");
    history.replaceState(null, "", "/");
  }
}

let sectorMomentumData = [];
let sectorMomentumSort = { key: "rank", dir: "desc" };

function momentumSortRows(rows, sort) {
  return [...rows].sort((a, b) => {
    const left = a[sort.key];
    const right = b[sort.key];
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    const comparison = typeof left === "string"
      ? left.localeCompare(right, "zh-Hant", { numeric: true })
      : Number(left) - Number(right);
    return sort.dir === "asc" ? comparison : -comparison;
  });
}

function infoTip(text) {
  return `<button type="button" class="info-tip" data-tip="${escapeHtml(text)}" aria-label="說明：${escapeHtml(text)}">?</button>`;
}

const RANK_BAND_TIP = "20R／60R／120R：近 20／60／120 個交易日報酬，在所有板塊間的百分位排名（0–99，越高代表這段期間漲幅相對最強）。Rank：綜合分數 = 20R×20% + 60R×40% + 120R×40%，兼顧短中長期動能。";
const REL_BAND_TIP = "REL = 板塊同期報酬 − 大盤（發行量加權股價指數）同期報酬。正值代表這段期間跑贏大盤，負值代表落後大盤。";
const MEMBER_COUNT_TIP = "這個細產業目前有幾檔「台灣前100大」成分股列入合成指數。檔數越少（例如只有1、2檔），指數越接近少數個股走勢，排名參考價值較低。";

function momentumSortHeader(key, label) {
  const active = sectorMomentumSort.key === key;
  const direction = active ? sectorMomentumSort.dir : "none";
  return `<th scope="col"${active ? ` aria-sort="${direction === "desc" ? "descending" : "ascending"}"` : ""}>` +
    `<button type="button" class="table-sort${active ? ` active ${direction}` : ""}" data-sort-key="${key}">${escapeHtml(label)}</button></th>`;
}

function sectorName(value) {
  return String(value || "-").replace(/指數$/, "");
}

function momentumRankGroup(value) {
  if (!isValue(value)) return "missing";
  if (Number(value) >= 67) return "leader";
  if (Number(value) >= 34) return "middle";
  return "lagger";
}

const _SECTOR_GROUPS = [
  { key: "leader", label: "領先板塊", detail: "Rank 67–99" },
  { key: "middle", label: "中段板塊", detail: "Rank 34–66" },
  { key: "lagger", label: "落後板塊", detail: "Rank 0–33" },
  { key: "missing", label: "資料不足", detail: "無法計算完整 Rank" },
];

function signedHeatClass(value) {
  if (!isValue(value)) return "metric-heat is-empty";
  const points = Math.abs(Number(value) * 100);
  const strength = points >= 15 ? 3 : points >= 5 ? 2 : 1;
  return `metric-heat ${Number(value) >= 0 ? "gain-heat" : "loss-heat"} heat-tier-${strength}`;
}

// 行內版比較徽章：套用跟 signedHeatClass 同一組三級色階（gain-heat/loss-heat/heat-tier-N），
// 只是換掉表格 <td> 專用的 metric-heat 基底 class，改成小 pill 形狀，方便貼在卡片、統計數字旁。
function deltaChip(value, digits = 1) {
  const heatClass = signedHeatClass(value).replace("metric-heat", "delta-chip");
  return `<span class="${heatClass}">${signedPct(value, digits)}</span>`;
}

function renderMomentumSummary(mode, rows) {
  const summary = byId("momentum-summary");
  const data = rows || [];
  if (!data.length) {
    summary.innerHTML = `<div><span>${mode === "sector" ? "資料日" : "資料狀態"}</span><strong>尚無資料</strong></div>` +
      `<div><span>${mode === "sector" ? "板塊數" : "產業群"}</span><strong>0</strong></div>` +
      `<div><span>${mode === "sector" ? "強勢板塊" : "細產業"}</span><strong>0</strong></div>` +
      `<div><span>目前領先</span><strong>—</strong></div>`;
    return;
  }
  if (mode === "sector") {
    const dates = data.map((row) => row.date).filter(Boolean).sort();
    const leaderCount = data.filter((row) => momentumRankGroup(row.rank) === "leader").length;
    const leading = momentumSortRows(data, { key: "rank", dir: "desc" })[0];
    summary.innerHTML = `<div><span>資料日</span><strong>${escapeHtml(dates.at(-1) || "-")}</strong></div>` +
      `<div><span>板塊數</span><strong>${fmt(data.length, 0)}</strong></div>` +
      `<div><span>強勢板塊</span><strong>${fmt(leaderCount, 0)}</strong><small>Rank ≥ 67</small></div>` +
      `<div><span>目前領先</span><strong title="${escapeHtml(leading?.index_name)}">${escapeHtml(sectorName(leading?.index_name))}</strong></div>`;
    return;
  }
  const subCount = data.reduce((total, row) => total + (row.sub_industries?.length || 0), 0);
  const leading = momentumSortRows(data, { key: "rank", dir: "desc" })[0];
  summary.innerHTML = `<div><span>資料狀態</span><strong>靜態快照</strong></div>` +
    `<div><span>產業群</span><strong>${fmt(data.length, 0)}</strong></div>` +
    `<div><span>可展開細產業</span><strong>${fmt(subCount, 0)}</strong></div>` +
    `<div><span>目前領先</span><strong title="${escapeHtml(leading?.industry)}">${escapeHtml(leading?.industry)}</strong></div>`;
}

function sectorMomentumRow(row) {
  const oneDayClass = row.change_pct_1d == null ? "" : row.change_pct_1d >= 0 ? "positive" : "negative";
  return `<tr>` +
    `<th scope="row" class="momentum-name"><strong>${escapeHtml(sectorName(row.index_name))}</strong><small>TWSE 類股指數</small></th>` +
    `<td class="momentum-price">${fmt(row.close_index, 2)}</td>` +
    `<td class="${oneDayClass}">${pct(row.change_pct_1d, 2, true)}</td>` +
    `<td class="trend-cell">${sparklineSvg(row.trend)}</td>` +
    `<td class="${rankHeatClass(row.rank_20d)}">${fmt(row.rank_20d, 0)}</td>` +
    `<td class="${rankHeatClass(row.rank_60d)}">${fmt(row.rank_60d, 0)}</td>` +
    `<td class="${rankHeatClass(row.rank_120d)}">${fmt(row.rank_120d, 0)}</td>` +
    `<td class="${rankHeatClass(row.rank)} composite-rank">${fmt(row.rank, 0)}</td>` +
    `<td class="${signedHeatClass(row.rel_20d)}">${pct(row.rel_20d, 2)}</td>` +
    `<td class="${signedHeatClass(row.rel_60d)}">${pct(row.rel_60d, 2)}</td>` +
    `<td class="${signedHeatClass(row.rel_120d)}">${pct(row.rel_120d, 2)}</td>` +
    `<td class="momentum-date">${escapeHtml(row.date)}</td></tr>`;
}

function renderSectorMomentum(rows) {
  if (rows !== undefined) sectorMomentumData = rows || [];
  const table = byId("sector-momentum-table");
  renderMomentumSummary("sector", sectorMomentumData);
  if (!sectorMomentumData.length) { emptyTable(table, 12, "板塊指數資料尚未回補"); return; }

  const body = _SECTOR_GROUPS.map((group) => {
    const groupedRows = momentumSortRows(
      sectorMomentumData.filter((row) => momentumRankGroup(row.rank) === group.key),
      sectorMomentumSort,
    );
    if (!groupedRows.length) return "";
    return `<tr class="momentum-group momentum-group-${group.key}"><th colspan="12" scope="rowgroup">` +
      `<span>${group.label}</span><small>${group.detail} · ${groupedRows.length} 個</small></th></tr>` +
      groupedRows.map(sectorMomentumRow).join("");
  }).join("");

  table.innerHTML = `<caption class="sr-only">TWSE 官方板塊短中長期動能排名與相對大盤報酬</caption>` +
    `<colgroup><col class="col-name"><col class="col-price"><col class="col-day"><col class="col-trend">` +
    `<col class="col-rank"><col class="col-rank"><col class="col-rank"><col class="col-rank">` +
    `<col class="col-rel"><col class="col-rel"><col class="col-rel"><col class="col-date"></colgroup>` +
    `<thead><tr class="momentum-band-row">` +
    `<th rowspan="2" scope="col">板塊</th><th rowspan="2" scope="col">收盤</th><th rowspan="2" scope="col">1D%</th>` +
    `<th rowspan="2" scope="col">120 日走勢</th><th colspan="4" scope="colgroup" class="rank-band">強度排名${infoTip(RANK_BAND_TIP)}</th>` +
    `<th colspan="3" scope="colgroup" class="rel-band">相對大盤${infoTip(REL_BAND_TIP)}</th><th rowspan="2" scope="col">資料日</th></tr>` +
    `<tr>${momentumSortHeader("rank_20d", "20R")}${momentumSortHeader("rank_60d", "60R")}` +
    `${momentumSortHeader("rank_120d", "120R")}${momentumSortHeader("rank", "Rank")}` +
    `${momentumSortHeader("rel_20d", "REL20")}${momentumSortHeader("rel_60d", "REL60")}` +
    `${momentumSortHeader("rel_120d", "REL120")}</tr></thead><tbody>${body}</tbody>`;

  $$(".table-sort", table).forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.sortKey;
    sectorMomentumSort = sectorMomentumSort.key === key
      ? { key, dir: sectorMomentumSort.dir === "desc" ? "asc" : "desc" }
      : { key, dir: "desc" };
    renderSectorMomentum();
  }));
}

// 純函式：走勢陣列 -> 一小段 inline SVG 折線圖。不重用 drawChart —— 那個是含座標軸／
// 圖例的全功能圖表，對表格裡每一列都畫一份太重；這裡只要「漲跌形狀 + 紅漲綠跌」。
function sparklineSvg(trend) {
  const values = (trend || []).map(Number).filter(Number.isFinite);
  if (values.length < 2) return `<span class="sparkline-empty">—</span>`;
  const width = 88;
  const height = 24;
  const pad = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (width - pad * 2) / (values.length - 1);
  const points = values.map((value, index) => {
    const x = pad + index * stepX;
    const y = height - pad - ((value - min) / span) * (height - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const rising = values.at(-1) >= values[0];
  const direction = rising ? "上升" : "下降";
  return `<svg class="sparkline" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="近期走勢${direction}">` +
    `<title>近期走勢${direction}</title>` +
    `<polyline points="${points}" fill="none" stroke="${rising ? "var(--red)" : "var(--green)"}" stroke-width="1.6" /></svg>`;
}

function rankHeatClass(value) {
  if (!isValue(value)) return "metric-heat rank-heat is-empty";
  const number = Number(value);
  const tier = number >= 85 ? 4 : number >= 67 ? 3 : number >= 34 ? 2 : 1;
  return `metric-heat rank-heat rank-tier-${tier}`;
}

let industryPivotSort = { key: "rank", dir: "desc" };
const industryPivotExpanded = new Set();

function _pivotSortValue(entry, key) {
  const value = entry[key];
  return value == null ? -Infinity : value;
}

const _PIVOT_COLUMNS = [
  { key: "name", label: "產業 / 細產業" },
  { key: "member_count", label: "成分股數", sortable: true },
  { key: "trend", label: "走勢" },
  { key: "rank_20d", label: "20R", sortable: true },
  { key: "rank_60d", label: "60R", sortable: true },
  { key: "rank_120d", label: "120R", sortable: true },
  { key: "rank", label: "Rank", sortable: true },
];

function _pivotRowHtml(entry, { indent = false, expandButton = null, membersKey = null } = {}) {
  const name = expandButton !== null ? entry.industry : entry.sub_industry;
  const nameCell = expandButton !== null
    ? `<button type="button" class="pivot-toggle" aria-expanded="${expandButton}" aria-label="${expandButton === "true" ? "收合" : "展開"}${escapeHtml(name)}細產業"><span class="pivot-caret" aria-hidden="true"></span><span>${escapeHtml(name)}</span></button>`
    : `<span class="pivot-child-name">${escapeHtml(name)}</span>`;
  const membersButton = membersKey !== null
    ? `<button type="button" class="pivot-members-btn" data-members-key="${escapeHtml(membersKey)}" aria-label="查看${escapeHtml(name)}成分股">成分股</button>`
    : "";
  return `<tr class="pivot-row${indent ? " pivot-child" : " pivot-parent"}"${indent ? "" : ` data-industry="${escapeHtml(entry.industry)}"`}>` +
    `<th scope="row" class="pivot-name"><span class="pivot-name-wrap">${nameCell}${membersButton}</span></th>` +
    `<td>${fmt(entry.member_count, 0)}</td>` +
    `<td>${sparklineSvg(entry.trend)}</td>` +
    `<td class="${rankHeatClass(entry.rank_20d)}">${fmt(entry.rank_20d, 0)}</td>` +
    `<td class="${rankHeatClass(entry.rank_60d)}">${fmt(entry.rank_60d, 0)}</td>` +
    `<td class="${rankHeatClass(entry.rank_120d)}">${fmt(entry.rank_120d, 0)}</td>` +
    `<td class="${rankHeatClass(entry.rank)}">${fmt(entry.rank, 0)}</td></tr>`;
}

function renderSubIndustryMomentum(industries) {
  const table = byId("sub-industry-momentum-table");
  renderMomentumSummary("sub-industry", industries);
  if (!industries?.length) { emptyTable(table, _PIVOT_COLUMNS.length, "細產業資料尚未回補"); return; }

  const sorted = [...industries].sort((a, b) => {
    const diff = _pivotSortValue(a, industryPivotSort.key) - _pivotSortValue(b, industryPivotSort.key);
    return industryPivotSort.dir === "asc" ? diff : -diff;
  });

  const pivotSortHeader = (column, rowspan = "") => {
    const active = industryPivotSort.key === column.key;
    const direction = active ? industryPivotSort.dir : "none";
    const tip = column.key === "member_count" ? infoTip(MEMBER_COUNT_TIP) : "";
    const button = `<button type="button" class="table-sort${active ? ` active ${direction}` : ""}" data-sort-key="${column.key}">${escapeHtml(column.label)}</button>`;
    return `<th scope="col"${rowspan ? ` rowspan="${rowspan}"` : ""}${active ? ` aria-sort="${direction === "desc" ? "descending" : "ascending"}"` : ""}>` +
      (tip ? `<span class="th-with-tip">${button}${tip}</span>` : button) + `</th>`;
  };
  const head = `<thead>` +
    `<tr class="momentum-band-row"><th rowspan="2" scope="col">產業／細產業</th>${pivotSortHeader(_PIVOT_COLUMNS[1], 2)}` +
    `<th rowspan="2" scope="col">120 日走勢</th><th colspan="4" scope="colgroup" class="rank-band">強度排名${infoTip(RANK_BAND_TIP)}</th></tr><tr>${_PIVOT_COLUMNS.slice(3).map((column) => {
    return pivotSortHeader(column);
  }).join("")}</tr></thead>`;

  const body = sorted.map((industry, industryIdx) => {
    const expanded = industryPivotExpanded.has(industry.industry);
    const rows = [_pivotRowHtml(industry, { expandButton: expanded ? "true" : "false", membersKey: `${industryIdx}` })];
    if (expanded) {
      industry.sub_industries.forEach((sub, subIdx) => {
        rows.push(_pivotRowHtml(sub, { indent: true, membersKey: `${industryIdx}:${subIdx}` }));
      });
    }
    return rows.join("");
  }).join("");

  const columns = `<colgroup><col class="col-name"><col class="col-members"><col class="col-trend">` +
    `<col class="col-rank"><col class="col-rank"><col class="col-rank"><col class="col-rank"></colgroup>`;
  table.innerHTML = `<caption class="sr-only">台灣前一百大股票細產業動能樞紐表</caption>${columns}${head}<tbody>${body}</tbody>`;

  $$(".table-sort", table).forEach((button) => button.addEventListener("click", () => {
    const key = button.dataset.sortKey;
    industryPivotSort = industryPivotSort.key === key
      ? { key, dir: industryPivotSort.dir === "desc" ? "asc" : "desc" }
      : { key, dir: "desc" };
    renderSubIndustryMomentum(industries);
  }));

  $$(".pivot-parent", table).forEach((row) => row.addEventListener("click", () => {
    const name = row.dataset.industry;
    if (industryPivotExpanded.has(name)) industryPivotExpanded.delete(name);
    else industryPivotExpanded.add(name);
    renderSubIndustryMomentum(industries);
  }));

  $$(".pivot-members-btn", table).forEach((button) => button.addEventListener("click", (event) => {
    // Stop the click from bubbling up to the parent row's toggle handler above —
    // otherwise "查看成分股" would also expand/collapse the sub_industry list.
    event.stopPropagation();
    const [industryIdx, subIdx] = button.dataset.membersKey.split(":");
    const industry = sorted[Number(industryIdx)];
    const entry = subIdx === undefined ? industry : industry.sub_industries[Number(subIdx)];
    openSubIndustryMembersDrawer(entry);
  }));
}

function subIndustryMembersRows(members) {
  if (!members?.length) return `<tr><td colspan="4"><div class="table-empty">尚無成分股資料</div></td></tr>`;
  return members.map((m) => {
    const hasChange = isValue(m.change_pct);
    const cls = hasChange ? (Number(m.change_pct) >= 0 ? "positive" : "negative") : "";
    const sign = hasChange && Number(m.change_pct) >= 0 ? "+" : "";
    return `<tr><td>${escapeHtml(m.code)}</td><td>${escapeHtml(m.name)}</td>` +
      `<td class="${cls}">${hasChange ? `${sign}${pct(m.change_pct, 2, true)}` : "－"}</td>` +
      `<td>${isValue(m.close) ? fmt(m.close, 2) : "－"}</td></tr>`;
  }).join("");
}

function openSubIndustryMembersDrawer(entry) {
  const members = entry?.members || [];
  const name = entry.industry || entry.sub_industry;
  openDrawer(`成分股 · ${name}（共 ${members.length} 檔）`, `
    <table class="data-table"><thead><tr><th>代碼</th><th>名稱</th><th>漲跌幅</th><th>收盤價</th></tr></thead>
    <tbody>${subIndustryMembersRows(members)}</tbody></table>
  `);
}

let subIndustryMomentumLoaded = false;
let subIndustryMomentumData = [];
async function loadSubIndustryMomentum() {
  try {
    setLoading(true);
    subIndustryMomentumData = await fetchJson(`${API}/market/sub-industry-momentum`);
    renderSubIndustryMomentum(subIndustryMomentumData);
  } catch (error) {
    showError(`細產業動能載入失敗：${error.message}`);
  } finally {
    setLoading(false);
  }
}

async function waitForSubIndustryRefresh() {
  await fetchJson(`${API}/market/sub-industry-momentum/refresh`, { method: "POST" });
  // 依序跑產業標籤／前100大名單／股價，最慢的一步要對外部 API 發上百次請求，
  // 給比個股更新更寬鬆的等待時間（最多 10 分鐘）。
  for (let attempt = 0; attempt < 300; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    const job = await fetchJson(`${API}/market/sub-industry-momentum/refresh-status`);
    if (job.status === "running") continue;
    return job;
  }
  throw new Error("回補仍在背景執行，可稍後重新查看");
}

async function refreshSubIndustryMomentum() {
  const button = byId("sub-industry-refresh-button");
  const message = byId("sub-industry-refresh-message");
  button.disabled = true;
  button.textContent = "回補中…";
  message.textContent = "正在依序回補產業標籤、前100大名單與股價，可能需要幾分鐘";
  try {
    const job = await waitForSubIndustryRefresh();
    if (job.status === "failed") {
      const failedSteps = (job.steps || []).filter((step) => step.status === "failed");
      message.textContent = `${job.message}：${failedSteps.map((step) => step.step).join("、")}`;
      showError(`細產業資料回補部分失敗：${failedSteps.map((step) => `${step.step}（${step.error}）`).join("；")}`);
    } else {
      message.textContent = job.message || "回補完成";
    }
    subIndustryMomentumLoaded = true;
    await loadSubIndustryMomentum();
  } catch (error) {
    message.textContent = "回補失敗，畫面保留既有資料";
    showError(`細產業資料回補失敗：${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "重新回補細產業資料";
  }
}
byId("sub-industry-refresh-button").addEventListener("click", refreshSubIndustryMomentum);

const _MOMENTUM_SOURCE_NOTES = {
  sector: "來源：TWSE 官方類股指數（約 30–37 類）；REL 以發行量加權股價指數為基準。",
  "sub-industry": "來源：台灣前 100 大成分股，以 FinMind 產業標籤建立等權重近似指數；成分股少的排名參考價值較低。",
};

const _MOMENTUM_LEGENDS = {
  sector: `<span><i class="legend-swatch rank"></i>Rank 採 20/40/40 加權</span>` +
    `<span><i class="legend-swatch gain"></i>REL 正值領先大盤</span>` +
    `<span><i class="legend-swatch loss"></i>REL 負值落後大盤</span>`,
  "sub-industry": `<span><i class="legend-swatch rank"></i>Rank 採 20/40/40 加權</span>` +
    `<span>點選產業列展開細項</span>`,
};

$$('[data-momentum-mode]').forEach((button) => button.addEventListener("click", () => {
  const mode = button.dataset.momentumMode;
  $$('[data-momentum-mode]').forEach((item) => item.classList.toggle("active", item === button));
  byId("sector-momentum-view").classList.toggle("hidden", mode !== "sector");
  byId("sub-industry-momentum-view").classList.toggle("hidden", mode !== "sub-industry");
  byId("momentum-source-note").textContent = _MOMENTUM_SOURCE_NOTES[mode];
  byId("momentum-legend").innerHTML = _MOMENTUM_LEGENDS[mode];
  renderMomentumSummary(mode, mode === "sector" ? sectorMomentumData : subIndustryMomentumData);
  if (mode === "sub-industry" && !subIndustryMomentumLoaded) {
    subIndustryMomentumLoaded = true;
    loadSubIndustryMomentum();
  }
}));

$$('#stock-rankings-tabs [data-rankings-tab]').forEach((button) => button.addEventListener("click", () => {
  state.stockRankingsTab = button.dataset.rankingsTab;
  $$('#stock-rankings-tabs [data-rankings-tab]').forEach((item) => item.classList.toggle("active", item === button));
  renderStockRankings(state.stockRankings);
}));
byId("stock-rankings-more").addEventListener("click", openStockRankingsDrawer);

$$('#industry-rankings-tabs [data-industry-tab]').forEach((button) => button.addEventListener("click", () => {
  state.industryRankingsTab = button.dataset.industryTab;
  $$('#industry-rankings-tabs [data-industry-tab]').forEach((item) => item.classList.toggle("active", item === button));
  renderIndustryRankings(state.industryRankings);
}));
byId("industry-rankings-more").addEventListener("click", openIndustryRankingsDrawer);

$$('#index-comparison-scale-tabs [data-comparison-scale]').forEach((button) => button.addEventListener("click", () => {
  state.indexComparisonScale = button.dataset.comparisonScale;
  $$('#index-comparison-scale-tabs [data-comparison-scale]').forEach((item) => item.classList.toggle("active", item === button));
  renderIndexComparison(state.marketOverview);
}));
$$('#index-comparison-range-tabs [data-comparison-range]').forEach((button) => button.addEventListener("click", () => {
  state.indexComparisonRange = button.dataset.comparisonRange;
  $$('#index-comparison-range-tabs [data-comparison-range]').forEach((item) => item.classList.toggle("active", item === button));
  renderIndexComparison(state.marketOverview);
}));

byId("index-contribution-more").addEventListener("click", openIndexContributionDrawer);
byId("market-cap-share-link").addEventListener("click", openMarketCapShareDrawer);
byId("index-detail-trigger").addEventListener("click", openIndexDetailDrawer);

function renderRanking(radar = state.radar) {
  const category = `${state.rankingTopic}_${state.rankingMarket}`;
  const rows = radar?.rankings?.[category] || [];
  const topics = {
    turnover: ["成交熱度", "用成交值找出資金最集中、最值得先研究的標的。（成交值＝成交量 × 成交均價）"],
    margin_ratio: ["券資壓力", "觀察融券相對融資的壓力，找出軋空或籌碼擁擠候選。（券資比＝融券餘額 ÷ 融資餘額）"],
    turnover_rate: ["交易活躍", "用週轉率辨識籌碼快速換手、價格正在形成共識的標的。（週轉率＝當日成交量 ÷ 流通在外股數）"],
  };
  byId("ranking-title").textContent = topics[state.rankingTopic][0];
  byId("ranking-description").textContent = topics[state.rankingTopic][1];
  byId("ranking-scope").textContent = state.rankingMarket === "listed" ? "上市股票" : "上櫃股票";
  byId("ranking-date").textContent = `資料日期 ${rows[0]?.date || "待補"}`;
  $$('[data-ranking-topic]').forEach((button) => button.classList.toggle("active", button.dataset.rankingTopic === state.rankingTopic));
  $$('[data-ranking-market]').forEach((button) => button.classList.toggle("active", button.dataset.rankingMarket === state.rankingMarket));
  const valueLabel = state.rankingTopic === "turnover" ? "成交值" : state.rankingTopic === "margin_ratio" ? "券資比" : "週轉率";
  const valueFormat = state.rankingTopic === "turnover"
    ? (value) => isValue(value) ? `${fmt(Number(value) / 1e8, 2)} 億` : "-"
    : (value) => pct(value, 2, true);
  tableFromRows(byId("ranking-table"), rows.slice(0, 50), [
    { key: "rank", label: "排名" }, { key: "code", label: "代碼" },
    {
      key: "name",
      label: "公司／標籤",
      format: (value, row) => {
        const market = row.market || (state.rankingMarket === "listed" ? "上市" : "上櫃");
        const type = String(row.code).startsWith("0") ? "ETF" : "個股";
        const industry = row.industry ? `<span>${escapeHtml(row.industry)}</span>` : "";
        return `<div class="stock-labels"><b>${escapeHtml(value)}</b><small>${escapeHtml(market)}</small><small>${type}</small>${industry}</div>`;
      },
    },
    { key: "value", label: valueLabel, format: valueFormat }, { key: "date", label: "資料日" },
  ], `${valueLabel}的${state.rankingMarket === "listed" ? "上市" : "上櫃"}排行資料源尚未接妥`);
  $$("#ranking-table tbody tr").forEach((row, index) => {
    const code = rows[index]?.code;
    if (!code) return;
    row.classList.add("clickable");
    row.addEventListener("click", () => { byId("code-input").value = code; loadStock(code); });
  });
}

function renderDashboard(dashboard, radar, valuationBenchmark = {}) {
  renderStockHeader(dashboard.stock, dashboard.freshness, valuationBenchmark);
  byId("market-current-stock").textContent = `${dashboard.stock.code} ${dashboard.stock.name || ""}${dashboard.stock.industry ? `｜${dashboard.stock.industry}` : ""}`;
  renderDecision(dashboard.decision);
  renderFundamentals(dashboard.fundamentals);
  renderQuality(dashboard.financial_quality, dashboard.governance);
  renderNineGrid(dashboard.nine_grid);
  renderMarket(dashboard.chips_market, radar);
}

function optionsQuery() {
  return new URLSearchParams(state.options).toString();
}

async function loadStock(code, { modelOnly = false, bootstrapAttempt = false } = {}) {
  const normalized = String(code).trim().toUpperCase();
  if (!normalized) return;
  closeDataHealth(false);
  setLoading(true);
  try {
    const dashboard = await fetchJson(`${API}/stocks/${encodeURIComponent(normalized)}/dashboard-v2?${optionsQuery()}`);
    if (!modelOnly || !state.dashboard) {
      state.radar = state.radar || await fetchJson(`${API}/market/radar`).catch(() => ({ futures: [], rankings: {} }));
      state.valuationBenchmark = await fetchJson(`${API}/stocks/${encodeURIComponent(normalized)}/valuation-benchmark`).catch(() => ({}));
      state.dashboard = dashboard;
      state.code = normalized;
      renderDashboard(dashboard, state.radar, state.valuationBenchmark);
      byId("empty-state").classList.add("hidden");
      byId("market-overview-panel").classList.add("hidden");
      byId("market-overview-tab").classList.remove("active");
      byId("market-overview-tab").setAttribute("aria-pressed", "false");
      state.marketOverviewActive = false;
      byId("index-comparison-panel").classList.add("hidden");
      byId("index-comparison-tab").classList.remove("active");
      byId("index-comparison-tab").setAttribute("aria-pressed", "false");
      state.indexComparisonActive = false;
      byId("stock-header").classList.remove("hidden");
      byId("freshness-rail").classList.remove("hidden");
      byId("workspace-nav").classList.remove("hidden");
      byId("workspace").classList.remove("hidden");
      byId("refresh-button").classList.remove("hidden");
      history.replaceState(null, "", `?code=${encodeURIComponent(normalized)}&view=${state.view}`);
    } else {
      state.dashboard.decision = dashboard.decision;
      renderDecision(dashboard.decision);
    }
  } catch (error) {
    if (error.status === 404 && !modelOnly && !bootstrapAttempt) {
      byId("refresh-message").textContent = `首次建立 ${normalized} 的研究資料…`;
      try {
        await waitForRefresh(normalized);
        return await loadStock(normalized, { bootstrapAttempt: true });
      } catch (refreshError) {
        showError(refreshError.message);
        return;
      }
    }
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
  requestAnimationFrame(() => { if (state.dashboard) renderDashboard(state.dashboard, state.radar || { futures: [], rankings: {} }, state.valuationBenchmark || {}); });
  window.scrollTo({ top: byId("workspace-nav").offsetTop - 60, behavior: "smooth" });
}

const HEALTH_LABELS = {
  healthy: "正常",
  degraded: "使用備援",
  incomplete: "歷史深度不足",
  stale: "資料過期",
  unavailable: "不可用",
  attention: "需注意",
  not_selected: "尚未選股",
  not_observed: "本次尚未觀察",
  blocked: "來源受限",
  failed: "最近失敗",
  running: "執行中",
  success: "成功",
  partial: "部分完成",
  uncalled: "本次尚未呼叫",
};
const HEALTH_SEVERITY = { unavailable: 6, stale: 5, failed: 5, blocked: 5, incomplete: 4, degraded: 3, healthy: 1, not_selected: 0, not_observed: 0 };

function healthStatus(status, label = HEALTH_LABELS[status] || status) {
  return `<span class="health-status status-${escapeHtml(status)}"><i></i>${escapeHtml(label)}</span>`;
}

function healthTime(value, includeTime = false) {
  if (!value) return "-";
  if (/^\d{4}(?:Q\d|$|[-/]\d{1,2}$)/.test(value) && !value.includes("T")) return value;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit",
    ...(includeTime ? { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false } : {}),
  }).format(parsed);
}

function renderHealthSummary() {
  const payload = state.health;
  if (!payload) return;
  const attention = payload.summary.attention;
  byId("health-summary").innerHTML = `
    <article class="health-summary-card primary"><span>整體判定</span>${healthStatus(payload.overall_status, payload.overall_status_label)}<strong>${attention ? `${attention} 項需要先確認` : "可直接進行研究"}</strong></article>
    <article class="health-summary-card"><span>符合規則</span><strong>${payload.summary.healthy}<small> / ${payload.summary.actionable} 項</small></strong><p>時效、深度與來源皆通過</p></article>
    <article class="health-summary-card"><span>評估範圍</span><strong>${payload.code ? escapeHtml(payload.code) : "全市場"}</strong><p>${payload.code ? "市場資料＋目前個股" : "個股資料等待選股"}</p></article>
    <article class="health-summary-card"><span>運作方式</span><strong>按需</strong><p>不常駐、不定時輪詢</p></article>`;
  byId("health-context").textContent = payload.code ? `目前股票 ${payload.code}` : "全市場";
  byId("health-evaluated-at").textContent = `評估時間 ${healthTime(payload.evaluated_at, true)}`;
  const badge = byId("health-badge");
  badge.textContent = attention ? `${attention} 項` : "正常";
  badge.dataset.status = payload.overall_status;

  const importanceWeight = { critical: 3, supporting: 2, optional: 1 };
  const issues = payload.datasets
    .filter((row) => !["healthy", "not_selected"].includes(row.status))
    .sort((a, b) => (importanceWeight[b.importance] || 0) - (importanceWeight[a.importance] || 0) || (HEALTH_SEVERITY[b.status] || 0) - (HEALTH_SEVERITY[a.status] || 0));
  byId("health-priority").innerHTML = issues.length
    ? `<div class="priority-heading"><b>優先確認</b><span>依影響程度排序，先看前 ${Math.min(issues.length, 5)} 項</span></div><div class="priority-list">${issues.slice(0, 5).map((row) => `<article><div>${healthStatus(row.status)}<b>${escapeHtml(row.label)}</b></div><p>${escapeHtml(row.reason)}</p></article>`).join("")}</div>`
    : `<div class="health-all-clear">${healthStatus("healthy")}<div><b>目前沒有阻礙判讀的資料問題</b><span>仍可在下方展開查看每一項的判定依據。</span></div></div>`;
}

function healthDatasetVisible(row) {
  const scope = byId("health-scope-filter").value;
  const status = byId("health-status-filter").value;
  if (scope !== "all" && row.scope !== scope) return false;
  if (status === "attention") return !["healthy", "not_selected"].includes(row.status);
  return status === "all" || row.status === status;
}

function renderHealthDatasets() {
  if (!state.health) return;
  const rows = state.health.datasets
    .filter(healthDatasetVisible)
    .sort((a, b) => (HEALTH_SEVERITY[b.status] || 0) - (HEALTH_SEVERITY[a.status] || 0) || a.label.localeCompare(b.label, "zh-Hant"));
  byId("health-datasets-body").innerHTML = rows.length ? rows.map((row) => {
    const completeness = row.row_count === null
      ? "-"
      : row.allow_empty && row.row_count === 0
        ? "允許為空"
        : `${Math.round((row.completeness_ratio || 0) * 100)}% · ${row.row_count}/${row.minimum_rows}`;
    return `<tr>
      <td><b>${escapeHtml(row.label)}</b><small>${row.scope === "stock" ? `個股 ${escapeHtml(row.scope_key || "")}` : "全市場"} · ${escapeHtml(row.cadence)} · ${row.importance === "critical" ? "決策核心" : row.importance === "optional" ? "選配" : "輔助"}</small></td>
      <td>${healthStatus(row.status, row.status_label)}</td>
      <td><b class="mono">${escapeHtml(healthTime(row.data_as_of))}</b><small>${row.last_success_at ? `成功於 ${escapeHtml(healthTime(row.last_success_at, true))}` : "尚無成功紀錄"}</small></td>
      <td><b class="mono">${escapeHtml(completeness)}</b><small>${escapeHtml(row.grain)}</small></td>
      <td><b>${escapeHtml(row.source_label || "-")}</b><small>${escapeHtml(row.source_tier || row.primary_source)}</small></td>
      <td class="health-reason">${escapeHtml(row.reason)}</td>
    </tr>`;
  }).join("") : `<tr><td colspan="6" class="health-empty">目前篩選條件沒有資料</td></tr>`;
}

function renderHealthSources() {
  if (!state.health) return;
  const rows = [...state.health.sources].sort((a, b) => (HEALTH_SEVERITY[b.status] || 0) - (HEALTH_SEVERITY[a.status] || 0) || b.canonical_datasets - a.canonical_datasets);
  byId("health-sources-body").innerHTML = rows.map((row) => `<tr>
    <td><b>${escapeHtml(row.label)}</b><small class="mono">${escapeHtml(row.id)}</small></td>
    <td><span class="source-tier tier-${escapeHtml(row.tier)}">${escapeHtml(row.tier)}</span></td>
    <td>${healthStatus(row.status, row.status_label)}</td>
    <td><b class="mono">${row.success_rate_24h === null ? "-" : `${Math.round(row.success_rate_24h * 100)}%`}</b><small>${row.runs_24h} 次觀察</small></td>
    <td><b>${row.canonical_datasets} 個資料集</b><small>${row.dependent_datasets} 個相依</small></td>
    <td><b class="mono">${escapeHtml(healthTime(row.latest_run?.started_at, true))}</b><small>${escapeHtml(row.latest_run?.error || "-")}</small></td>
  </tr>`).join("");
}

function endpointRegex(path) {
  const pattern = path.split("/").map((part) => part.startsWith("{") && part.endsWith("}")
    ? "[^/]+"
    : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("/");
  return new RegExp(`^${pattern}$`);
}

function endpointMetric(path, method) {
  const matcher = endpointRegex(path);
  const matching = Object.values(state.apiMetrics).filter((metric) => metric.method === method && matcher.test(metric.path));
  if (!matching.length) return null;
  return matching.reduce((total, metric) => ({
    count: total.count + metric.count,
    successCount: total.successCount + metric.successCount,
    errorCount: total.errorCount + metric.errorCount,
    totalMs: total.totalMs + metric.totalMs,
    lastStatus: !total.lastAt || metric.lastAt > total.lastAt ? metric.lastStatus : total.lastStatus,
    lastAt: !total.lastAt || metric.lastAt > total.lastAt ? metric.lastAt : total.lastAt,
  }), { count: 0, successCount: 0, errorCount: 0, totalMs: 0, lastStatus: null, lastAt: null });
}

function renderHealthApi() {
  const rows = state.healthEndpoints.flatMap((endpoint) => endpoint.methods.map((method) => {
    const metric = endpointMetric(endpoint.path, method);
    const average = metric ? metric.totalMs / metric.count : null;
    const status = !metric ? "uncalled" : metric.errorCount ? (metric.successCount ? "degraded" : "failed") : average > 1500 ? "degraded" : "healthy";
    return { ...endpoint, method, metric, average, status };
  })).sort((a, b) => (a.metric ? 0 : 1) - (b.metric ? 0 : 1) || (HEALTH_SEVERITY[b.status] || 0) - (HEALTH_SEVERITY[a.status] || 0) || a.path.localeCompare(b.path));
  byId("health-api-body").innerHTML = rows.map((row) => `<tr>
    <td><span class="http-method method-${row.method.toLowerCase()}">${row.method}</span><b class="mono api-path">${escapeHtml(row.path)}</b></td>
    <td>${healthStatus(row.status)}</td>
    <td><b class="mono">${row.metric?.count ?? 0}</b></td>
    <td><b class="mono">${row.metric ? `${Math.round(row.metric.successCount / row.metric.count * 100)}%` : "-"}</b></td>
    <td><b class="mono">${row.average === null ? "-" : `${Math.round(row.average)} ms`}</b></td>
    <td><b class="mono">${row.metric?.lastStatus || "-"}</b><small>${escapeHtml(healthTime(row.metric?.lastAt, true))}</small></td>
  </tr>`).join("");
}

function renderHealthRuns() {
  if (!state.health) return;
  const labels = Object.fromEntries(state.health.datasets.map((row) => [row.id, row.label]));
  const sources = Object.fromEntries(state.health.sources.map((row) => [row.id, row.label]));
  byId("health-runs-body").innerHTML = state.health.recent_runs.length ? state.health.recent_runs.map((row) => `<tr>
    <td><b class="mono">${escapeHtml(healthTime(row.started_at, true))}</b><small>${escapeHtml(row.scope_key)}</small></td>
    <td><b>${escapeHtml(labels[row.dataset_id] || row.dataset_id)}</b><small class="mono">${escapeHtml(row.dataset_id)}</small></td>
    <td><b>${escapeHtml(sources[row.source] || row.source)}</b></td>
    <td>${healthStatus(row.status)}</td>
    <td><b class="mono">${row.duration_ms === null ? "-" : `${Math.round(row.duration_ms)} ms`}</b><small>${row.http_status ? `HTTP ${row.http_status}` : ""}</small></td>
    <td class="health-reason"><b class="mono">${escapeHtml(row.data_as_of || "-")}</b><small>${escapeHtml(row.error || `${row.row_count ?? "-"} 筆`)}</small></td>
  </tr>`).join("") : `<tr><td colspan="6" class="health-empty">這個範圍尚無外部資料更新紀錄</td></tr>`;
}

function setHealthTab(tab) {
  state.healthTab = tab;
  $$('[data-health-tab]').forEach((button) => button.classList.toggle("active", button.dataset.healthTab === tab));
  $$('[data-health-panel]').forEach((panel) => panel.classList.toggle("hidden", panel.dataset.healthPanel !== tab));
  $('[data-health-filters]').classList.toggle("hidden", tab !== "datasets");
  if (tab === "api") renderHealthApi();
}

async function loadDataHealth() {
  setLoading(true);
  try {
    const query = state.code ? `?code=${encodeURIComponent(state.code)}` : "";
    const [health, endpoints] = await Promise.all([
      fetchJson(`${API}/data-health${query}`),
      fetchJson(`${API}/data-health/endpoints`),
    ]);
    state.health = health;
    state.healthEndpoints = endpoints;
    renderHealthSummary();
    renderHealthDatasets();
    renderHealthSources();
    renderHealthApi();
    renderHealthRuns();
  } catch (error) {
    showError(`資料健康評估失敗：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function openDataHealth() {
  document.body.classList.add("health-open");
  byId("data-health-panel").classList.remove("hidden");
  byId("method-drawer").classList.add("hidden");
  const url = new URL(window.location.href);
  url.searchParams.set("panel", "data-health");
  if (state.code) url.searchParams.set("code", state.code);
  history.replaceState(null, "", url);
  window.scrollTo({ top: 0, behavior: "instant" });
  loadDataHealth();
}

function closeDataHealth(updateUrl = true) {
  document.body.classList.remove("health-open");
  byId("data-health-panel").classList.add("hidden");
  if (updateUrl) {
    const url = new URL(window.location.href);
    url.searchParams.delete("panel");
    history.replaceState(null, "", url);
  }
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
byId("landing-focus-button").addEventListener("click", () => {
  byId("code-input").focus();
});
byId("market-overview-tab").addEventListener("click", () => {
  if (state.marketOverviewActive) hideMarketOverviewTab(); else showMarketOverviewTab();
});
byId("index-comparison-tab").addEventListener("click", () => {
  if (state.indexComparisonActive) hideIndexComparisonTab(); else showIndexComparisonTab();
});
byId("market-snapshot-link").addEventListener("click", (event) => {
  event.preventDefault();
  showMarketOverviewTab();
});
document.addEventListener("click", (event) => { if (!byId("search-form").contains(event.target)) byId("search-results").classList.remove("show"); });
$$('.nav-tab').forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$$('[data-option]').forEach((select) => select.addEventListener("change", () => {
  state.options[select.dataset.option] = select.value;
  if (state.code) loadStock(state.code, { modelOnly: true });
}));
$$('[data-fund-mode]').forEach((button) => button.addEventListener("click", () => {
  const tableMode = button.dataset.fundMode === "table";
  $$('[data-fund-mode]').forEach((item) => item.classList.toggle("active", item === button));
  byId("fundamentals-chart-view").classList.toggle("hidden", tableMode);
  byId("fundamentals-table-view").classList.toggle("hidden", !tableMode);
  if (!tableMode && state.dashboard) requestAnimationFrame(() => renderFundamentals(state.dashboard.fundamentals));
}));
$$('[data-ranking-topic]').forEach((button) => button.addEventListener("click", () => {
  state.rankingTopic = button.dataset.rankingTopic;
  renderRanking();
}));
$$('[data-ranking-market]').forEach((button) => button.addEventListener("click", () => {
  state.rankingMarket = button.dataset.rankingMarket;
  renderRanking();
}));

const drawer = byId("method-drawer");
byId("method-toggle").addEventListener("click", () => drawer.classList.toggle("hidden"));
byId("method-close").addEventListener("click", () => drawer.classList.add("hidden"));
byId("health-toggle").addEventListener("click", openDataHealth);
byId("health-close").addEventListener("click", () => closeDataHealth());
byId("health-reload").addEventListener("click", loadDataHealth);
$$('[data-health-tab]').forEach((button) => button.addEventListener("click", () => setHealthTab(button.dataset.healthTab)));
byId("health-scope-filter").addEventListener("change", renderHealthDatasets);
byId("health-status-filter").addEventListener("change", renderHealthDatasets);

async function waitForRefresh(code) {
  await fetchJson(`${API}/stocks/${encodeURIComponent(code)}/refresh`, { method: "POST" });
  for (let attempt = 0; attempt < 120; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    const job = await fetchJson(`${API}/stocks/${encodeURIComponent(code)}/refresh-status`);
    if (job.status === "running") continue;
    byId("refresh-message").textContent = job.message || "更新完成";
    if (job.status === "completed") return job;
    throw new Error(job.message || "資料更新失敗");
  }
  throw new Error("更新仍在背景執行，可稍後重新查詢");
}

async function refreshCurrentStock() {
  if (!state.code) return;
  const button = byId("refresh-button");
  button.disabled = true;
  button.textContent = "更新中…";
  byId("refresh-message").textContent = "正在背景更新；目前畫面仍可繼續研究";
  try {
    await waitForRefresh(state.code);
    state.radar = null;
    await loadStock(state.code);
  } catch (error) {
    showError(`更新失敗：${error.message}`);
    byId("refresh-message").textContent = "更新失敗，畫面保留既有資料";
  } finally {
    button.disabled = false;
    button.textContent = "更新資料";
  }
}
byId("refresh-button").addEventListener("click", refreshCurrentStock);

function tickClock() {
  byId("clock").textContent = new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date());
}
tickClock(); setInterval(tickClock, 1000);

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state.dashboard) renderDashboard(state.dashboard, state.radar || { futures: [], rankings: {} }, state.valuationBenchmark || {});
    if (state.marketOverview && state.marketOverviewActive) renderMarketOverview(state.marketOverview);
    if (state.marketOverview && state.indexComparisonActive) renderIndexComparison(state.marketOverview);
  }, 150);
});

const params = new URLSearchParams(window.location.search);
const initialView = params.get("view");
if (["overview", "fundamentals", "quality", "nine-grid", "market"].includes(initialView)) switchView(initialView);
const initialCode = params.get("code");
const initialPanel = params.get("panel");
if (initialCode) {
  byId("code-input").value = initialCode;
  if (initialPanel === "data-health") state.code = initialCode;
  else loadStock(initialCode);
}
if (initialPanel === "data-health") openDataHealth();
else if (initialPanel === "market-overview") showMarketOverviewTab();
else if (initialPanel === "index-comparison") showIndexComparisonTab();
loadMarketOverview();
