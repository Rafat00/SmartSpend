// Analytics page charts. Data is embedded by Flask as JSON in #analyticsData.
(function () {
  const data = JSON.parse(document.getElementById("analyticsData").textContent);
  const taka = (v) => "৳" + Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });
  const moneyAxis = { beginAtZero: true, ticks: { callback: (v) => taka(v) } };
  const tip = { callbacks: { label: (ctx) => " " + ctx.dataset.label + ": " + taka(ctx.parsed.y) } };

  new Chart(document.getElementById("chartWeekly"), {
    type: "bar",
    data: { labels: data.weekly.labels, datasets: [{ label: "Week starting", data: data.weekly.values, backgroundColor: "#4f46e5" }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: tip }, scales: { y: moneyAxis } },
  });

  new Chart(document.getElementById("chartComparison"), {
    type: "bar",
    data: {
      labels: data.comparison.labels,
      datasets: [
        { label: "Last month", data: data.comparison.previous, backgroundColor: "#cbd5e1" },
        { label: "This month", data: data.comparison.current, backgroundColor: "#4f46e5" },
      ],
    },
    options: { maintainAspectRatio: false, plugins: { tooltip: tip }, scales: { y: moneyAxis } },
  });
})();
