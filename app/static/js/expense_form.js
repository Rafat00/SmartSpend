// "Suggest category" button on the Add/Edit expense form.
// The browser only talks to OUR server; the API key stays on the server.
(function () {
  const btn = document.getElementById("aiCategorizeBtn");
  if (!btn) return;
  const status = document.getElementById("aiStatus");

  btn.addEventListener("click", async () => {
    const name = document.getElementById("expense_name").value.trim();
    const store = document.getElementById("store").value.trim();
    const note = document.getElementById("description").value.trim();
    const text = [name, store ? "from " + store : "", note].filter(Boolean).join(" ");
    if (!name) { status.textContent = "Type an expense name first."; return; }

    btn.disabled = true;
    status.textContent = "Thinking…";
    try {
      const res = await fetch(window.CATEGORIZE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": window.SMARTSPEND.csrf },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Request failed");
      document.getElementById("category").value = data.category;
      document.getElementById("subcategory").value = data.subcategory || "";
      const how = data.source === "ai" ? "AI suggests" : "Suggested (rule-based)";
      status.textContent = how + ": " + data.category + (data.subcategory ? " › " + data.subcategory : "") + (data.notice ? " — " + data.notice : "");
    } catch (err) {
      status.textContent = "Could not suggest a category: " + err.message;
    } finally {
      btn.disabled = false;
    }
  });
})();
