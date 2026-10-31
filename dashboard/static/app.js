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
const MAP_ICON = { M: "monster", E: "elite", R: "rest", $: "shop", T: "chest", "?": "event" };
const BOSS_ICON = [["guardian", "guardian"], ["hexaghost", "hexaghost"], ["slime", "slime"], ["collector", "collector"],
  ["automaton", "automaton"], ["champ", "champ"], ["awakened", "awakened"], ["time eater", "timeeater"], ["donu", "donu"],
  ["deca", "donu"], ["heart", "heart"]];
const bossIcon = (name) => (BOSS_ICON.find(([k]) => String(name || "").toLowerCase().includes(k)) || [])[1];
const BAD_POWERS = new Set(["Vulnerable", "Weakened", "Frail", "Poison", "Entangled", "No Draw", "Hex", "Constricted", "Shackled", "Draw Reduction", "Confusion"]);

const state = {
  runs: [],
  catalog: { cards: {}, relics: {}, potions: {} },
  game: { available: false, relics: {}, cards: {} },  // which game image belongs to each relic and card
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
    <div class="crumbs">${["尖塔战报", ...crumbs].map((c) => `<span>${esc(c)}</span>`).join("")}</div>
    <h1 class="section-title">${esc(title)}${small ? `<small>${esc(small)}</small>` : ""}</h1>
    ${desc ? `<p class="page-desc">${esc(desc)}</p>` : ""}
  </div>`;

// ---------- game art ----------
// Images come from the local game install through the dashboard server (/game/<path inside desktop-1.0.jar>).
const G = (path) => `/game/${path}`;
const gimg = (path, cls = "gico", alt = "") => `<img class="${cls}" src="${G(path)}" alt="${esc(alt)}" onerror="this.remove()">`;

// libGDX texture atlas -> {region: {page, x, y, w, h, ow, oh, ox, oy}}
function parseAtlas(text) {
  const regions = {};
  let page = null, cur = null;
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) { page = null; continue; }
    if (!line.startsWith(" ") && !line.includes(":")) {
      if (page === null) page = line.trim();
      else regions[line.trim()] = cur = { page };
      continue;
    }
    const m = /^\s+(xy|size|orig|offset):\s*(-?\d+),\s*(-?\d+)/.exec(line);
    if (cur && m) {
      const [k1, k2] = { xy: ["x", "y"], size: ["w", "h"], orig: ["ow", "oh"], offset: ["ox", "oy"] }[m[1]];
      cur[k1] = +m[2]; cur[k2] = +m[3];
    }
  }
  return regions;
}

// ---------- the spire behind the page ----------
// The title screen's own spire (title/title.atlas): sky, the tower in two halves, its glowing windows and drifting
// clouds. Scrolling down the page climbs it, from the ground to the burning cap.
(async function spire() {
  const box = $(".spire-bg");
  let atlas;
  try {
    const res = await fetch(G("title/title.atlas"));
    if (!res.ok) return;
    atlas = parseAtlas(await res.text());
  } catch { return; }
  const H = 2280; // mg3Top (1140) over mg3Bot (1140)
  // A region drawn inside its original frame, the frame's top at frameTop (atlas offsets count from the bottom).
  const piece = (name, frameTop, cls = "") => {
    const r = atlas[name];
    if (!r) return "";
    const top = frameTop + r.oh - r.oy - r.h;
    return `<div class="${cls}" style="left:${r.ox}px;top:${top}px;width:${r.w}px;height:${r.h}px;background-image:url(${G("title/" + r.page)});background-position:-${r.x}px -${r.y}px"></div>`;
  };
  const sky = atlas["jpg/sky"];
  box.innerHTML = `<div class="sky"></div>
    <div class="stage" style="height:${H}px">
      ${piece("mg3Top", 0)}${piece("mg3Bot", 1140)}
      ${piece("mg3TopGlow1", 0, "glow")}${piece("mg3TopGlow2", 0, "glow b")}${piece("mg3BotGlow", 1140, "glow")}
      ${piece("topCloud2", -40, "cloud")}${piece("topCloud5", -40, "cloud slow")}${piece("midCloud10", 120, "cloud slow")}
      ${piece("mg2", H - 848)}${piece("mg1", H - 332)}${piece("fg", H - 626)}
    </div>`;
  // The sky sits in a corner of its page; crop it like the other regions and scale it to cover the window.
  if (sky) box.querySelector(".sky").innerHTML = `<div style="position:absolute;left:0;top:0;background:url(${G("title/" + sky.page)}) -${sky.x}px -${sky.y}px no-repeat;transform-origin:0 0"></div>`;
  const stage = box.querySelector(".stage");
  const skyImg = box.querySelector(".sky > div");
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  function place() {
    const vw = innerWidth, vh = innerHeight;
    // Wide enough to cover the window, tall enough that there is some tower to climb.
    const k = Math.max(vw / 1920, (vh * 1.25) / H);
    const room = Math.max(1, document.documentElement.scrollHeight - vh);
    const p = still ? 0 : Math.min(1, scrollY / room);
    const dx = Math.min(0, (vw - 1920 * k) * 0.2);
    stage.style.transform = `translate(${dx}px, ${-(H * k - vh) * (1 - p)}px) scale(${k})`;
    if (skyImg && sky) {
      const ks = Math.max(vw / sky.w, vh / sky.h);
      skyImg.style.width = `${sky.w}px`;
      skyImg.style.height = `${sky.h}px`;
      skyImg.style.transform = `scale(${ks})`;
    }
  }
  let queued = false;
  const later = () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; place(); }); } };
  addEventListener("scroll", later, { passive: true });
  addEventListener("resize", later);
  new ResizeObserver(later).observe(document.body);
  place();
})();

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

// ---------- navigation ----------
function show(view) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view !== "live") stopLive();
  if (view === "live") startLive();
  if (view === "lore" && !state.knowledge) loadLore();
  if (view === "replay" && !state.run && state.runs.length) openRun(defaultRun().id, false);
  location.hash = view;
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
  root.innerHTML = `
    ${pageHead(["对局"], "对局记录", "", "AI 铁甲战士的每一次攀登。点击一行查看逐步回放。")}
    <div class="grid stats">
      ${[["攀登次数", real.length, "", "images/ui/topPanel/map.png"], ["登顶", wins, "gold", "images/ui/map/boss/heart.png"],
        ["最高楼层", best, "", "images/ui/topPanel/floor.png"], ["平均楼层", avg, "", "images/ui/topPanel/floor.png"],
        ["最高分", bestScore || "—", "gold", "images/ui/topPanel/ascension.png"]]
        .map(([l, n, c, icon]) => `<div class="panel stat">${gimg(icon)}<div><div class="lbl">${l}</div><div class="num ${c}">${n}</div></div></div>`).join("")}
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
      <td>${duration(r.started, r.ended)}</td>
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
    ${pageHead(["回放", s.seed], `${s.seed} 回放`, `A${s.ascension ?? "?"} · ${s.result}`)}
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
  $("#step-label").textContent = `第 ${n} 步 · F${t.floor ?? "?"} · ${SCREEN_NAME[t.screen] || t.screen || ""}`;
  document.querySelectorAll("#log-list .log-item").forEach((el) => el.classList.toggle("cur", +el.dataset.step === n));
  const cur = $(`#log-list .log-item[data-step="${n}"]`);
  if (cur) cur.scrollIntoView({ block: "nearest" });
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

// The game's intent icons (images/ui/intent); plain attacks grow with the damage like in the game.
const INTENT_ICON = { ATTACK_BUFF: "attackBuff", ATTACK_DEBUFF: "attackDebuff", ATTACK_DEFEND: "attackDefend", BUFF: "buff1",
  DEBUFF: "debuff1", STRONG_DEBUFF: "debuff2", DEFEND: "defend", DEFEND_BUFF: "defendBuff", DEFEND_DEBUFF: "defend",
  ESCAPE: "escape", MAGIC: "magic", SLEEP: "sleep", STUN: "stun", UNKNOWN: "unknown" };
const INTENT_NAME = { ATTACK: "攻击", ATTACK_BUFF: "攻击+强化", ATTACK_DEBUFF: "攻击+减益", ATTACK_DEFEND: "攻击+格挡", BUFF: "强化",
  DEBUFF: "减益", STRONG_DEBUFF: "强力减益", DEFEND: "格挡", DEFEND_BUFF: "格挡+强化", DEFEND_DEBUFF: "格挡+减益", ESCAPE: "逃跑",
  MAGIC: "魔法", SLEEP: "睡眠", STUN: "眩晕", UNKNOWN: "未知" };
function intentHtml(m) {
  const i = m.intent || "";
  const name = INTENT_NAME[i] || i || "—";
  if (i.startsWith("ATTACK")) {
    const dmg = m.move_adjusted_damage > 0 ? m.move_adjusted_damage : "?";
    const total = (m.move_adjusted_damage || 0) * Math.max(1, m.move_hits || 1);
    const tier = [5, 10, 15, 20, 25, 30].findIndex((t) => total < t) + 1 || 7;
    const icon = i === "ATTACK" ? `attack/attack_intent_${tier}` : INTENT_ICON[i];
    const hits = m.move_hits > 1 ? `×${m.move_hits}` : "";
    return `<span class="intent atk" title="${esc(name)}">${gimg(`images/ui/intent/${icon}.png`)}${dmg}${hits}</span>`;
  }
  const cls = i.includes("DEBUFF") ? "deb" : i.includes("BUFF") || i.includes("DEFEND") ? "buf" : "";
  const icon = INTENT_ICON[i];
  return `<span class="intent ${cls}">${icon ? gimg(`images/ui/intent/${icon}.png`) : ""}${esc(name)}</span>`;
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
    ${cardArt(c.id)}
    <div class="ctext">${esc(info.text.length > 70 ? info.text.slice(0, 68) + "…" : info.text)}</div>
    <div class="ctype">${TYPE_NAME[c.type] || ""}</div>
  </div>`;
}

// The card's portrait from cards/cards.atlas, scaled to the tile's 100px width.
function cardArt(id) {
  const r = state.game.cards?.[id];
  if (!r) return "";
  const k = 100 / r.w;
  return `<div class="art" style="background-image:url(${G(r.page)});background-size:${2048 * k}px;background-position:-${r.x * k}px -${r.y * k}px"></div>`;
}

function relicsHtml(relics) {
  return (relics || []).map((r) => {
    const info = state.catalog.relics[r.id];
    const tip = tipHtml(`${r.name}${info && info.name !== r.name ? ` (${info.name})` : ""}`, info?.tier || "", info?.text || "");
    const img = state.game.relics?.[r.id];
    if (img) return `<div class="relic art" data-tip="${tip}"><img src="${G(img)}" alt="${esc(r.name)}"></div>`;
    const initial = (info?.name || r.id || "?").slice(0, 1);
    return `<div class="relic" data-tip="${tip}">${esc(initial)}</div>`;
  }).join("");
}

// The game tints white liquid/hybrid/spots layers per PotionColor in code; these are close stand-ins for those tints.
const POTION_TINT = {
  POISON: ["#4bd13b", "#2a7f1f", "#b6ff7a"], BLUE: ["#3d7fe0", "#1c3f8f", "#9fd0ff"], FIRE: ["#ff5a1f", "#b8200f", "#ffd25a"],
  GREEN: ["#3fbf5a", "#1e6e33", "#a8f0b0"], EXPLOSIVE: ["#ff9a1f", "#c8481a", "#fff07a"], WEAK: ["#9a6ad6", "#4d2f80", "#d9c2ff"],
  FEAR: ["#3b2a52", "#1b1026", "#a36ad6"], STRENGTH: ["#d8302a", "#7a0f0f", "#ff9c8a"], WHITE: ["#e8e8e8", "#a9a9b0", "#ffffff"],
  FAIRY: ["#ff8fd1", "#c24c9a", "#fff0fa"], ANCIENT: ["#e8c060", "#8a6420", "#fff2b0"], ELIXIR: ["#f0c040", "#9a6a10", "#fff3b5"],
  ENERGY: ["#ffd23a", "#e08a10", "#fff7c0"], SWIFT: ["#36c7c0", "#157a78", "#b5fff7"], FRUIT: ["#ff7a4a", "#c03a2a", "#ffe08a"],
  SNECKO: ["#8fb02a", "#4a6a10", "#e2f07a"], SMOKE: ["#5d5d68", "#2a2a33", "#a8a8b5"], STEROID: ["#c41e3a", "#5a0a18", "#ff7a8a"],
  SKILL: ["#3fbf5a", "#1e6e33", "#a8f0b0"], ATTACK: ["#d8302a", "#7a0f0f", "#ff9c8a"], POWER: ["#3d7fe0", "#1c3f8f", "#9fd0ff"],
  NONE: ["#9aa0a8", "#5d636b", "#d5d9de"],
};

function potionArt(id) {
  const p = state.game.potions?.[id];
  if (!p) return "";
  const [liquid, hybrid, spots] = POTION_TINT[p.color] || POTION_TINT.NONE;
  const tinted = (layer, color) => (p[layer] ? `<i style="background:${color};-webkit-mask-image:url(${G(p[layer])});mask-image:url(${G(p[layer])})"></i>` : "");
  return `<div class="pot-art">${tinted("liquid", liquid)}${tinted("hybrid", hybrid)}${tinted("spots", spots)}${p.glass ? `<img src="${G(p.glass)}" alt="">` : ""}</div>`;
}

function potionsHtml(potions) {
  return (potions || []).map((p) => {
    if (p.id === "Potion Slot") return `<div class="potion empty">·</div>`;
    const info = state.catalog.potions[p.id];
    const art = potionArt(p.id);
    return `<div class="potion ${art ? "art" : ""}" data-tip="${tipHtml(`${p.name}${info && info.name !== p.name ? ` (${info.name})` : ""}`, info?.rarity || "", info?.text || "")}">${art || "⚗"}</div>`;
  }).join("");
}

function renderState(gs) {
  const top = `
    <div class="state-top">
      ${hpBar(gs.current_hp, gs.max_hp, gs.combat?.player?.block || 0)}
      <span class="stat-pill">${gimg("images/ui/topPanel/panelGoldBag.png")}${gs.gold ?? "?"}</span>
      <span class="stat-pill">${gimg("images/ui/topPanel/floor.png")}F${gs.floor ?? "?"} · 第 ${gs.act ?? "?"} 幕</span>
      ${gs.ascension_level ? `<span class="stat-pill">${gimg("images/ui/topPanel/ascension.png")}${gs.ascension_level}</span>` : ""}
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
      return `<div class="battlefield"><div class="panel-title">选择下一层</div>${optionsList((s.next_nodes || []).map((n) => `${MAP_ICON[n.symbol] && state.game.available ? gimg(`images/ui/map/${MAP_ICON[n.symbol]}.png`, "gico room") : ROOM_ICON[n.symbol] || n.symbol} 第 ${n.x} 列`))}</div>`;
    case "GAME_OVER":
      return `<div class="battlefield gameover">
        <div class="go-title" style="color:${s.victory ? "var(--gold)" : "#ff8a76"}">${s.victory ? "登顶成功" : "攀登终结"}</div>
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
      bosses += `<g><circle class="boss" cx="${x(i)}" cy="${y(p.hp)}" r="5"/><text x="${x(i)}" y="${y(p.hp) - 9}" text-anchor="middle" fill="#f3d58c">♛ ${p.hp}</text></g>`;
  });
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" id="chart-svg">
    <defs><linearGradient id="hpgrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="rgba(255,90,67,.45)"/><stop offset="1" stop-color="rgba(255,90,67,0)"/></linearGradient></defs>
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
// Drawn on the game's own parchment with its room icons; the walked path is inked over it.
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
  const W = 420, H = 820, top = 175, S = 40;
  const px = (x) => 50 + x * ((W - 100) / 6), py = (y) => H - 50 - y * ((H - 50 - top) / Math.max(1, maxY));
  let edges = "", icons = "";
  for (const n of nodes) {
    for (const c of n.children || []) {
      if (c.y > maxY) continue;
      const walk = walkEdges.has(`${n.x},${n.y}>${c.x},${c.y}`);
      edges += `<line class="edge ${walk ? "walk" : ""}" x1="${px(n.x)}" y1="${py(n.y)}" x2="${px(c.x)}" y2="${py(c.y)}"/>`;
    }
  }
  for (const n of nodes) {
    const key = `${n.x},${n.y}`, x = px(n.x), y = py(n.y), icon = MAP_ICON[n.symbol];
    const mark = icon && state.game.available
      ? `<image href="${G(`images/ui/map/${icon}.png`)}" x="${x - S / 2}" y="${y - S / 2}" width="${S}" height="${S}"/>`
      : `<text x="${x}" y="${y}">${ROOM_ICON[n.symbol] || esc(n.symbol)}</text>`;
    icons += `<g class="node ${n.symbol} ${walkSet.has(key) ? "walk" : ""}" data-node="${key}"><circle class="ring" cx="${x}" cy="${y}" r="${S / 2 + 2}"/>${mark}</g>`;
  }
  const bossName = run.bosses?.[state.act];
  const bk = bossIcon(bossName);
  const boss = bk && state.game.available
    ? `<g class="boss"><image href="${G(`images/ui/map/boss/${bk}.png`)}" x="${W / 2 - 70}" y="8" width="140" height="140"/></g>`
    : `<text x="${W / 2}" y="80" style="font-size:44px">♛</text>`;
  const paper = state.game.available
    ? `<div class="paper">${["mapTop", "mapMid", "mapBot"].map((p) => `<img src="${G(`images/ui/map/${p}.png`)}" alt="">`).join("")}</div>` : "";
  $("#map-view").innerHTML = `<div class="mapsheet ${paper ? "" : "plain"}">${paper}<svg viewBox="0 0 ${W} ${H}">${boss}
    ${bossName ? `<text class="boss-name" x="${W / 2}" y="${top - 8}">${esc(bossName)}</text>` : ""}${edges}${icons}</svg></div>`;
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
    ${pageHead(["知识库"], "知识库", "", "AI 跨局积累的经验、攻略，以及每轮评测的记录。")}
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
  const summary = state.runs.find((r) => r.id === info.run);
  const fresh = Date.now() / 1000 - info.mtime < 120;
  $("#view-live").innerHTML = `
    ${pageHead(["实时"], "实时观战", "", "每 3 秒读取一次最新的对局记录。")}
    <div class="live-banner">
      <span class="status" style="color:${fresh ? "#ff8a76" : "var(--muted)"}">${fresh ? `<span class="live-dot"></span>正在攀登` : "暂无动静"}</span>
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
    state.game = await api("/api/game").catch(() => state.game);
  } catch (e) {
    $("#view-hall").innerHTML = `<div class="empty">无法连接面板服务：${esc(e.message)}</div>`;
    return;
  }
  const view = location.hash.slice(1);
  if (["hall", "replay", "lore", "live"].includes(view)) show(view);
})();
