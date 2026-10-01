/* FinSight AI — Chart.js rendering. Follows the project's dataviz method:
   - fixed, non-cycled categorical color assignment (a category keeps its color
     regardless of sort order or which categories are present that month)
   - sequential single-hue for magnitude-only charts (top merchants)
   - one y-axis only; a forecast is drawn as a dashed extension of the same series,
     never a second scale
   - thin marks, hairline gridlines, legend for 2+ series, no data-label flooding */

const Charts = (() => {
  const instances = {};

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // Fixed category -> categorical slot. Order never changes regardless of amount/
  // sort, so a category's color stays stable across reloads and filters.
  const CATEGORY_SLOT = {
    Rent: "--series-1",
    Food: "--series-2",
    Transport: "--series-3",
    Bills: "--series-4",
    Entertainment: "--series-5",
    Shopping: "--series-6",
    Healthcare: "--series-7",
    Education: "--series-8",
  };

  function colorForCategory(name) {
    const slot = CATEGORY_SLOT[name];
    return cssVar(slot || "--series-other");
  }

  function destroy(id) {
    if (instances[id]) {
      instances[id].destroy();
      delete instances[id];
    }
  }

  function baseGridOptions() {
    const grid = cssVar("--gridline");
    const muted = cssVar("--text-muted");
    return {
      grid: { color: grid, drawTicks: false },
      ticks: { color: muted, font: { size: 11 } },
      border: { color: cssVar("--baseline") },
    };
  }

  function money(v) {
    if (v === null || v === undefined) return "—";
    return "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  }

  function renderTrendChart(canvasId, legendElId, monthly, forecast) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId).getContext("2d");

    const historyLabels = monthly.map((m) => m.period);
    const forecastPeriods = (forecast && forecast.forecast) || [];
    const labels = historyLabels.concat(forecastPeriods.map((f) => f.period));

    const income = monthly.map((m) => Number(m.income)).concat(forecastPeriods.map(() => null));

    const expensesActual = monthly.map((m) => Number(m.expenses)).concat(forecastPeriods.map(() => null));

    const expensesForecast = historyLabels.map(() => null);
    if (forecastPeriods.length && monthly.length) {
      expensesForecast[expensesForecast.length - 1] = Number(monthly[monthly.length - 1].expenses);
    }
    forecastPeriods.forEach((f) => expensesForecast.push(Number(f.predicted_expenses)));

    const seriesIncome = cssVar("--series-1");
    const seriesExpense = cssVar("--series-2");
    const grid = baseGridOptions();

    instances[canvasId] = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Income",
            data: income,
            borderColor: seriesIncome,
            backgroundColor: seriesIncome,
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: seriesIncome,
            pointBorderColor: cssVar("--surface-1"),
            pointBorderWidth: 2,
            tension: 0.25,
            spanGaps: false,
          },
          {
            label: "Expenses",
            data: expensesActual,
            borderColor: seriesExpense,
            backgroundColor: seriesExpense,
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: seriesExpense,
            pointBorderColor: cssVar("--surface-1"),
            pointBorderWidth: 2,
            tension: 0.25,
          },
          {
            label: "Expenses (forecast)",
            data: expensesForecast,
            borderColor: seriesExpense,
            backgroundColor: "transparent",
            borderWidth: 2,
            borderDash: [5, 4],
            pointRadius: (c) => (c.dataIndex >= historyLabels.length ? 3 : 0),
            pointBackgroundColor: seriesExpense,
            pointBorderColor: cssVar("--surface-1"),
            pointBorderWidth: 2,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar("--surface-2"),
            titleColor: cssVar("--text-primary"),
            bodyColor: cssVar("--text-secondary"),
            borderColor: cssVar("--border"),
            borderWidth: 1,
            padding: 10,
            callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y)}` },
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: grid.ticks, border: grid.border },
          y: { ...grid, ticks: { ...grid.ticks, callback: (v) => money(v) } },
        },
      },
    });

    const legendEl = document.getElementById(legendElId);
    if (legendEl) {
      legendEl.innerHTML = `
        <span class="legend-item"><span class="legend-swatch" style="background:${seriesIncome}"></span>Income</span>
        <span class="legend-item"><span class="legend-swatch" style="background:${seriesExpense}"></span>Expenses</span>
        <span class="legend-item"><span class="legend-swatch" style="background:${seriesExpense};opacity:.5"></span>Forecast</span>
      `;
    }
  }

  function renderCategoryChart(canvasId, categories) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId).getContext("2d");
    const sorted = [...categories].sort((a, b) => Number(b.total_amount) - Number(a.total_amount));
    const grid = baseGridOptions();

    instances[canvasId] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: sorted.map((c) => c.category),
        datasets: [
          {
            data: sorted.map((c) => Number(c.total_amount)),
            backgroundColor: sorted.map((c) => colorForCategory(c.category)),
            borderRadius: 4,
            maxBarThickness: 22,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar("--surface-2"),
            titleColor: cssVar("--text-primary"),
            bodyColor: cssVar("--text-secondary"),
            borderColor: cssVar("--border"),
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: (c) => {
                const row = sorted[c.dataIndex];
                return `${money(row.total_amount)} · ${(row.percent_of_expenses * 100).toFixed(1)}% · ${row.transaction_count} txns`;
              },
            },
          },
        },
        scales: {
          x: { ...grid, ticks: { ...grid.ticks, callback: (v) => money(v) } },
          y: { grid: { display: false }, ticks: grid.ticks, border: grid.border },
        },
      },
    });
  }

  function renderMerchantsChart(canvasId, merchants) {
    destroy(canvasId);
    const ctx = document.getElementById(canvasId).getContext("2d");
    const top = [...merchants].sort((a, b) => Number(b.total_amount) - Number(a.total_amount)).slice(0, 8);
    const grid = baseGridOptions();
    const hue = cssVar("--seq-500");

    instances[canvasId] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: top.map((m) => m.merchant),
        datasets: [
          {
            data: top.map((m) => Number(m.total_amount)),
            backgroundColor: hue,
            borderRadius: 4,
            maxBarThickness: 18,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar("--surface-2"),
            titleColor: cssVar("--text-primary"),
            bodyColor: cssVar("--text-secondary"),
            borderColor: cssVar("--border"),
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: (c) => `${money(top[c.dataIndex].total_amount)} · ${top[c.dataIndex].transaction_count} txns`,
            },
          },
        },
        scales: {
          x: { ...grid, ticks: { ...grid.ticks, callback: (v) => money(v) } },
          y: { grid: { display: false }, ticks: grid.ticks, border: grid.border },
        },
      },
    });
  }

  function destroyAll() {
    Object.keys(instances).forEach(destroy);
  }

  return { renderTrendChart, renderCategoryChart, renderMerchantsChart, colorForCategory, money, destroyAll };
})();
