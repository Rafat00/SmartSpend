// Predictions chart: solid bars = actual months, hatched/orange bars = ML estimates.
(function () {
  const data = JSON.parse(document.getElementById("predictionData").textContent);
  const taka = (v) => "৳" + Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 });

  new Chart(document.getElementById("chartPrediction"), {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [
        { label: "Actual", data: data.actual, backgroundColor: "#4f46e5" },
        { label: "Estimate", data: data.estimate, backgroundColor: "rgba(249,115,22,.65)", borderColor: "#f97316", borderWidth: 2, borderDash: [4, 4] },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { tooltip: { callbacks: { label: (ctx) => " " + ctx.dataset.label + ": " + taka(ctx.parsed.y) } } },
      scales: { y: { beginAtZero: true, ticks: { callback: (v) => taka(v) } } },
    },
  });
})();
