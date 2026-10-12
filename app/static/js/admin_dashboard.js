// Admin dashboard charts. Data is embedded by the server (counts only, from the database).
(function () {
  const el = document.getElementById('chart-data');
  if (!el || typeof Chart === 'undefined') return;
  const d = JSON.parse(el.textContent);
  const palette = ['#4f46e5', '#0ea5e9', '#f59e0b', '#10b981', '#ec4899', '#8b5cf6', '#ef4444', '#64748b'];
  const base = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } };
  const intAxis = { beginAtZero: true, ticks: { precision: 0 } };

  new Chart(document.getElementById('expenseTrend'), {
    type: 'line',
    data: { labels: d.months, datasets: [{ label: 'Expense records', data: d.expense_counts, borderColor: '#4f46e5',
      backgroundColor: 'rgba(79,70,229,.12)', fill: true, tension: .3 }] },
    options: { ...base, scales: { y: intAxis } },
  });
  new Chart(document.getElementById('signups'), {
    type: 'bar',
    data: { labels: d.months, datasets: [{ label: 'New users', data: d.signups, backgroundColor: '#0ea5e9', borderRadius: 4 }] },
    options: { ...base, scales: { y: intAxis } },
  });
  new Chart(document.getElementById('logins'), {
    type: 'bar',
    data: { labels: d.days, datasets: [{ label: 'Users logged in', data: d.logins, backgroundColor: '#10b981', borderRadius: 4 }] },
    options: { ...base, scales: { y: intAxis } },
  });
  const mix = document.getElementById('categoryMix');
  if (!d.categories.length) {
    mix.parentElement.innerHTML = '<div class="chart-empty">No expenses recorded yet</div>';
  } else {
    new Chart(mix, {
      type: 'doughnut',
      data: { labels: d.categories, datasets: [{ data: d.category_counts, backgroundColor: palette }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right' } } },
    });
  }
})();
