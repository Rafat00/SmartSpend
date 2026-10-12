// Dashboard charts. Data comes from /api/charts (real database data for the logged-in user).
(function () {
  const PALETTE = ["#4f46e5", "#0ea5e9", "#f97316", "#10b981", "#ec4899", "#eab308", "#8b5cf6", "#ef4444", "#14b8a6", "#64748b"];
  const taka = (v) => "৳" + Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });

  function showEmpty(canvasId) {
    const box = document.getElementById(canvasId).parentElement;
    box.innerHTML = '<div class="chart-empty">No data yet</div>';
  }
  const hasData = (values) => values.some((v) => v > 0);

  const moneyAxis = { beginAtZero: true, ticks: { callback: (v) => taka(v) } };
  const moneyTooltip = { callbacks: { label: (ctx) => " " + taka(ctx.parsed.y ?? ctx.parsed) } };

  fetch(window.CHART_URL, { headers: { Accept: "application/json" } })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((d) => {
      // Chart 1: monthly trend
      if (hasData(d.monthly.values)) {
        new Chart(document.getElementById("chartMonthly"), {
          type: "line",
          data: { labels: d.monthly.labels, datasets: [{ label: "Spending", data: d.monthly.values, borderColor: "#4f46e5", backgroundColor: "rgba(79,70,229,.12)", fill: true, tension: 0.3 }] },
          options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: moneyTooltip }, scales: { y: moneyAxis } },
        });
      } else showEmpty("chartMonthly");

      // Chart 2: by category
      document.getElementById("categoryScope").textContent = "· " + d.categories.scope;
      if (hasData(d.categories.values)) {
        new Chart(document.getElementById("chartCategory"), {
          type: "doughnut",
          data: { labels: d.categories.labels, datasets: [{ data: d.categories.values, backgroundColor: PALETTE }] },
          options: { maintainAspectRatio: false, plugins: { legend: { position: "right" }, tooltip: { callbacks: { label: (ctx) => " " + ctx.label + ": " + taka(ctx.parsed) } } } },
        });
      } else showEmpty("chartCategory");

      // Chart 3: top stores
      if (hasData(d.stores.values)) {
        new Chart(document.getElementById("chartStores"), {
          type: "bar",
          data: { labels: d.stores.labels, datasets: [{ label: "Spent", data: d.stores.values, backgroundColor: "#0ea5e9" }] },
          options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => " " + taka(ctx.parsed.x) } } }, scales: { x: moneyAxis } },
        });
      } else showEmpty("chartStores");

      // Chart 4: daily spending
      if (hasData(d.daily.values)) {
        new Chart(document.getElementById("chartDaily"), {
          type: "bar",
          data: { labels: d.daily.labels, datasets: [{ label: "Spent", data: d.daily.values, backgroundColor: "#10b981" }] },
          options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: moneyTooltip }, scales: { y: moneyAxis, x: { ticks: { maxTicksLimit: 10 } } } },
        });
      } else showEmpty("chartDaily");
    })
    .catch(() => {
      ["chartMonthly", "chartCategory", "chartStores", "chartDaily"].forEach((id) => {
        document.getElementById(id).parentElement.innerHTML = '<div class="chart-empty">Could not load chart data.</div>';
      });
    });
})();
