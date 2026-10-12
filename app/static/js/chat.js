// AI chatbot UI. Messages are inserted with textContent (never innerHTML) so
// nothing the AI returns can inject HTML/JS into the page.
(function () {
  const box = document.getElementById("chatMessages");
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const send = document.getElementById("chatSend");
  const history = []; // last few turns, sent back so follow-up questions work

  function addMessage(text, who) {
    const div = document.createElement("div");
    div.className = "msg " + (who === "user" ? "msg-user" : "msg-bot");
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
  }
  function addNote(text) {
    const div = document.createElement("div");
    div.className = "msg-note";
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  async function ask(question) {
    addMessage(question, "user");
    const pending = addMessage("Thinking…", "bot");
    send.disabled = input.disabled = true;
    try {
      const res = await fetch(window.CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": window.SMARTSPEND.csrf },
        body: JSON.stringify({ message: question, history: history.slice(-6) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Request failed");
      pending.textContent = data.reply;
      if (data.notice) addNote(data.notice);
      history.push({ role: "user", content: question }, { role: "assistant", content: data.reply });
    } catch (err) {
      pending.textContent = "Sorry, something went wrong: " + err.message;
    } finally {
      send.disabled = input.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    ask(q);
  });
  document.querySelectorAll(".suggestion").forEach((b) =>
    b.addEventListener("click", () => ask(b.textContent.trim()))
  );
})();
