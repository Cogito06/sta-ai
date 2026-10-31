"use strict";
// Spire Chronicle: read-only dashboard over runs/, guides/ and runs/lessons.json (see dashboard/server.py).

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path) => {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
};

const TEST_SEEDS = new Set(["SCENARIO1", "61599666974301", "SMOKE2"]);
const ROOM_ICON = { M: "⚔", E: "☠", R: "🔥", $: "💰", T: "◆", "?": "?", B: "♛" };
const ROOM_NAME = { MonsterRoom: "普通战斗", MonsterRoomElite: "精英", MonsterRoomBoss: "Boss", RestRoom: "休息处", ShopRoom: "商店", TreasureRoom: "宝箱", EventRoom: "事件", NeowRoom: "涅奥" };
const SCREEN_NAME = {
  EVENT: "事件", MAP: "地图", COMBAT_REWARD: "战斗奖励", CARD_REWARD: "选牌", SHOP_ROOM: "商店入口", SHOP_SCREEN: "商店",
  REST: "休息处", BOSS_REWARD: "Boss 遗物", GRID: "选择卡牌", HAND_SELECT: "选择手牌", GAME_OVER: "结算", CHEST: "宝箱", NONE: "战斗",
};
const TYPE_NAME = { ATTACK: "攻击", SKILL: "技能", POWER: "能力", CURSE: "诅咒", STATUS: "状态" };
const BAD_POWERS = new Set(["Vulnerable", "Weakened", "Frail", "Poison", "Entangled", "No Draw", "Hex", "Constricted", "Shackled", "Draw Reduction", "Confusion"]);

const state = {
  runs: [],
  catalog: { cards: {}, relics: {}, potions: {} },
  knowledge: null,
  run: null,          // detail of the run shown in replay
  step: 1,
  stepCache: new Map(),
  act: null,
  playTimer: null,
  live: { run: null, steps: 0, timer: null },
  hideTests: true,
};

const pageHead = (crumbs, title, small, desc) => `
  <div class="page-head">
    <div class="crumbs">${["Spire Chronicle", ...crumbs].map((c) => `<span>${esc(c)}</span>`).join("")}</div>
    <h1 class="section-title">${esc(title)}${small ? `<small>${esc(small)}</small>` : ""}</h1>
    ${desc ? `<p class="page-desc">${esc(desc)}</p>` : ""}
  </div>`;

// ---------- tooltip ----------
const tip = $("#tooltip");
document.addEventListener("mouseover", (ev) => {
  const el = ev.target.closest("[data-tip]");
  if (!el) return;
  tip.innerHTML = el.dataset.tip;
  tip.hidden = false;
});
document.addEventListener("mousemove", (ev) => {
  if (tip.hidden) return;
  const x = Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 16, window.innerHeight - tip.offsetHeight - 8);
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
});
document.addEventListener("mouseout", (ev) => {
  if (ev.target.closest("[data-tip]")) tip.hidden = true;
});
const tipHtml = (title, sub, body) =>
  esc(`<div class="tt-title">${esc(title)}</div>${sub ? `<div class="tt-sub">${esc(sub)}</div>` : ""}<div>${esc(body || "")}</div>`);

function cardInfo(card) {
  const entry = state.catalog.cards[card.id];
  const face = entry ? (card.upgrades ? entry.upgraded || entry.base : entry.base) : null;
  return { english: face?.name || card.id, text: face?.text || "", rarity: entry?.rarity || "" };
}

// ---------- time helpers ----------
const parseT = (t) => (t ? new Date(t) : null);
function duration(a, b) {
  const s = (parseT(b) - parseT(a)) / 1000;
  if (!isFinite(s) || s < 0) return "—";
  const m = Math.round(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)} 小时 ${m % 60} 分` : `${m} 分钟`;
}
const fmtDate = (t) => (t ? t.replace("T", " ").slice(0, 16) : "—");
// "20261023_171713_seed-..." -> "10-23 17:17 那局"
const runLabel = (id) => {
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/.exec(id || "");
  return m ? `${m[2]}-${m[3]} ${m[4]}:${m[5]} 那局` : id || "";
};

// ---------- the spire behind every page ----------
// A spire taller than the screen. Floors map onto its three tiers (one per act) and the tip (the heart).
// Scrolling a page climbs it; in replay and live it follows the floor in view, so dragging the steps moves it.
const TOWER_H = 2000;
const TOWER_BANDS = [[0, 1880], [17, 1360], [34, 860], [51, 400], [56, 150]];
function floorY(f) {
  f = Math.max(0, Math.min(56, f || 0));
  for (let i = 1; i < TOWER_BANDS.length; i++) {
    const [f0, y0] = TOWER_BANDS[i - 1], [f1, y1] = TOWER_BANDS[i];
    if (f <= f1) return y0 + ((f - f0) / (f1 - f0)) * (y1 - y0);
  }
  return 150;
}
function buildTower() {
  const tiers = [[1880, 1360, 124, 98], [1360, 860, 88, 66], [860, 400, 56, 38]]; // [bottom y, top y, bottom half-width, top half-width]
  let body = "", windows = "";
  tiers.forEach(([yb, yt, wb, wt], i) => {
    body += `<path class="tw-body" d="M${200 - wb} ${yb} L${200 - wt} ${yt} L${200 + wt} ${yt} L${200 + wb} ${yb} Z"/>`;
    body += `<rect class="tw-ledge" x="${200 - wt - 10}" y="${yt - 8}" width="${(wt + 10) * 2}" height="10" rx="2"/>`;
    for (let y = yb - 40; y > yt + 24; y -= 52) {
      const half = wb + ((wt - wb) * (yb - y)) / (yb - yt) - 22;
      for (let x = -half; x <= half; x += Math.max(26, half / 1.5)) windows += `<rect class="tw-win" x="${200 + x - 3}" y="${y - 9}" width="6" height="12" rx="3"/>`;
    }
    body += `<text class="tw-act" x="${200 + wb + 14}" y="${(yb + yt) / 2}">第 ${["一", "二", "三"][i]} 幕</text>`;
  });
  const spire = `<path class="tw-body" d="M162 400 L200 110 L238 400 Z"/><circle class="tw-heart" cx="200" cy="250" r="10"/>
    <text class="tw-act" x="252" y="262">心脏</text>`;
  const land = `<path class="tw-land" d="M-40 2000 L-40 1900 Q60 1850 130 1880 Q200 1905 270 1876 Q350 1842 440 1890 L440 2000 Z"/>`;
  const clouds = `<g class="tw-cloud"><ellipse cx="110" cy="1120" rx="90" ry="14"/><ellipse cx="300" cy="1150" rx="70" ry="11"/>
    <ellipse cx="270" cy="660" rx="80" ry="12"/><ellipse cx="120" cy="690" rx="55" ry="9"/><ellipse cx="290" cy="320" rx="60" ry="9"/></g>`;
  const marker = `<g id="tower-runs"></g><g id="tower-mark" style="display:none"><line class="tw-mark" x1="40" x2="360" y1="0" y2="0"/>
    <circle class="tw-mark-dot" cx="200" cy="0" r="6"/><text class="tw-mark-text" x="-40" y="-10"></text></g>`;
  const box = document.createElement("div");
  box.className = "tower-bg";
  box.setAttribute("aria-hidden", "true");
  box.innerHTML = `<svg viewBox="-60 0 520 ${TOWER_H}">${land}${body}${spire}${windows}${clouds}${marker}</svg>`;
  document.body.prepend(box);
}
let towerFocus = null;   // a floor to keep centred (replay, live), or null to follow the page scroll
function layoutTower() {
  const box = $(".tower-bg"), svg = box && box.querySelector("svg");
  if (!svg) return;
  const avail = box.clientHeight, h = svg.getBoundingClientRect().height;
  const lowest = Math.min(0, avail - h);   // base at the bottom of the screen
  let off;
  if (towerFocus != null) {
    off = avail * 0.5 - floorY(towerFocus) * (h / TOWER_H);
  } else {
    const room = document.documentElement.scrollHeight - window.innerHeight;
    off = lowest * (1 - (room > 0 ? window.scrollY / room : 0));
  }
  svg.classList.toggle("follow", towerFocus != null);
  svg.style.transform = `translateY(${Math.max(lowest, Math.min(0, off)).toFixed(1)}px)`;
}
window.addEventListener("scroll", () => towerFocus == null && layoutTower(), { passive: true });
window.addEventListener("resize", layoutTower);
function setTowerFloor(floor, label, follow = false) {
  const g = $("#tower-mark");
  if (!g) return;
  towerFocus = follow ? floor || 0 : null;
  if (floor == null) g.style.display = "none";
  else {
    g.style.display = "";
    g.setAttribute("transform", `translate(0 ${floorY(floor).toFixed(1)})`);
    g.querySelector("text").textContent = label || `F${floor}`;
  }
  layoutTower();
}buildTower();
layoutTower();
// One dot per run at the floor where it ended, fanned out sideways so runs on the same floor stay visible.
function setTowerRuns(runs) {
  const g = $("#tower-runs");
  if (!g) return;
  const byFloor = {};
  g.innerHTML = runs.map((r) => {
    const k = r.floor || 0, i = (byFloor[k] = (byFloor[k] || 0) + 1) - 1;
    const x = 200 + (i % 2 ? 1 : -1) * Math.ceil(i / 2) * 14;
    const cls = r.result === "胜利" ? "win" : r.result === "阵亡" ? "dead" : "going";
    return `<circle class="tw-run ${cls}" cx="${x}" cy="${floorY(k).toFixed(1)}" r="5"><title>${esc(r.seed)} · F${k}</title></circle>`;
  }).join("");
}

// ---------- navigation ----------
function show(view) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view !== "live") stopLive();
  if (view === "live") startLive();
  if (view === "lore" && !state.knowledge) loadLore();
  if (view === "archive") loadArchive(location.hash.split("/")[1]);
  if (view === "replay" && !state.run && state.runs.length) openRun(defaultRun().id, false);
  if (view === "replay" && state.run) setStep(state.step);
  else if (view !== "live") setTowerFloor(state.bestFloor, state.bestFloor != null ? `最高 F${state.bestFloor}` : "");
  if (location.hash.slice(1).split("/")[0] !== view) location.hash = view;
}
$("#tabs").addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (b) show(b.dataset.view);
});

const isTest = (r) => TEST_SEEDS.has(String(r.seed)) || r.steps < 10;
const defaultRun = () => state.runs.find((r) => !isTest(r)) || state.runs[0];

// ---------- hall ----------
function renderHall() {
  const root = $("#view-hall");
  const runs = state.runs.filter((r) => !state.hideTests || !isTest(r));
  const real = state.runs.filter((r) => !isTest(r));
  const done = real.filter((r) => r.result !== "进行中");
  const wins = real.filter((r) => r.result === "胜利").length;
  const best = Math.max(0, ...real.map((r) => r.floor || 0));
  const avg = done.length ? (done.reduce((s, r) => s + (r.floor || 0), 0) / done.length).toFixed(1) : "—";
  const bestScore = Math.max(0, ...real.map((r) => r.score || 0));
  state.bestFloor = best;
  setTowerRuns(real);
  if ($("#view-hall").classList.contains("active")) setTowerFloor(best, `最高 F${best}`);
  root.innerHTML = `
    ${pageHead(["Records"], "对局记录", "Ascent Log", "AI 铁甲战士的每一次攀登。点击一行查看逐步回放。")}
    <div class="grid stats">
      ${[["攀登次数<span class=\"en\">Runs</span>", real.length, ""], ["登顶<span class=\"en\">Cleared</span>", wins, "gold"], ["最高楼层<span class=\"en\">Peak</span>", best, ""], ["平均楼层<span class=\"en\">Avg</span>", avg, ""], ["最高分<span class=\"en\">Score</span>", bestScore || "—", "accent"]]
        .map(([l, n, c]) => `<div class="panel stat"><div class="lbl">${l}</div><div class="num ${c}">${n}</div></div>`).join("")}
    </div>
    <div class="filters">
      <input type="search" id="run-search" placeholder="搜索种子、结果、日期">
      <label><input type="checkbox" id="hide-tests" ${state.hideTests ? "checked" : ""}> 隐藏测试局</label>
      <span class="muted">共 ${runs.length} 局</span>
    </div>
    <div class="table-wrap"><table class="data">
      <thead><tr><th>结果</th><th>种子</th><th>进阶</th><th>记忆</th><th>楼层</th><th>分数</th><th>血量</th><th>金币</th><th>步数</th><th>用时</th><th>开始时间</th></tr></thead>
      <tbody id="run-grid"></tbody>
    </table></div>`;
  const grid = $("#run-grid");
  const paint = (q) => {
    const list = runs.filter((r) => !q || `${r.seed} ${r.result} ${r.started} ${r.id}`.toLowerCase().includes(q.toLowerCase()));
    grid.innerHTML = list.map(runCard).join("") || `<tr><td colspan="11" class="empty">没有符合条件的对局</td></tr>`;
  };
  paint("");
  $("#run-search").addEventListener("input", (e) => paint(e.target.value));
  $("#hide-tests").addEventListener("change", (e) => { state.hideTests = e.target.checked; renderHall(); });
  grid.addEventListener("click", (ev) => {
    const card = ev.target.closest("[data-run]");
    if (card) { openRun(card.dataset.run); show("replay"); }
  });
}

function runCard(r) {
  const cls = r.result === "胜利" ? "win" : r.result === "阵亡" ? "dead" : "";
  const badge = r.result === "胜利" ? `<span class="badge win">登顶</span>`
    : r.result === "阵亡" ? `<span class="badge dead">阵亡</span>` : `<span class="badge going">进行中</span>`;
  const mem = r.memory === true ? `<span class="badge mem">开</span>` : r.memory === false ? `<span class="badge nomem">关</span>` : `<span class="muted">—</span>`;
  const pct = Math.min(100, ((r.floor || 0) / 55) * 100);
  const act = (r.floor || 0) > 34 ? "第三幕" : (r.floor || 0) > 17 ? "第二幕" : "第一幕";
  return `
    <tr class="${cls || "going"}" data-run="${esc(r.id)}" title="${esc(r.id)}">
      <td class="result">${badge}</td>
      <td><div class="seed">${esc(r.seed)}</div><div class="sub">${esc(r.class || "IRONCLAD")}${r.resumed ? " · 续局" : ""}</div></td>
      <td>A${r.ascension ?? "?"}</td>
      <td>${mem}</td>
      <td><div class="floorbar"><b>${r.floor || 0}</b><div class="track" title="${act}"><i style="width:${pct}%"></i></div></div></td>
      <td><b>${r.score ?? "—"}</b></td>
      <td>${r.hp ?? "?"}<span class="muted">/${r.max_hp ?? "?"}</span></td>
      <td>${r.gold ?? "?"}</td>
      <td>${r.steps}</td>
      <td class="txt">${duration(r.started, r.ended)}</td>
      <td class="muted">${esc(fmtDate(r.started))}</td>
    </tr>`;
}

// ---------- replay ----------
async function openRun(id, scroll = true) {
  stopPlay();
  state.run = await api(`/api/run/${encodeURIComponent(id)}`);
  state.stepCache = new Map();
  state.step = 1;
  state.act = null;
  renderReplayShell();
  await setStep(state.run.timeline.length ? 1 : 0);
  if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderReplayShell() {
  const root = $("#view-replay");
  const run = state.run;
  const s = run.summary;
  const options = state.runs.map((r) => `<option value="${esc(r.id)}" ${r.id === s.id ? "selected" : ""}>${esc(r.seed)} · ${esc(fmtDate(r.started))} · F${r.floor} · ${esc(r.result)}${isTest(r) ? " (测试)" : ""}</option>`).join("");
  const memo = run.memory || {};
  root.innerHTML = `
    ${pageHead(["Replay", s.seed], `${s.seed} 回放`, `Ascension ${s.ascension ?? "?"} · ${s.result === "阵亡" ? "Defeated" : s.result === "胜利" ? "Victory" : "In progress"}`)}
    <div class="replay-head">
      <select id="run-select">${options}</select>
      <span class="badge ${s.result === "胜利" ? "win" : s.result === "阵亡" ? "dead" : "going"}">${esc(s.result)}</span>
      <span class="chip">进阶 ${s.ascension ?? "?"}</span>
      <span class="chip">分数 ${s.score ?? "—"}</span>
      <span class="chip">${duration(s.started, s.ended)}</span>
      <span class="chip">${s.steps} 步</span>
      <span class="chip">${esc(s.id)}</span>
    </div>
    <div class="grid replay-grid">
      <div class="grid">
        <div class="panel">
          <div class="scrubber">
            <button class="btn small" id="prev">◀</button>
            <button class="btn small primary" id="play">▶ 播放</button>
            <button class="btn small" id="next">▶</button>
            <input type="range" id="step-range" min="1" max="${Math.max(1, run.timeline.length)}" value="1">
            <span class="step-label" id="step-label"></span>
          </div>
          <div id="state-view"></div>
        </div>
        <div class="panel map">
          <div class="panel-title">攀登路线</div>
          <div class="act-tabs" id="act-tabs"></div>
          <div id="map-view"></div>
        </div>
      </div>
      <div class="grid">
        <div class="panel chart">
          <div class="panel-title">生命曲线 <span class="hint">点击跳到那一步</span></div>
          <div id="chart"></div>
        </div>
        ${memo.plan || memo.route || (memo.notes || []).length ? `
        <div class="panel">
          <div class="panel-title">本局笔记</div>
          ${memo.plan ? `<div class="memo"><b>构筑计划 · F${memo.plan.floor}</b>${esc(memo.plan.text)}</div>` : ""}
          ${memo.route ? `<div class="memo"><b>路线 · F${memo.route.floor}</b>${esc(memo.route.text)}</div>` : ""}
          ${(memo.notes || []).map((n) => `<div class="memo">${esc(n.text || n)}</div>`).join("")}
        </div>` : ""}
        <div class="panel">
          <div class="panel-title">行动日志</div>
          <div class="log-list" id="log-list">${run.log.map(logItem).join("")}</div>
        </div>
      </div>
    </div>`;
  $("#run-select").addEventListener("change", (e) => openRun(e.target.value, false));
  $("#prev").addEventListener("click", () => setStep(state.step - 1));
  $("#next").addEventListener("click", () => setStep(state.step + 1));
  $("#play").addEventListener("click", togglePlay);
  $("#step-range").addEventListener("input", (e) => setStep(+e.target.value));
  $("#log-list").addEventListener("click", (ev) => {
    const it = ev.target.closest("[data-step]");
    if (it) setStep(+it.dataset.step);
  });
  renderChart();
}

function logItem(e) {
  const parts = [];
  if (e.input) parts.push(`<div class="act">${esc(e.input)}</div>`);
  if (e.inspect) parts.push(`<div class="insp">🔍 查阅 ${esc(e.inspect)}</div>`);
  if (e.note) parts.push(`<div class="note">✒ ${e.tag ? `[${esc(e.tag)}] ` : ""}${esc(e.note)}</div>`);
  if (e.guide) parts.push(`<div class="note">📖 攻略「${esc(e.guide)}」更新</div>`);
  if (e.error) parts.push(`<div class="err">✖ ${esc(e.error)}</div>`);
  if (e.auto && e.auto.length) parts.push(`<div class="auto">↳ ${esc(e.auto.join("；"))}</div>`);
  if (!parts.length) parts.push(`<div class="auto">${esc(Object.keys(e).filter((k) => !["step", "t", "floor", "screen"].includes(k)).join(", ") || "—")}</div>`);
  return `<div class="log-item" data-step="${e.step}"><div><div class="sn">#${e.step}</div><div class="floor">F${e.floor ?? "?"}</div></div><div>${parts.join("")}</div></div>`;
}

async function stepData(runId, step) {
  const key = `${runId}:${step}`;
  if (!state.stepCache.has(key)) state.stepCache.set(key, api(`/api/run/${encodeURIComponent(runId)}/step/${step}`).catch(() => null));
  return state.stepCache.get(key);
}

async function setStep(n) {
  const run = state.run;
  if (!run || !run.timeline.length) {
    $("#state-view").innerHTML = `<div class="empty">这局没有记录到游戏状态</div>`;
    return;
  }
  n = Math.max(1, Math.min(run.timeline.length, n));
  state.step = n;
  $("#step-range").value = n;
  const t = run.timeline[n - 1];
  setTowerFloor(t.floor, `F${t.floor ?? 0}`, true);
  $("#step-label").textContent = `第 ${n} 步 · F${t.floor ?? "?"} · ${SCREEN_NAME[t.screen] || t.screen || ""}`;
  document.querySelectorAll("#log-list .log-item").forEach((el) => el.classList.toggle("cur", +el.dataset.step === n));
  const cur = $(`#log-list .log-item[data-step="${n}"]`);
  // Scroll only the log list; scrollIntoView would also move the page.
  const list = $("#log-list");
  if (cur && list) {
    const top = cur.offsetTop - list.offsetTop;
    if (top < list.scrollTop || top + cur.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = top - list.clientHeight / 3;
  }
  moveChartCursor();
  const act = t.act ?? 1;
  if (state.act !== act) { state.act = act; renderMap(); } else highlightHere();
  const gs = await stepData(run.summary.id, n);
  if (state.step !== n) return;
  $("#state-view").innerHTML = gs ? renderState(gs) : `<div class="empty">读取失败</div>`;
  // Prefetch the next few steps so playback is smooth.
  for (let k = 1; k <= 3; k++) if (n + k <= run.timeline.length) stepData(run.summary.id, n + k);
}

function togglePlay() {
  if (state.playTimer) return stopPlay();
  $("#play").textContent = "⏸ 暂停";
  state.playTimer = setInterval(() => {
    if (state.step >= state.run.timeline.length) return stopPlay();
    setStep(state.step + 1);
  }, 700);
}
function stopPlay() {
  clearInterval(state.playTimer);
  state.playTimer = null;
  const b = $("#play");
  if (b) b.textContent = "▶ 播放";
}

// ---------- state rendering (shared by replay and live) ----------
function hpBar(cur, max, block = 0) {
  const pct = max ? Math.max(0, Math.min(100, (cur / max) * 100)) : 0;
  const bpct = max ? Math.min(100, (block / max) * 100) : 0;
  return `<div class="hpbar"><div class="fill" style="width:${pct}%"></div>${block ? `<div class="blk" style="width:${bpct}%"></div>` : ""}<div class="txt">${cur ?? "?"}/${max ?? "?"}${block ? ` 🛡${block}` : ""}</div></div>`;
}

function powersHtml(powers) {
  return (powers || []).map((p) => {
    const neg = BAD_POWERS.has(p.id) || ((p.id === "Strength" || p.id === "Dexterity") && p.amount < 0);
    const amt = p.amount === -1 && p.id !== "Strength" ? "" : ` ${p.amount}`;
    return `<span class="power ${neg ? "neg" : "pos"}" data-tip="${tipHtml(p.name, p.id, "")}">${esc(p.name)}${amt}</span>`;
  }).join("");
}

function intentHtml(m) {
  const i = m.intent || "";
  if (i.startsWith("ATTACK")) {
    const dmg = m.move_adjusted_damage > 0 ? m.move_adjusted_damage : "?";
    const hits = m.move_hits > 1 ? `×${m.move_hits}` : "";
    const extra = i === "ATTACK" ? "" : i.replace("ATTACK_", "+");
    return `<span class="intent atk">⚔ ${dmg}${hits} ${esc(extra)}</span>`;
  }
  if (i.includes("DEBUFF")) return `<span class="intent deb">☠ ${esc(i)}</span>`;
  if (i.includes("BUFF") || i.includes("DEFEND")) return `<span class="intent buf">✦ ${esc(i)}</span>`;
  return `<span class="intent">${esc(i || "—")}</span>`;
}

function cardHtml(c, letter) {
  const info = cardInfo(c);
  const cost = c.cost === -1 ? "X" : c.cost === -2 ? "" : c.cost;
  const cls = [c.type || "", c.upgrades ? "up" : "", c.playable === false ? "unplayable" : ""].join(" ");
  const sub = `${TYPE_NAME[c.type] || c.type || ""} · ${info.rarity}${c.ethereal ? " · 虚无" : ""}${c.exhausts ? " · 消耗" : ""}`;
  return `<div class="card ${cls}" data-tip="${tipHtml(`${c.name}${c.name !== info.english ? ` (${info.english})` : ""}`, sub, info.text)}">
    ${cost !== "" ? `<div class="cost">${esc(cost)}</div>` : ""}
    ${letter ? `<div class="letter">${letter}</div>` : ""}
    <div class="cname">${esc(c.name)}</div>
    <div class="ctext">${esc(info.text.length > 70 ? info.text.slice(0, 68) + "…" : info.text)}</div>
    <div class="ctype">${TYPE_NAME[c.type] || ""}</div>
  </div>`;
}

function relicsHtml(relics) {
  return (relics || []).map((r) => {
    const info = state.catalog.relics[r.id];
    const initial = (info?.name || r.id || "?").slice(0, 1);
    return `<div class="relic" data-tip="${tipHtml(`${r.name}${info && info.name !== r.name ? ` (${info.name})` : ""}`, info?.tier || "", info?.text || "")}">${esc(initial)}</div>`;
  }).join("");
}

function potionsHtml(potions) {
  return (potions || []).map((p) => {
    if (p.id === "Potion Slot") return `<div class="potion empty">·</div>`;
    const info = state.catalog.potions[p.id];
    return `<div class="potion" data-tip="${tipHtml(`${p.name}${info && info.name !== p.name ? ` (${info.name})` : ""}`, info?.rarity || "", info?.text || "")}">⚗</div>`;
  }).join("");
}

function renderState(gs) {
  const top = `
    <div class="state-top">
      ${hpBar(gs.current_hp, gs.max_hp, gs.combat?.player?.block || 0)}
      <span class="stat-pill"><span class="ico">💰</span>${gs.gold ?? "?"}</span>
      <span class="stat-pill"><span class="ico">🗼</span>F${gs.floor ?? "?"} · 第 ${gs.act ?? "?"} 幕</span>
      <span class="chip">${esc(ROOM_NAME[gs.room_type] || gs.room_type || "")}</span>
      <span class="chip">${esc(SCREEN_NAME[gs.screen_type] || gs.screen_type || "")}</span>
      ${gs.act_boss ? `<span class="chip">Boss：${esc(gs.act_boss)}</span>` : ""}
    </div>
    <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center">
      <div class="relics">${relicsHtml(gs.relics)}</div>
      <div class="potions">${potionsHtml(gs.potions)}</div>
    </div>`;
  let body = "";
  if (gs.combat && ["NONE", "HAND_SELECT", "GRID", "CARD_REWARD"].includes(gs.screen_type) && gs.combat.monsters) {
    const c = gs.combat;
    body = `
      <div class="battlefield">
        <div class="monsters">${c.monsters.map((m) => `
          <div class="monster ${m.is_gone || m.current_hp <= 0 ? "dead" : ""}">
            ${m.is_gone || m.current_hp <= 0 ? `<span class="intent">✝ 已倒下</span>` : intentHtml(m)}
            <div class="mname">${esc(m.name)}</div>
            ${hpBar(m.current_hp, m.max_hp, m.block)}
            <div class="powers">${powersHtml(m.powers)}</div>
          </div>`).join("")}
        </div>
        <div class="player-row">
          <div class="energy" title="能量">${c.player?.energy ?? "?"}</div>
          <div><div style="font-weight:700">回合 ${c.turn ?? "?"}</div><div class="piles">抽牌堆 ${c.draw} · 弃牌堆 ${c.discard} · 消耗 ${c.exhaust}</div></div>
          <div class="powers" style="justify-content:flex-start">${powersHtml(c.player?.powers)}</div>
        </div>
        <div class="hand">${c.hand.map((card, i) => cardHtml(card, String.fromCharCode(97 + i))).join("") || `<span class="muted">手牌为空</span>`}</div>
      </div>`;
    // HAND_SELECT picks from the hand already shown above.
    if (gs.screen_type === "GRID" || gs.screen_type === "CARD_REWARD") body += screenHtml(gs);
  } else {
    body = screenHtml(gs);
  }
  const deck = `<details style="margin-top:12px"><summary class="muted" style="cursor:pointer;font-weight:600">牌组 · ${gs.deck.length} 张</summary>
    <div class="hand">${gs.deck.map((c) => cardHtml(c)).join("")}</div></details>`;
  return top + body + deck;
}

function optionsList(items) {
  return `<div class="options">${items.map((t) => `<div class="memo">${t}</div>`).join("")}</div>`;
}

function screenHtml(gs) {
  const s = gs.screen_state || {};
  switch (gs.screen_type) {
    case "EVENT":
      return `<div class="battlefield"><div class="panel-title">事件 · ${esc(s.event_name || "")}</div>
        <div style="white-space:pre-wrap;color:var(--muted)">${esc((s.body_text || "").replace(/#[a-z]|~|@/g, ""))}</div>
        ${optionsList((s.options || []).map((o) => `${o.disabled ? "🔒 " : ""}${esc(o.text || o.label)}`))}</div>`;
    case "CARD_REWARD":
      return `<div class="battlefield"><div class="panel-title">选牌</div><div class="hand">${(s.cards || []).map((c) => cardHtml(c)).join("")}</div></div>`;
    case "GRID":
    case "HAND_SELECT":
      return `<div class="battlefield"><div class="panel-title">选择卡牌 ${s.num_cards ? `<span class="hint">${s.num_cards} 张</span>` : ""}</div><div class="hand">${(s.cards || s.hand || []).map((c) => cardHtml(c)).join("")}</div></div>`;
    case "COMBAT_REWARD":
      return `<div class="battlefield"><div class="panel-title">战利品</div>${optionsList((s.rewards || []).map((r) => esc(
        r.type === "GOLD" || r.type === "STOLEN_GOLD" ? `💰 ${r.gold} 金币` : r.type === "POTION" ? `⚗ ${r.potion?.name}` : r.type === "RELIC" ? `◆ ${r.relic?.name}` : r.type === "CARD" ? "🂠 卡牌奖励" : r.type)))}</div>`;
    case "SHOP_SCREEN":
      return `<div class="battlefield"><div class="panel-title">商店</div>
        <div class="hand">${(s.cards || []).map((c) => `<div>${cardHtml(c)}<div class="price">${c.price}g</div></div>`).join("")}</div>
        ${optionsList([...(s.relics || []).map((r) => `◆ ${esc(r.name)} — ${r.price}g`), ...(s.potions || []).map((p) => `⚗ ${esc(p.name)} — ${p.price}g`), s.purge_available ? `✂ 删牌 — ${s.purge_cost}g` : ""].filter(Boolean))}</div>`;
    case "REST":
      return `<div class="battlefield"><div class="panel-title">篝火</div>${optionsList((s.rest_options || []).map((o) => esc({ rest: "休息", smith: "锻造", lift: "举重", dig: "挖掘", recall: "回忆", toke: "吸烟", key: "钥匙" }[o] || o)))}</div>`;
    case "BOSS_REWARD":
      return `<div class="battlefield"><div class="panel-title">Boss 遗物</div><div class="relics">${relicsHtml(s.relics)}</div>${optionsList((s.relics || []).map((r) => esc(`${r.name}：${state.catalog.relics[r.id]?.text || ""}`)))}</div>`;
    case "MAP":
      return `<div class="battlefield"><div class="panel-title">选择下一层</div>${optionsList((s.next_nodes || []).map((n) => `${ROOM_ICON[n.symbol] || n.symbol} 第 ${n.x} 列`))}</div>`;
    case "GAME_OVER":
      return `<div class="battlefield gameover">
        <div class="go-title" style="color:${s.victory ? "var(--ok)" : "var(--bad)"}">${s.victory ? "登顶成功" : "攀登终结"}</div>
        <div class="go-score">最终分数 <b>${s.score ?? "?"}</b></div></div>`;
    default:
      return `<div class="battlefield muted">${esc(SCREEN_NAME[gs.screen_type] || gs.screen_type || "")}</div>`;
  }
}

// ---------- HP chart ----------
function renderChart() {
  const tl = state.run.timeline;
  const box = $("#chart");
  if (!tl.length) { box.innerHTML = `<div class="empty">无数据</div>`; return; }
  const W = 600, H = 190, P = { l: 30, r: 10, t: 12, b: 22 };
  const maxHp = Math.max(1, ...tl.map((p) => p.max_hp || 0));
  const x = (i) => P.l + (i / Math.max(1, tl.length - 1)) * (W - P.l - P.r);
  const y = (v) => P.t + (1 - (v || 0) / maxHp) * (H - P.t - P.b);
  const pts = tl.map((p, i) => `${x(i).toFixed(1)},${y(p.hp).toFixed(1)}`);
  const maxPts = tl.map((p, i) => `${x(i).toFixed(1)},${y(p.max_hp).toFixed(1)}`);
  let bands = "", labels = "", bosses = "";
  let start = 0;
  for (let i = 1; i <= tl.length; i++) {
    if (i === tl.length || tl[i].act !== tl[start].act) {
      if ((tl[start].act || 1) % 2 === 0) bands += `<rect class="act-band" x="${x(start)}" y="${P.t}" width="${x(i - 1) - x(start)}" height="${H - P.t - P.b}"/>`;
      labels += `<text x="${(x(start) + x(i - 1)) / 2}" y="${H - 6}" text-anchor="middle">第 ${tl[start].act ?? "?"} 幕</text>`;
      start = i;
    }
  }
  tl.forEach((p, i) => {
    if (p.room === "MonsterRoomBoss" && (i === 0 || tl[i - 1].room !== "MonsterRoomBoss"))
      bosses += `<g><circle class="boss" cx="${x(i)}" cy="${y(p.hp)}" r="5"/><text x="${x(i)}" y="${y(p.hp) - 9}" text-anchor="middle" class="boss-label">♛ ${p.hp}</text></g>`;
  });
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" id="chart-svg">
    <defs><linearGradient id="hpgrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#D2496A" stop-opacity=".22"/><stop offset="1" stop-color="#D2496A" stop-opacity="0"/></linearGradient></defs>
    ${bands}
    <line class="axis" x1="${P.l}" y1="${H - P.b}" x2="${W - P.r}" y2="${H - P.b}"/>
    <text x="4" y="${y(maxHp) + 4}">${maxHp}</text><text x="4" y="${y(maxHp / 2) + 4}">${Math.round(maxHp / 2)}</text>
    <polygon class="hp-area" points="${x(0)},${H - P.b} ${pts.join(" ")} ${x(tl.length - 1)},${H - P.b}"/>
    <polyline class="max-line" points="${maxPts.join(" ")}"/>
    <polyline class="hp-line" points="${pts.join(" ")}"/>
    ${bosses}${labels}
    <line class="cursor" id="chart-cursor" x1="0" y1="${P.t}" x2="0" y2="${H - P.b}"/>
  </svg>`;
  const svg = $("#chart-svg");
  svg.addEventListener("click", (ev) => {
    const r = svg.getBoundingClientRect();
    const fx = ((ev.clientX - r.left) / r.width) * W;
    const i = Math.round(((fx - P.l) / (W - P.l - P.r)) * (tl.length - 1));
    setStep(i + 1);
  });
  state.chartX = x;
  moveChartCursor();
}
function moveChartCursor() {
  const c = $("#chart-cursor");
  if (c && state.chartX) { const v = state.chartX(state.step - 1); c.setAttribute("x1", v); c.setAttribute("x2", v); }
}

// ---------- map ----------
function renderMap() {
  const run = state.run;
  const acts = Object.keys(run.maps).map(Number).sort();
  $("#act-tabs").innerHTML = acts.map((a) => `<button class="btn small ${a === state.act ? "active" : ""}" data-act="${a}">第 ${a} 幕</button>`).join("");
  $("#act-tabs").onclick = (ev) => { const b = ev.target.closest("[data-act]"); if (b) { state.act = +b.dataset.act; renderMap(); } };
  const nodes = run.maps[state.act];
  if (!nodes) { $("#map-view").innerHTML = `<div class="empty">这一幕没有地图数据</div>`; return; }
  const walked = (run.path[state.act] || []).map((n) => `${n.x},${n.y}`);
  const walkSet = new Set(walked);
  const walkEdges = new Set();
  for (let i = 1; i < walked.length; i++) walkEdges.add(`${walked[i - 1]}>${walked[i]}`);
  const maxY = Math.max(...nodes.map((n) => n.y));
  const W = 420, H = 560, px = (x) => 30 + x * ((W - 60) / 6), py = (y) => H - 50 - y * ((H - 100) / Math.max(1, maxY));
  let edges = "", circles = "";
  for (const n of nodes) {
    for (const c of n.children || []) {
      if (c.y > maxY) continue;
      const walk = walkEdges.has(`${n.x},${n.y}>${c.x},${c.y}`);
      edges += `<line class="edge ${walk ? "walk" : ""}" x1="${px(n.x)}" y1="${py(n.y)}" x2="${px(c.x)}" y2="${py(c.y)}"/>`;
    }
  }
  for (const n of nodes) {
    const key = `${n.x},${n.y}`;
    circles += `<g class="node ${n.symbol} ${walkSet.has(key) ? "walk" : ""}" data-node="${key}"><circle cx="${px(n.x)}" cy="${py(n.y)}" r="12"/><text x="${px(n.x)}" y="${py(n.y)}">${ROOM_ICON[n.symbol] || esc(n.symbol)}</text></g>`;
  }
  const boss = `<g class="node B"><circle cx="${W / 2}" cy="22" r="16" style="stroke:var(--bad);fill:var(--bad-soft)"/><text x="${W / 2}" y="22">♛</text></g>`;
  $("#map-view").innerHTML = `<svg viewBox="0 0 ${W} ${H}">${edges}${circles}${boss}</svg>`;
  highlightHere();
}
function highlightHere() {
  document.querySelectorAll("#map-view .node.here").forEach((n) => n.classList.remove("here"));
  const t = state.run?.timeline[state.step - 1];
  if (!t || t.act !== state.act) return;
  const y = (t.floor ?? 0) - (1 + 17 * ((t.act ?? 1) - 1));
  const hit = (state.run.path[state.act] || []).find((n) => n.y === y);
  if (hit) document.querySelector(`#map-view [data-node="${hit.x},${hit.y}"]`)?.classList.add("here");
}

// ---------- lore ----------
function md(text) {
  const lines = text.replace(/\r/g, "").split("\n");
  const out = [];
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  let i = 0, list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*\|/.test(line)) {
      closeList();
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const body = rows.filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r));
      out.push(`<table><thead><tr>${cells(body[0]).map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>${body.slice(1).map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { closeList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }
    const li = line.match(/^\s*([-*]|\d+\.)\s+(.*)/);
    if (li) {
      const kind = /\d/.test(li[1]) ? "ol" : "ul";
      if (list !== kind) { closeList(); out.push(`<${kind}>`); list = kind; }
      out.push(`<li>${inline(li[2])}</li>`);
      i++;
      continue;
    }
    closeList();
    if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    i++;
  }
  closeList();
  return out.join("\n");
}

async function loadLore() {
  $("#view-lore").innerHTML = `<div class="empty">展开卷轴中…</div>`;
  state.knowledge = await api("/api/knowledge");
  renderLore("lessons");
}

function renderLore(tab, sub) {
  const k = state.knowledge;
  const tabs = [["lessons", `经验 ${k.lessons.length}`], ["guides", `攻略 ${k.guides.length}`], ["patches", `评测补丁 ${k.patches.length}`], ["eval", "评测记录"]];
  let body = "";
  if (tab === "lessons") {
    body = `<div class="grid tips">${k.lessons.map((l, i) => `
      <div class="tip-card"><div class="tip-head"><b>经验 #${i + 1}</b><span title="${esc(l.run || "")}">${esc(runLabel(l.run))} · F${l.floor ?? "?"}</span></div><p>${esc(l.text)}</p></div>`).join("") || `<div class="empty">还没有经验</div>`}</div>`;
  } else if (tab === "guides") {
    const g = k.guides.find((x) => x.topic === sub) || k.guides[0];
    const [cur, hist] = g ? g.text.split(/\n## History\n/) : ["", ""];
    const versions = hist ? hist.split("\n").filter((l) => l.startsWith("- ")).length : 0;
    const stamp = (cur.match(/\(([^()]*seed[^()]*)\)\s*$/m) || [])[1] || "—";
    body = `<div class="grid guide-layout">
      <div class="panel toc"><div class="toc-title">攻略</div>${k.guides.map((x) => `<a data-guide="${esc(x.topic)}" class="${g && x.topic === g.topic ? "active" : ""}">${esc(x.topic)}</a>`).join("")}</div>
      ${g ? `<div class="article-layout">
        <div class="panel wiki">${md(cur)}${hist ? `<h2>历史版本</h2><div class="history">${md(hist)}</div>` : ""}</div>
        <aside class="infobox"><div class="ib-title">${esc(g.topic)}</div>
          <div class="ib-row"><span>文件</span><span>guides/${esc(g.topic)}.md</span></div>
          <div class="ib-row"><span>最近更新</span><span>${esc(stamp)}</span></div>
          <div class="ib-row"><span>历史版本</span><span>${versions}</span></div>
          <div class="ib-row"><span>作者</span><span>AI 玩家（guide 工具）</span></div></aside></div>` : `<div class="panel empty">还没有攻略</div>`}</div>`;
  } else if (tab === "patches") {
    const p = k.patches.find((x) => x.name === sub) || k.patches[0];
    body = `<div class="grid guide-layout">
      <div class="panel toc"><div class="toc-title">补丁</div>${k.patches.map((x) => `<a data-patch="${esc(x.name)}" class="${p && x.name === p.name ? "active" : ""}">${esc(x.name)}</a>`).join("")}</div>
      <div class="panel">${p ? `<div class="panel-title">${esc(p.name)}</div><p class="muted" style="margin:0 0 10px">评测局结束后 AI 写下的经验和攻略改动。绿色是新增，红色是删除。</p><div class="diff">${diffHtml(p.text)}</div>` : `<div class="empty">没有补丁</div>`}</div></div>`;
  } else {
    body = `<div class="panel wiki">${md(k.docs["eval-baseline.md"] || "没有评测记录")}</div>`;
  }
  $("#view-lore").innerHTML = `
    ${pageHead(["Knowledge"], "知识库", "Knowledge", "AI 跨局积累的经验、攻略，以及每轮评测的记录。")}
    <div class="lore-tabs">${tabs.map(([id, name]) => `<button class="btn ${id === tab ? "active" : ""}" data-lore="${id}">${name}</button>`).join("")}
      <button class="btn small" id="lore-reload" style="margin-left:auto">刷新</button></div>
    ${body}`;
  $("#view-lore").onclick = (ev) => {
    const t = ev.target.closest("[data-lore]");
    if (t) return renderLore(t.dataset.lore);
    const g = ev.target.closest("[data-guide]");
    if (g) return renderLore("guides", g.dataset.guide);
    const p = ev.target.closest("[data-patch]");
    if (p) return renderLore("patches", p.dataset.patch);
    if (ev.target.id === "lore-reload") { state.knowledge = null; loadLore(); }
  };
}

function diffHtml(text) {
  return text.split("\n").map((l) => {
    const cls = /^(diff |index |--- |\+\+\+ |@@)/.test(l) ? "hdr" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "";
    return `<span class="${cls}">${esc(l) || " "}</span>`;
  }).join("");
}

// ---------- compendium: every enemy met, grouped like the game's own (act, then normal / elite / boss) ----------
const ROOM_SHORT = { MonsterRoom: "普通", MonsterRoomElite: "精英", MonsterRoomBoss: "Boss", EventRoom: "事件" };
const INTENT_ZH = { ATTACK: "攻击", ATTACK_BUFF: "攻击+强化", ATTACK_DEBUFF: "攻击+削弱", ATTACK_DEFEND: "攻击+格挡" };
const KINDS = { boss: { name: "Boss", icon: "♛" }, elite: { name: "精英", icon: "☠" }, normal: { name: "普通", icon: "⚔" } };
const kindOf = (e) => (e.room === "MonsterRoomBoss" ? "boss" : e.room === "MonsterRoomElite" ? "elite" : "normal");
const firstAct = (e) => e.act || 0;

async function loadArchive(openId) {
  if (!state.archive) {
    $("#view-archive").innerHTML = `${pageHead(["Compendium"], "敌人图鉴", "Compendium", "正在整理所有对局的战斗记录…")}`;
    [state.archive] = await Promise.all([api("/api/bestiary"), state.knowledge ? null : api("/api/knowledge").then((k) => (state.knowledge = k))]);
    const order = { boss: 0, elite: 1, normal: 2 };
    state.archive.sort((a, b) => firstAct(a) - firstAct(b) || order[kindOf(a)] - order[kindOf(b)] || b.encounters - a.encounters);
  }
  renderArchive(state.archiveFilter || {}, openId ? decodeURIComponent(openId) : null);
}

function renderArchive(filter = state.archiveFilter || {}, openId = null) {
  state.archiveFilter = filter;
  const list = state.archive.filter((e) => (!filter.act || firstAct(e) === filter.act) && (!filter.kind || kindOf(e) === filter.kind));
  const btn = (key, val, label) => `<button class="btn small ${(filter[key] || 0) === val ? "active" : ""}" data-f="${key}" data-v="${val}">${label}</button>`;
  const acts = [...new Set(list.map(firstAct))].sort();
  $("#view-archive").innerHTML = `
    ${pageHead(["Compendium"], "敌人图鉴", "Compendium", "AI 在所有对局里遇到过的敌人，按幕和房间分类。数据来自实际战斗记录：遭遇次数、平均损失的生命、造成的阵亡。")}
    <div class="filters-row">
      <span class="muted">幕</span>${btn("act", 0, "全部")}${[1, 2, 3].map((a) => btn("act", a, `第 ${a} 幕`)).join("")}
      <span class="muted" style="margin-left:14px">房间</span>${btn("kind", 0, "全部")}${Object.entries(KINDS).map(([k, v]) => btn("kind", k, `${v.icon} ${v.name}`)).join("")}
    </div>
    <div id="entry-detail"></div>
    ${acts.map((a) => `
      <h2 class="group-title">第 ${a || "?"} 幕</h2>
      <div class="grid archive-grid">${list.filter((e) => firstAct(e) === a).map(entryCard).join("")}</div>`).join("") || `<div class="empty">没有符合条件的敌人</div>`}`;
  $("#view-archive").onclick = (ev) => {
    const f = ev.target.closest("[data-f]");
    if (f) return renderArchive({ ...filter, [f.dataset.f]: isNaN(+f.dataset.v) ? f.dataset.v : +f.dataset.v });
    const c = ev.target.closest("[data-entry]");
    if (c) return openEntry(c.dataset.entry);
    if (ev.target.closest("[data-close]")) $("#entry-detail").innerHTML = "";
    const r = ev.target.closest("[data-goto]");
    if (r) { openRun(r.dataset.goto); show("replay"); }
  };
  if (openId) openEntry(openId);
}

const entryName = (e) => e.names[e.names.length - 1] || e.id;

function entryCard(e) {
  const kind = kindOf(e);
  return `<article class="entry k-${kind}" data-entry="${esc(e.id)}">
    <div class="entry-kind"><span>${KINDS[kind].icon}</span><small>${KINDS[kind].name}</small></div>
    <div class="entry-body">
      <div class="entry-name">${esc(entryName(e))}</div>
      <div class="entry-id">${esc(e.id)} · 生命 ${e.max_hp}</div>
      <div class="entry-meta">
        <span>遭遇 <b>${e.encounters}</b></span>
        <span>平均损失 <b>${e.avg_pct}%</b></span>
        ${e.deaths ? `<span class="dead-count">阵亡 <b>${e.deaths}</b></span>` : ""}
      </div>
    </div>
  </article>`;
}

function relatedLessons(e) {
  const k = state.knowledge;
  if (!k) return [];
  const spaced = e.id.replace(/([a-z])([A-Z])/g, "$1 $2");
  const keys = [e.id, spaced, spaced.replace(/^The /, ""), ...e.names].filter((s) => s && s.length > 2).map((s) => s.toLowerCase());
  return k.lessons.filter((l) => keys.some((key) => l.text.toLowerCase().includes(key)));
}

function openEntry(id) {
  const e = state.archive.find((x) => x.id === id);
  if (!e) return;
  const kind = kindOf(e);
  const lessons = relatedLessons(e);
  const stats = [["遭遇次数", e.encounters], ["涉及对局", e.runs], ["最大生命", e.max_hp], ["平均回合", e.avg_turns],
    ["平均损失", `${e.avg_loss} (${e.avg_pct}%)`], ["单场最多", e.worst], ["造成阵亡", e.deaths]];
  $("#entry-detail").innerHTML = `
    <div class="entry-sheet panel k-${kind}" style="margin:0 0 26px">
      <div class="sheet-head">
        <div class="sheet-kind">${KINDS[kind].icon}</div>
        <div class="sheet-title">
          <div class="crumbs">Compendium / ${esc(e.id)}</div>
          <h2>${esc(entryName(e))}</h2>
          <div class="muted">${e.names.length > 1 ? `别名：${esc(e.names.join("、"))} · ` : ""}出现于第 ${e.acts.join("、")} 幕 · ${e.rooms.map((r) => ROOM_SHORT[r] || r).join(" / ")}</div>
        </div>
        <button class="btn small" data-close>关闭</button>
      </div>
      <div class="sheet-grid">
        <section>
          <h3>战斗数据</h3>
          <dl class="kv">${stats.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
        </section>
        <section>
          <h3>意图与能力</h3>
          <div class="sub-h">见过的最大攻击</div>
          <ul class="plain">${e.hits.filter((h) => h.intent.startsWith("ATTACK")).slice(0, 5).map((h) =>
            `<li>${esc(INTENT_ZH[h.intent] || h.intent)} <code>${h.damage}${h.times > 1 ? ` × ${h.times}` : ""}</code></li>`).join("") || "<li class='muted'>没有记录到攻击</li>"}</ul>
          <div class="sub-h">其他意图</div>
          <div>${e.hits.filter((h) => !h.intent.startsWith("ATTACK")).map((h) => `<span class="chip">${esc(h.intent)}</span>`).join("") || "<span class='muted'>—</span>"}</div>
          <div class="sub-h">身上出现过的能力</div>
          <div>${e.powers.map((p) => `<span class="chip">${esc(p)}</span>`).join("") || "<span class='muted'>—</span>"}</div>
        </section>
        <section>
          <h3>相关经验</h3>
          ${lessons.length ? lessons.map((l) => `<p class="lesson-quote">${esc(l.text)}</p>`).join("") : `<p class="muted">经验库里还没有提到它。</p>`}
        </section>
      </div>
      <section class="sheet-log">
        <h3>遭遇记录 <span class="muted" style="text-transform:none;letter-spacing:0">点一行打开那局的回放</span></h3>
        <div class="table-wrap"><table class="data">
          <thead><tr><th>对局</th><th>楼层</th><th>房间</th><th>同场</th><th>回合</th><th>损失</th><th>结果</th></tr></thead>
          <tbody>${e.fights.map((f) => `<tr data-goto="${esc(f.run)}" class="${f.died ? "dead" : ""}">
            <td>${esc(runLabel(f.run))}</td><td>F${f.floor}</td><td class="txt">${ROOM_SHORT[f.room] || f.room}</td>
            <td class="txt">${esc(f.with.join("、") || "—")}</td><td>${f.turns}</td><td>${f.loss} <span class="muted">(${f.pct}%)</span></td>
            <td class="txt">${f.died ? `<span class="badge dead">阵亡</span>` : `<span class="badge win">存活</span>`}</td></tr>`).join("")}</tbody></table></div>
      </section>
    </div>`;
  $("#entry-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}
// ---------- live ----------
function startLive() {
  if (!$("#view-live").innerHTML) $("#view-live").innerHTML = `<div class="empty">连接尖塔中…</div>`;
  pollLive();
  state.live.timer = setInterval(pollLive, 3000);
}
function stopLive() {
  clearInterval(state.live.timer);
  state.live.timer = null;
}
async function pollLive() {
  let info;
  try { info = await api("/api/live"); } catch { return; }
  if (!info.run) { $("#view-live").innerHTML = `<div class="empty">还没有任何对局</div>`; return; }
  if (info.run === state.live.run && info.steps === state.live.steps) { $("#live-age") && ($("#live-age").textContent = ageText(info.mtime)); return; }
  state.live.run = info.run;
  state.live.steps = info.steps;
  const raw = info.steps ? await api(`/api/run/${encodeURIComponent(info.run)}/step/${info.steps}`).catch(() => null) : null;
  if (raw) setTowerFloor(raw.floor, `F${raw.floor ?? 0}`, true);
  const summary = state.runs.find((r) => r.id === info.run);
  const fresh = Date.now() / 1000 - info.mtime < 120;
  $("#view-live").innerHTML = `
    ${pageHead(["Live"], "实时观战", "Live", "每 3 秒读取一次最新的对局记录。")}
    <div class="live-banner">
      <span class="status" style="color:${fresh ? "var(--star)" : "var(--muted)"}">${fresh ? `<span class="live-dot"></span>正在攀登` : "暂无动静"}</span>
      <span class="chip">${esc(info.run)}</span>
      <span class="chip">第 ${info.steps} 步</span>
      <span class="chip" id="live-age">${ageText(info.mtime)}</span>
      <button class="btn small primary" id="live-open">在回放中打开</button>
    </div>
    <div class="grid replay-grid">
      <div class="panel">${raw ? renderState(raw) : `<div class="empty">等待游戏状态…</div>`}</div>
      <div class="panel"><div class="panel-title">最近行动</div><div class="log-list">${info.recent.slice().reverse().map(logItem).join("")}</div></div>
    </div>`;
  $("#live-open").onclick = async () => { await refreshRuns(); await openRun(info.run); show("replay"); };
  if (!summary) refreshRuns();
}
function ageText(mtime) {
  const s = Math.round(Date.now() / 1000 - mtime);
  return s < 60 ? `${s} 秒前更新` : s < 3600 ? `${Math.round(s / 60)} 分钟前更新` : `${Math.round(s / 3600)} 小时前更新`;
}

// ---------- boot ----------
async function refreshRuns() {
  state.runs = await api("/api/runs");
  renderHall();
}

(async function boot() {
  try {
    [state.catalog] = await Promise.all([api("/api/catalog"), refreshRuns()]);
  } catch (e) {
    $("#view-hall").innerHTML = `<div class="empty">无法连接面板服务：${esc(e.message)}</div>`;
    return;
  }
  const view = location.hash.slice(1).split("/")[0];
  if (["hall", "replay", "archive", "lore", "live"].includes(view)) show(view);
})();
