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

// ---------- embers ----------
(function embers() {
  const box = $(".embers");
  for (let i = 0; i < 28; i++) {
    const e = document.createElement("i");
    e.style.left = `${Math.random() * 100}%`;
    e.style.animationDuration = `${9 + Math.random() * 14}s`;
    e.style.animationDelay = `${-Math.random() * 20}s`;
    e.style.setProperty("--drift", `${(Math.random() - 0.5) * 160}px`);
    e.style.transform = `scale(${0.5 + Math.random()})`;
    box.appendChild(e);
  }
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
    <h1 class="section-title">战报大厅<small>HALL OF RUNS</small></h1>
    <div class="grid stats">
      ${[["攀登次数", real.length], ["登顶", wins], ["最高楼层", best], ["平均楼层", avg], ["最高分", bestScore || "—"]]
        .map(([l, n]) => `<div class="panel stat"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("")}
    </div>
    <div class="filters">
      <input type="search" id="run-search" placeholder="搜索种子 / 结果 / 日期…">
      <label><input type="checkbox" id="hide-tests" ${state.hideTests ? "checked" : ""}> 隐藏测试局</label>
      <span class="muted">共 ${runs.length} 局</span>
    </div>
    <div class="grid runs" id="run-grid"></div>`;
  const grid = $("#run-grid");
  const paint = (q) => {
    const list = runs.filter((r) => !q || `${r.seed} ${r.result} ${r.started} ${r.id}`.toLowerCase().includes(q.toLowerCase()));
    grid.innerHTML = list.map(runCard).join("") || `<div class="empty">没有符合条件的对局</div>`;
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
  const badge = r.result === "胜利" ? `<span class="badge win">♛ 登顶</span>`
    : r.result === "阵亡" ? `<span class="badge dead">☠ 阵亡</span>` : `<span class="badge going">⏳ 进行中</span>`;
  const mem = r.memory === true ? `<span class="badge mem">记忆 开</span>` : r.memory === false ? `<span class="badge nomem">记忆 关</span>` : "";
  const pct = Math.min(100, ((r.floor || 0) / 55) * 100);
  return `
    <article class="panel run-card ${cls}" data-run="${esc(r.id)}">
      <div class="run-head">
        <div>
          <div class="run-seed">${esc(r.seed)}</div>
          <div class="run-meta">${esc(fmtDate(r.started))} · ${esc(r.class || "IRONCLAD")} · 进阶 ${r.ascension ?? "?"}</div>
        </div>
        <div style="text-align:right">${badge}<div style="margin-top:4px">${mem}</div></div>
      </div>
      <div class="run-body">
        <div class="big-floor"><div class="n">${r.floor || 0}</div><div class="l">楼层</div></div>
        <div class="climb">
          <div class="climb-bar"><div class="climb-fill" style="width:${pct}%"></div></div>
          <div class="climb-marks"><span style="left:0%">0</span><span style="left:${(17 / 55) * 100}%">幕二</span><span style="left:${(34 / 55) * 100}%">幕三</span><span style="left:${(51 / 55) * 100}%">心脏</span></div>
        </div>
      </div>
      <div class="run-foot">
        <span>分数 <b>${r.score ?? "—"}</b></span>
        <span>血量 <b>${r.hp ?? "?"}/${r.max_hp ?? "?"}</b></span>
        <span>金币 <b>${r.gold ?? "?"}</b></span>
        <span>步数 <b>${r.steps}</b></span>
        <span>用时 <b>${duration(r.started, r.ended)}</b></span>
        ${r.resumed ? `<span class="chip">中途续局</span>` : ""}
      </div>
    </article>`;
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
    <h1 class="section-title">对局回放<small>RUN REPLAY</small></h1>
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
            <button class="btn small" id="play">▶ 播放</button>
            <button class="btn small" id="next">▶</button>
            <input type="range" id="step-range" min="1" max="${Math.max(1, run.timeline.length)}" value="1">
            <span class="step-label" id="step-label"></span>
          </div>
          <div id="state-view"></div>
        </div>
        <div class="panel map">
          <div class="panel-title">🗺 攀登路线</div>
          <div class="act-tabs" id="act-tabs"></div>
          <div id="map-view"></div>
        </div>
      </div>
      <div class="grid">
        <div class="panel chart">
          <div class="panel-title">❤ 生命曲线 <span class="muted" style="font-size:12px;font-weight:400">点击跳转</span></div>
          <div id="chart"></div>
        </div>
        ${memo.plan || memo.route || (memo.notes || []).length ? `
        <div class="panel">
          <div class="panel-title">✒ 本局笔记</div>
          ${memo.plan ? `<div class="memo"><b>构筑计划</b>（F${memo.plan.floor}）\n${esc(memo.plan.text)}</div>` : ""}
          ${memo.route ? `<div class="memo"><b>路线</b>（F${memo.route.floor}）\n${esc(memo.route.text)}</div>` : ""}
          ${(memo.notes || []).map((n) => `<div class="memo">${esc(n.text || n)}</div>`).join("")}
        </div>` : ""}
        <div class="panel">
          <div class="panel-title">📜 行动日志</div>
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
  const deck = `<details style="margin-top:12px"><summary class="muted" style="cursor:pointer">🂠 牌组（${gs.deck.length} 张）</summary>
    <div class="hand">${gs.deck.map((c) => cardHtml(c)).join("")}</div></details>`;
  return top + body + deck;
}

function optionsList(items) {
  return `<div style="display:flex;flex-direction:column;gap:6px;margin-top:8px">${items.map((t) => `<div class="memo">${t}</div>`).join("")}</div>`;
}

function screenHtml(gs) {
  const s = gs.screen_state || {};
  switch (gs.screen_type) {
    case "EVENT":
      return `<div class="battlefield"><div class="panel-title">❖ ${esc(s.event_name || "事件")}</div>
        <div style="white-space:pre-wrap;color:#d9ccb8">${esc((s.body_text || "").replace(/#[a-z]|~|@/g, ""))}</div>
        ${optionsList((s.options || []).map((o) => `${o.disabled ? "🔒 " : ""}${esc(o.text || o.label)}`))}</div>`;
    case "CARD_REWARD":
      return `<div class="battlefield"><div class="panel-title">🂠 选一张牌</div><div class="hand">${(s.cards || []).map((c) => cardHtml(c)).join("")}</div></div>`;
    case "GRID":
    case "HAND_SELECT":
      return `<div class="battlefield"><div class="panel-title">🂠 选择卡牌 ${s.num_cards ? `（${s.num_cards} 张）` : ""}</div><div class="hand">${(s.cards || s.hand || []).map((c) => cardHtml(c)).join("")}</div></div>`;
    case "COMBAT_REWARD":
      return `<div class="battlefield"><div class="panel-title">🏆 战利品</div>${optionsList((s.rewards || []).map((r) => esc(
        r.type === "GOLD" || r.type === "STOLEN_GOLD" ? `💰 ${r.gold} 金币` : r.type === "POTION" ? `⚗ ${r.potion?.name}` : r.type === "RELIC" ? `◆ ${r.relic?.name}` : r.type === "CARD" ? "🂠 卡牌奖励" : r.type)))}</div>`;
    case "SHOP_SCREEN":
      return `<div class="battlefield"><div class="panel-title">💰 商店</div>
        <div class="hand">${(s.cards || []).map((c) => `<div>${cardHtml(c)}<div style="text-align:center;color:var(--gold2)">${c.price}g</div></div>`).join("")}</div>
        ${optionsList([...(s.relics || []).map((r) => `◆ ${esc(r.name)} — ${r.price}g`), ...(s.potions || []).map((p) => `⚗ ${esc(p.name)} — ${p.price}g`), s.purge_available ? `✂ 删牌 — ${s.purge_cost}g` : ""].filter(Boolean))}</div>`;
    case "REST":
      return `<div class="battlefield"><div class="panel-title">🔥 篝火</div>${optionsList((s.rest_options || []).map((o) => esc({ rest: "休息", smith: "锻造", lift: "举重", dig: "挖掘", recall: "回忆", toke: "吸烟", key: "钥匙" }[o] || o)))}</div>`;
    case "BOSS_REWARD":
      return `<div class="battlefield"><div class="panel-title">♛ Boss 遗物</div><div class="relics">${relicsHtml(s.relics)}</div>${optionsList((s.relics || []).map((r) => esc(`${r.name}：${state.catalog.relics[r.id]?.text || ""}`)))}</div>`;
    case "MAP":
      return `<div class="battlefield"><div class="panel-title">🗺 选择下一层</div>${optionsList((s.next_nodes || []).map((n) => `${ROOM_ICON[n.symbol] || n.symbol} 第 ${n.x} 列`))}</div>`;
    case "GAME_OVER":
      return `<div class="battlefield" style="text-align:center;padding:30px">
        <div style="font-family:var(--serif);font-size:30px;font-weight:900;color:${s.victory ? "var(--gold2)" : "#ff8a73"}">${s.victory ? "♛ 登顶成功" : "☠ 攀登终结"}</div>
        <div style="font-family:var(--display);font-size:22px;margin-top:8px">分数 ${s.score ?? "?"}</div></div>`;
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
  const boss = `<g class="node B"><circle cx="${W / 2}" cy="22" r="16" style="stroke:#c0392b;fill:#3a0f0b"/><text x="${W / 2}" y="22">♛</text></g>`;
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
  const tabs = [["lessons", `📜 经验卷轴 (${k.lessons.length})`], ["guides", `📖 攻略典籍 (${k.guides.length})`], ["patches", `🧪 评测补丁 (${k.patches.length})`], ["eval", "⚖ 评测记录"]];
  let body = "";
  if (tab === "lessons") {
    body = `<div class="grid scrolls">${k.lessons.map((l, i) => `
      <div class="scroll"><span class="num">№ ${i + 1}</span>${esc(l.text)}
        <div class="src"><span>F${l.floor ?? "?"}</span><span>${esc(l.run || "")}</span></div></div>`).join("") || `<div class="empty">还没有经验</div>`}</div>`;
  } else if (tab === "guides") {
    const g = k.guides.find((x) => x.topic === sub) || k.guides[0];
    const [cur, hist] = g ? g.text.split(/\n## History\n/) : ["", ""];
    body = `<div class="grid guide-layout">
      <div class="panel toc">${k.guides.map((x) => `<a data-guide="${esc(x.topic)}" class="${g && x.topic === g.topic ? "active" : ""}">${esc(x.topic)}</a>`).join("")}</div>
      <div class="panel wiki">${g ? md(cur) + (hist ? `<h2>历史版本</h2><div class="history">${md(hist)}</div>` : "") : `<div class="empty">还没有攻略</div>`}</div></div>`;
  } else if (tab === "patches") {
    const p = k.patches.find((x) => x.name === sub) || k.patches[0];
    body = `<div class="grid guide-layout">
      <div class="panel toc">${k.patches.map((x) => `<a data-patch="${esc(x.name)}" class="${p && x.name === p.name ? "active" : ""}">${esc(x.name)}</a>`).join("")}</div>
      <div class="panel">${p ? `<div class="panel-title">${esc(p.name)}</div><div class="muted" style="margin-bottom:8px">评测局结束后它写下的经验与攻略改动（绿色为新增，红色为删除）</div><div class="diff">${diffHtml(p.text)}</div>` : `<div class="empty">没有补丁</div>`}</div></div>`;
  } else {
    body = `<div class="panel wiki">${md(k.docs["eval-baseline.md"] || "没有评测记录")}</div>`;
  }
  $("#view-lore").innerHTML = `
    <h1 class="section-title">知识典籍<small>CODEX</small></h1>
    <div class="lore-tabs">${tabs.map(([id, name]) => `<button class="btn ${id === tab ? "active" : ""}" data-lore="${id}">${name}</button>`).join("")}
      <button class="btn small" id="lore-reload" style="margin-left:auto">↻ 刷新</button></div>
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
    <h1 class="section-title">实时观战<small>LIVE</small></h1>
    <div class="live-banner">
      <span class="status" style="color:${fresh ? "#ff8a73" : "var(--muted)"}">${fresh ? `<span class="live-dot"></span> 正在攀登` : "◌ 暂无动静"}</span>
      <span class="chip">${esc(info.run)}</span>
      <span class="chip">第 ${info.steps} 步</span>
      <span class="chip" id="live-age">${ageText(info.mtime)}</span>
      <button class="btn small" id="live-open">在回放中打开</button>
    </div>
    <div class="grid replay-grid">
      <div class="panel">${raw ? renderState(raw) : `<div class="empty">等待游戏状态…</div>`}</div>
      <div class="panel"><div class="panel-title">📜 最近行动</div><div class="log-list">${info.recent.slice().reverse().map(logItem).join("")}</div></div>
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
  const view = location.hash.slice(1);
  if (["hall", "replay", "lore", "live"].includes(view)) show(view);
})();
