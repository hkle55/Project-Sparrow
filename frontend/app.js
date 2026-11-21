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
  mode: "auto",        // server picks work/home by time of day; Switch mode overrides until reload
  clockView: store.get("sparrow.view", "countdown") === "clock",  // show ET clock times
  sim: "",
  season: "",          // "" = from the date; Dev menu can preview another season
  netDown: false,
  data: null,          // last successful response
  skew: 0,             // server_now - client_now (seconds)
  lastOk: 0,           // client time of last successful poll (seconds)
  lastError: null,
  modes: ["auto", "work", "home"],
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

// --- Seasons: decoration only, picked from the Eastern-time month ------------------------
const SEASONS = ["winter", "winter", "spring", "spring", "spring", "summer",
  "summer", "summer", "fall", "fall", "fall", "winter"];  // Jan..Dec
const etMonth = new Intl.DateTimeFormat("en-US", { timeZone: ET, month: "numeric" });
const seasonOf = (epoch) => SEASONS[Number(etMonth.format(new Date(epoch * 1000))) - 1];

// Stable pseudo-random numbers per particle, so nothing needs to be stored between frames.
const rand = (i, salt) => {
  const v = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453;
  return v - Math.floor(v);
};

// Falling particles. y wraps around, x sways; `t` is seconds (frozen when motion is reduced).
function fall(c, t, n, speed, sway, colors, size) {
  for (let i = 0; i < n; i++) {
    const v = speed * (0.6 + rand(i, 1) * 0.8);
    const y = ((t * v + rand(i, 2) * 30) % 30) - 3;
    const x = Math.round((rand(i, 3) * SCENE_W + Math.sin(t * (0.8 + rand(i, 4)) + i) * sway
      + SCENE_W) % SCENE_W);
    c.fillStyle = colors[i % colors.length];
    const [w, h] = size(i, t);
    c.fillRect(x, Math.round(y), w, h);
  }
}

const WEATHER = {
  winter(c, t) {
    fall(c, t, 22, 4, 2, ["#ffffff", "#dfe8f0"], (i) => (i % 5 === 0 ? [2, 2] : [1, 1]));
  },
  spring(c, t) {  // cherry blossom petals
    fall(c, t, 12, 3, 4, ["#f7b6c8", "#fbd3df", "#f39ab4"], (i) => (i % 3 === 0 ? [2, 1] : [1, 1]));
  },
  summer(c, t) {  // sun with twinkling rays
    const [cx, cy] = [8, 6];
    c.fillStyle = "#ffd23f";
    c.fillRect(cx - 2, cy - 3, 5, 7); c.fillRect(cx - 3, cy - 2, 7, 5);
    c.fillStyle = "#ffe98a"; c.fillRect(cx - 1, cy - 2, 2, 2);
    const long = Math.floor(t * 2) % 2 === 0;
    c.fillStyle = "#ffb627";
    for (const [dx, dy] of [[0, -5], [0, 5], [-5, 0], [5, 0]]) {
      c.fillRect(cx + dx, cy + dy, 1, 1);
      if (long) c.fillRect(cx + dx * 1.2, cy + dy * 1.2, 1, 1);
    }
    for (const [dx, dy] of [[-4, -4], [4, -4], [-4, 4], [4, 4]]) {
      if (!long) c.fillRect(cx + dx, cy + dy, 1, 1);
    }
  },
  fall(c, t) {  // leaves tumble: they flip between flat and edge-on
    fall(c, t, 10, 3, 5, ["#e8742c", "#c0392b", "#f2b134", "#a0522d"],
      (i, tt) => (Math.floor(tt * 3 + i) % 2 ? [2, 1] : [1, 2]));
  },
};

// Things that sit on the ground for each season (drawn under the bus).
const GROUND = {
  winter(c) { c.fillStyle = "#e8eef4"; c.fillRect(0, 20, SCENE_W, 1); },  // snow on the curb
  spring(c) { c.fillStyle = "#4a7c3a"; for (const x of [12, 40, 71, 93]) c.fillRect(x, 19, 1, 2); },
  summer() {},
  fall(c) {
    for (const [x, col] of [[15, "#c0392b"], [48, "#e8742c"], [77, "#f2b134"], [99, "#e8742c"]]) {
      c.fillStyle = col; c.fillRect(x, 20, 2, 1);
    }
  },
};

let sceneRec = null;  // what drawScene last showed, so the animation loop can redraw it

function drawScene(rec, now) {
  sceneRec = rec;
  const c = $("scene").getContext("2d");
  const season = state.season || seasonOf(now);
  const t = reduceMotion ? 0 : performance.now() / 1000;
  c.clearRect(0, 0, SCENE_W, 26);
  c.globalAlpha = 1;
  WEATHER[season](c, t);
  c.fillStyle = "#3a3a3a"; c.fillRect(0, 21, SCENE_W, 1);                 // curb
  GROUND[season](c);
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
  if (season === "winter") { c.fillStyle = "#ffffff"; c.fillRect(x + 2, 9, 19, 1); }  // snowy roof
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
  $("modeLabel").textContent = data.label.toUpperCase() + (data.auto ? " · AUTO" : "");

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
    state.modes = ["auto", ...modes.filter((m) => m.configured).map((m) => m.mode)];
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
    $("modeLabel").textContent = `${state.mode.toUpperCase()}…`;  // until the new data arrives
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
  $("seasonSelect").addEventListener("change", (e) => { state.season = e.target.value; render(); });
  $("netSim").addEventListener("change", (e) => { state.netDown = e.target.checked; poll(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });

  poll();
  setInterval(poll, POLL_MS);
  setInterval(render, 1000);
  // Smooth falling snow/leaves/petals between the once-a-second redraws.
  if (!reduceMotion) setInterval(() => { if (state.data) drawScene(sceneRec, serverNow()); }, 100);
}

init();
