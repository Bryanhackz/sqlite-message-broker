// © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
// Admin monitor: polls /admin/stats. The admin key lives in memory only,
// never in localStorage, sessionStorage, or cookies.

const state = { key: null, timer: null };

const $ = (sel) => document.querySelector(sel);

function setStatus(text) {
  const el = $("#status");
  if (el) el.textContent = text;
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

async function refresh() {
  if (!state.key) return;
  const tbody = $("#queues tbody");
  if (!tbody) return;
  try {
    const res = await fetch("/admin/stats", {
      headers: { "X-API-Key": state.key, "Accept": "application/json" },
      credentials: "same-origin",
    });
    if (res.status === 401) {
      setStatus("Invalid API key");
      disconnect();
      return;
    }
    if (!res.ok) return;
    const data = await res.json();
    tbody.replaceChildren();
    for (const [name, stats] of Object.entries(data.queues || {})) {
      const tr = document.createElement("tr");
      tr.append(cell(name));
      for (const key of ["pending", "processing", "done", "dead"]) {
        tr.append(cell(String(stats[key] ?? 0)));
      }
      tbody.append(tr);
    }
    setStatus("Connected");
  } catch {
    setStatus("Network error");
  }
}

function disconnect() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  state.key = null;
  setStatus("Disconnected");
}

function connect(key) {
  state.key = key;
  if (state.timer) clearInterval(state.timer);
  refresh();
  state.timer = setInterval(refresh, 2000);
}

document.addEventListener("DOMContentLoaded", () => {
  const form = $("#key-form");
  const input = $("#api-key");
  const dc = $("#disconnect");
  if (form && input) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (!input.value) return;
      connect(input.value);
      input.value = "";
    });
  }
  if (dc) dc.addEventListener("click", disconnect);
});