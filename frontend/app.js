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
  clockView: store.get("sparrow.view", "countdown") === "clock",  // show ET clock times
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
const mins = (s) => Math.floor(s / 60);

// Eastern time, whatever timezone the viewer's phone is in. Uses the server-corrected clock.
const ET = "America/New_York";
const etTime = new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "numeric", minute: "2-digit" });
const etClock = new Intl.DateTimeFormat("en-US", {
  timeZone: ET, hour: "numeric", minute: "2-digit", second: "2-digit", timeZoneName: "short",
});
const hm = (epoch) => etTime.format(new Date(epoch * 1000));   // always floor: never overstate time left

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
  if (rec.action === "tight" || left < 0) {
    // TIGHT from the server, or the leave time passed since the last poll. Still reachable
    // on foot? Then it's a tight connection; otherwise wait for the next poll to re-plan.
    if (untilBus >= walkS) { action = "TIGHT · GO NOW"; cls = "tight"; }
    else { action = "CHECKING…"; cls = "none"; }
  } else if (left < LEAVE_NOW_S) {
    action = "LEAVE NOW"; cls = "leave_now";
  } else if (left < rec.ready_s) {
    action = state.clockView ? `GET READY · LEAVE ${hm(rec.leave_at)}` : `GET READY ${mins(left)}m`;
    cls = "get_ready";
  } else {
    action = state.clockView ? `LEAVE AT ${hm(rec.leave_at)}` : `LEAVE IN ${mins(left)}m`;
    cls = "leave_in";
  }
  let reason = rec.reason;
  if (rec.approx) reason = `${kindWord(rec.kind)} time, not live · ${reason}`;
  if (disconnected) reason = `Offline: countdown may be wrong · ${reason}`;
  let alt = "";
  if (rec.alt) {
    const altLeft = rec.alt.leave_at - now;
    alt = altLeft >= 0
      ? `Safer: BUS ${rec.alt.route} · ` +
        (state.clockView ? `leave ${hm(rec.alt.leave_at)}` : `leave in ${mins(altLeft)}m`)
      : `Safer: BUS ${rec.alt.route}`;
  }
  return {
    route: `BUS ${rec.route}`, action, reason, alt,
    cls: cls + (rec.approx || disconnected ? " approx" : ""),
  };
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
        const text = state.clockView ? hm(a.at) : m <= 0 ? "now" : `${m}m`;
        const notLive = a.kind !== "live";
        cell.textContent = notLive ? `≈${text}` : text;
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

// --- Pixel-art scene: the bus's distance from the stop tracks the recommended bus --------
// Decorative only (the text says everything); 15+ min away = far left, arriving = at the stop.
const SCENE_W = 120, SCENE_RANGE_S = 15 * 60;
const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function drawBus(c, x, y, frame) {
  const px = (dx, dy, w, h, col) => { c.fillStyle = col; c.fillRect(x + dx, y + dy, w, h); };
  px(1, 0, 22, 1, "#e8e8e8");                       // roof
  px(0, 1, 24, 9, "#e8e8e8");                       // body
  for (let i = 0; i < 4; i++) px(2 + i * 4, 2, 3, 3, "#33414f");  // side windows
  px(18, 2, 2, 7, "#33414f");                       // door
  px(21, 2, 3, 4, "#7fb3e0");                       // windshield
  px(0, 6, 18, 1, "#d0021b"); px(20, 6, 4, 1, "#d0021b");         // stripe
  px(23, 8, 1, 1, "#ffd23f");                       // headlight
  for (const wx of [3, 16]) {                       // wheels, hubs turn while it moves
    px(wx, 9, 5, 3, "#111");
    px(wx + 1 + frame, 10, 1, 1, "#999");
  }
}

function drawScene(rec, now) {
  const c = $("scene").getContext("2d");
  c.clearRect(0, 0, SCENE_W, 26);
  c.globalAlpha = 1;
  c.fillStyle = "#3a3a3a"; c.fillRect(0, 21, SCENE_W, 1);                 // curb
  for (let x = 2; x < SCENE_W; x += 8) { c.fillStyle = "#2a2a2a"; c.fillRect(x, 24, 4, 1); }  // lane dashes
  c.fillStyle = "#8a8a8a"; c.fillRect(110, 7, 1, 14);                     // stop pole
  c.fillStyle = "#2f80ed"; c.fillRect(106, 3, 9, 6);                      // stop sign
  c.fillStyle = "#fff"; c.fillRect(108, 5, 5, 2);
  if (!rec) return;
  const untilBus = rec.arrives_at - now;
  const p = Math.min(1, Math.max(0, 1 - untilBus / SCENE_RANGE_S));
  const x = Math.round(-4 + p * (104 - 24 + 4));     // bus front reaches the stop on arrival
  const moving = untilBus > 0 && !reduceMotion;
  if (rec.approx) c.globalAlpha = 0.45;              // not live: a "ghost" bus
  drawBus(c, x, 10, moving ? Math.floor(now) % 2 : 0);
  c.globalAlpha = 1;
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
  $("clock").textContent = etClock.format(new Date(now * 1000));
  $("badge").textContent = badge;
  $("badge").className = `badge ${badgeCls}`;

  const hero = heroFor(data, disconnected, now);
  $("route").textContent = hero.route || " ";
  $("action").textContent = hero.action;
  $("reason").textContent = hero.reason || " ";
  $("alt").textContent = hero.alt || "";
  $("alt").hidden = !hero.alt;
  $("hero").className = `hero ${hero.cls}`;
  drawScene(data.configured ? data.rec : null, now);

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
  const syncView = () => {
    $("viewBtn").textContent = state.clockView ? "Show countdown" : "Show schedule";
    $("viewBtn").setAttribute("aria-pressed", String(state.clockView));
  };
  syncView();
  $("viewBtn").addEventListener("click", () => {
    state.clockView = !state.clockView;
    store.set("sparrow.view", state.clockView ? "clock" : "countdown");
    syncView();
    render();
  });
  $("simSelect").addEventListener("change", (e) => { state.sim = e.target.value; state.data = null; poll(); });
  $("netSim").addEventListener("change", (e) => { state.netDown = e.target.checked; poll(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  poll();
  setInterval(poll, POLL_MS);
  setInterval(render, 1000);
}

init();
