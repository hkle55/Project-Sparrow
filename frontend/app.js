// Sparrow device simulator: a thin client. The backend does all the transit logic;
// this only polls, counts down locally between polls, and renders.
"use strict";

const POLL_MS = 15000;        // backend caches SEPTA for 20 s, so faster polling buys nothing
const NO_CONN_AFTER_S = 45;   // no successful poll for this long -> "NO CONNECTION"
const LEAVE_NOW_S = 60;

const $ = (id) => document.getElementById(id);
const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const state = {
  mode: store.get("sparrow.mode", "work"),
  sim: "",
  netDown: false,
  data: null,          // last successful response
  skew: 0,             // server_now - client_now (seconds)
  lastOk: 0,           // client time of last successful poll (seconds)
  lastError: null,
  modes: ["work", "home"],
};

const clientNow = () => Date.now() / 1000;
const serverNow = () => clientNow() + state.skew;
const mins = (s) => Math.floor(s / 60);   // always floor: never overstate time left

const viewKey = () => `${state.mode}|${state.sim}`;

async function poll() {
  const key = viewKey();
  const url = `/api/v1/commute/${state.mode}` + (state.sim ? `?sim=${encodeURIComponent(state.sim)}` : "");
  try {
    if (state.netDown) throw new Error("simulated network loss");
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (key !== viewKey()) return; // user switched mode/scenario while this was in flight
    state.skew = data.now - clientNow();
    state.data = data;
    state.lastOk = clientNow();
    state.lastError = null;
  } catch (err) {
    state.lastError = String(err.message || err);
  }
  render();
}

function badgeFor(data, disconnected) {
  if (disconnected) return ["NO CONN", "noconn"];
  if (!data.configured) return ["SETUP", "offline"];
  return {
    live: ["LIVE", "live"],
    stale: ["STALE", "stale"],
    offline: ["SCHED", "scheduled"],
  }[data.data.status] || ["?", "offline"];
}

function heroFor(data, disconnected, now) {
  const rec = data.rec;
  if (!data.configured) return { route: "", action: "NOT SET UP", cls: "none", reason: data.message };
  if (!rec) return { route: "", action: "NO BUS", cls: "none", reason: data.message || "" };

  const left = rec.leave_at - now;
  const untilBus = rec.arrives_at - now;
  let action, cls;
  const route = data.routes.find((r) => r.route === rec.route);
  const walkS = route ? route.walk_min * 60 : 0;
  if (left < 0) {
    // Leave time passed since the last poll. Still reachable on foot? Then hurry;
    // otherwise wait for the next poll to pick another bus.
    if (untilBus >= walkS) { action = "LEAVE NOW"; cls = "leave_now"; }
    else { action = "CHECKING…"; cls = "none"; }
  } else if (left < LEAVE_NOW_S) {
    action = "LEAVE NOW"; cls = "leave_now";
  } else if (left < rec.ready_s) {
    action = `GET READY ${mins(left)}m`; cls = "get_ready";
  } else {
    action = `LEAVE IN ${mins(left)}m`; cls = "leave_in";
  }
  let reason = rec.reason;
  if (rec.approx) reason = `${kindWord(rec.kind)} time, not live · ${reason}`;
  if (disconnected) reason = `Offline: countdown may be wrong · ${reason}`;
  return { route: `BUS ${rec.route}`, action, cls: cls + (rec.approx || disconnected ? " approx" : ""), reason };
}

function kindWord(kind) {
  return { scheduled: "Scheduled", estimated: "Estimated", stale: "Old", live: "Live" }[kind] || kind;
}

function renderRows(data, now) {
  const rows = $("rows");
  rows.replaceChildren();
  if (!data.configured) return;
  for (const r of data.routes) {
    const row = document.createElement("div");
    row.className = "row";
    const label = document.createElement("span");
    label.className = "label";
    label.innerHTML = `ROUTE <b>${r.route}</b>`;
    row.append(label);
    for (let i = 0; i < 3; i++) {
      const a = r.arrivals[i];
      const cell = document.createElement("span");
      cell.className = "t";
      if (!a) {
        cell.textContent = "—";
        cell.classList.add("empty");
      } else {
        const m = mins(a.at - now);
        const text = m <= 0 ? "now" : `${m}m`;
        const notLive = a.kind !== "live";
        cell.textContent = notLive ? `~${text}` : text;
        if (notLive) cell.classList.add("approx");
        // catch state can only get worse as time passes; recompute locally
        const slack = a.leave_at - now;
        const walkOnly = a.at - now - r.walk_min * 60;
        if (walkOnly < 0) cell.classList.add("missed");
        else if (slack < 0) cell.classList.add("tight");
        cell.title = `${a.kind}${a.dest ? " → " + a.dest : ""}${a.veh ? " · bus " + a.veh : ""}`;
      }
      row.append(cell);
    }
    rows.append(row);
  }
}

function render() {
  const data = state.data;
  const now = serverNow();
  const sinceOk = state.lastOk ? clientNow() - state.lastOk : Infinity;
  const disconnected = state.lastError !== null && sinceOk > NO_CONN_AFTER_S;

  if (!data) {
    $("action").textContent = state.lastError ? "NO CONNECTION" : "LOADING";
    $("badge").textContent = state.lastError ? "NO CONN" : "…";
    $("badge").className = "badge noconn";
    $("updated").textContent = state.lastError ? `Can't reach Sparrow (${state.lastError})` : "";
    return;
  }

  $("device").classList.toggle("simulated", !!data.simulated);
  $("simBanner").hidden = !data.simulated;
  $("modeLabel").textContent = data.label.toUpperCase();

  const [badge, badgeCls] = badgeFor(data, disconnected);
  $("badge").textContent = badge;
  $("badge").className = `badge ${badgeCls}`;

  const hero = heroFor(data, disconnected, now);
  $("route").textContent = hero.route || " ";
  $("action").textContent = hero.action;
  $("reason").textContent = hero.reason || " ";
  $("hero").className = `hero ${hero.cls}`;

  renderRows(data, now);

  // Freshness: how old SEPTA's data is right now, not just when we last asked.
  const updated = $("updated");
  if (data.data.feed_age_s != null) {
    const age = Math.max(0, Math.round(data.data.feed_age_s + (clientNow() - state.lastOk)));
    updated.textContent = age < 90 ? `Updated ${age}s ago` : `Updated ${mins(age)}m ago`;
  } else if (data.configured) {
    updated.textContent = data.simulated ? "Simulated data" : "No live data";
  } else {
    updated.textContent = "";
  }
  const conn = $("conn");
  if (disconnected) {
    conn.textContent = `NO CONNECTION ${mins(sinceOk)}m`;
    conn.className = "bad";
  } else if (state.lastError) {
    conn.textContent = "retrying…";
    conn.className = "bad";
    conn.title = state.lastError;
  } else if (data.data.error && !data.simulated) {
    conn.textContent = "SEPTA issue";
    conn.className = "bad";
    conn.title = data.data.error;
  } else {
    conn.textContent = "";
    conn.className = "";
  }
}

async function init() {
  try {
    const [modes, scenarios] = await Promise.all([
      fetch("/api/v1/modes").then((r) => r.json()),
      fetch("/api/v1/scenarios").then((r) => r.json()),
    ]);
    state.modes = modes.map((m) => m.mode);
    if (!state.modes.includes(state.mode)) state.mode = state.modes[0];
    for (const s of scenarios) {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.label;
      $("simSelect").append(opt);
    }
  } catch { /* poll() will surface connection problems */ }

  $("modeBtn").addEventListener("click", () => {
    const i = state.modes.indexOf(state.mode);
    state.mode = state.modes[(i + 1) % state.modes.length];
    store.set("sparrow.mode", state.mode);
    state.data = null;
    poll();
  });
  $("refreshBtn").addEventListener("click", poll);
  $("simSelect").addEventListener("change", (e) => { state.sim = e.target.value; state.data = null; poll(); });
  $("netSim").addEventListener("change", (e) => { state.netDown = e.target.checked; poll(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  poll();
  setInterval(poll, POLL_MS);
  setInterval(render, 1000);
}

init();
