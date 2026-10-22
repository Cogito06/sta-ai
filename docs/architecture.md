# 接口架构（v0.2）

> 已定（2026-10-22）：直接 fork CommunicationMod 修改（StS1 基本不再更新，不用担心合并）；牌库说明在一局里第一次出现时附上，之后用 `inspect`；用游戏自己的 card id，不另编号。

> 依据：[info-matrix.md](info-matrix.md)（人类 UI 与 CommunicationMod 对照表）、[interface-spec.md](interface-spec.md)（接口规格）。
> 核心思路（cogito 提出）：把所有牌编成一个**牌库**（含升级后的属性），接口只发牌的编号和会变的数字，LLM 对照牌库理解。同样的做法推广到遗物、药水、能力、敌人、事件。

---

## 1. 总体：静态的和动态的分开

游戏信息分两种：

| | 静态信息 | 动态信息 |
|---|---|---|
| 是什么 | 不随局面变：牌的说明、基础数值、升级后的数值、类型、稀有度、关键词；遗物、药水、能力的说明 | 随局面变：手牌里这张牌现在打多少伤害、费用被改成几、敌人现在多少血、意图 |
| 从哪来 | **数据库（牌库等）**，从游戏文件里提取一次 | **游戏运行时**，我们 fork 的 CommunicationMod |
| 怎么给 LLM | 一局开始时读一次（或按需查），之后反复用，**不重复发** | 每次状态里只发编号 + 会变的数字 |

好处：
- **省 token**：Bash 的说明只需要读一次，之后每回合只发 `Bash 2费 10dmg 2Vuln`
- **不会算错**：动态数字来自游戏本身，静态说明来自游戏文件
- **RL 能直接用**：牌的编号就是 RL 的输入特征，牌库里的数值就是牌的特征向量

## 2. 组件

```
┌──────────────────── 游戏端（你的电脑，Java） ────────────────────┐
│ Slay the Spire                                                   │
│  └─ ① 我们 fork 的 CommunicationMod：直接在源码里加字段和修正    │
└───────────────────────────── JSON ↕ 命令 ─────────────────────────┘
┌──────────────────── Python 端 ───────────────────────────────────┐
│ ② Catalog 数据库：牌库 / 遗物库 / 药水库 / 能力库 / 敌人库 / 事件库│
│ ③ Bridge 核心                                                    │
│    ├─ 状态模型：把 JSON 变成结构化的 Observation                  │
│    ├─ 信息过滤：按对照表藏掉人看不到的（抽牌堆顺序等）            │
│    ├─ 历史记录：走过的路线、刚才发生了什么（对比前后状态）        │
│    ├─ 动作执行器：规范动作 → 命令；序列执行和停下规则；规则出牌  │
│    └─ 自动处理：只处理没有选择的步骤                              │
│ ④ 渲染器：Observation → LLM 文本（以后加：→ RL 向量）             │
│ ⑤ MCP Server：start_run / get_state / act / inspect / note       │
│ ⑥ 日志与回放：每步记录、原始 JSON、每局汇总                      │
└──────────────────────────────────────────────────────────────────┘
                              ↕ MCP
                         Claude Code（LLM）
             （以后接上：策略库、LLM 自建的工具库）
```

### ① CommunicationMod fork（游戏端）

直接 fork CommunicationMod，改 `GameStateConverter.java` 等源码。StS1 基本不再更新，不需要和原版保持同步。fork 后也能顺手修原版的已知问题（Match and Keep 状态不传、药水满时无反馈等）。

只导出**游戏运行时才知道的东西**（静态说明交给牌库，不在这里导）：

| 加的字段 | 用途 |
|---|---|
| 每张牌当前的 `damage`、`block`、`magic_number`（游戏已经算好的值，也就是牌面上显示的数字） | 手牌数字和 UI 一致；Heavy Blade、Rampage、Searing Blow、Body Slam 等由游戏自己算 |
| 能量上限 | 显示 `Energy 2/3` |
| 抽牌堆打乱后再发送 | 从源头杜绝顺序泄露 |
| 事件正文（非配图事件也给） | 事件选择需要 |
| 燃烧精英标记、敌人招式名、Match and Keep 状态 | 优先级低，后做 |

### ② Catalog 数据库（静态数据）

**牌库**是核心，范围不只是战士牌：Ironclad 一局里还会遇到无色牌、诅咒、状态牌（Wound、Burn、Dazed 等），所以都要收。

每张牌一条：
```json
{
  "id": "Bash",               // 用游戏内部的 card id 当主键，CommunicationMod 直接给这个
  "code": "R012",             // 可选的短编号（R=红色/Ironclad，C=无色，S=状态，K=诅咒）
  "name": "Bash",
  "color": "RED", "type": "ATTACK", "rarity": "BASIC",
  "cost": 2, "target": "ENEMY",
  "keywords": [],             // Exhaust / Ethereal / Innate / Unplayable / Retain
  "base":     {"damage": 8,  "magic": 2, "text": "Deal 8 damage. Apply 2 Vulnerable."},
  "upgraded": {"damage": 10, "magic": 3, "text": "Deal 10 damage. Apply 3 Vulnerable."},
  "tags": ["vulnerable"]      // 以后给策略库和 RL 用，可以先空着
}
```
- 主键用游戏自己的 card id，不另起编号，避免对不上。短编号只是为了显示更省 token，可以不用
- 升级前后各存一份，cost 变化（如 Body Slam+ 0 费）也在 `upgraded` 里
- **数据来源**：从你电脑上游戏的 `desktop-1.0.jar` 里提取（英文本地化文本 + 每张牌 Java 类里的数值），用脚本自动生成，不手抄。和游戏版本绑定，带版本号

其他库同样结构，按需建：

| 库 | 内容 | 规模（大约） |
|---|---|---|
| 牌库 | Ironclad 牌 + 无色 + 诅咒 + 状态 | ~120 张 |
| 遗物库 | 说明、是否战斗相关、计数含义 | ~180 个（Ironclad 可用的） |
| 药水库 | 说明、是否需要目标、战斗外能否用 | ~30 种 |
| 能力库 | 玩家和敌人身上的 buff/debuff 说明 | ~100 种 |
| 敌人库 | 名字、所在 Act、HP 范围、能力；招式表以后再加 | ~70 种 |
| 事件库 | 事件名、各选项的说明 | ~50 个 |

### ③ Bridge 核心

就是规格文档第 3 节的东西，按模块分开：

- **状态模型**：JSON → `Observation` 对象（Python dataclass）。牌只存 `id + upgrades + 动态数字`，其他从牌库查
- **信息过滤**：按对照表，把人看不到的去掉。这一层单独做，方便以后检查"有没有泄露"
- **历史记录**：地图走过的路线；对比前后两个状态，生成"刚才发生了什么"
- **动作执行器**：规范动作 → CommunicationMod 命令；整回合序列；停下规则；规则出牌（`repeat play Skill` 等）
- **自动处理**：只处理没有选择的步骤

### ④ 渲染器

`Observation` → 文本。牌在状态里写成 `b Bash 2 [10 dmg, 2 Vuln]`：名字 + 当前费用 + 当前数字，说明靠牌库。
以后加一个 `Observation → 向量` 的渲染器给 RL，复用同一套状态模型和牌库。

### ⑤ MCP Server

工具同规格文档：`start_run`、`get_state`、`act`、`inspect`、`note`。`inspect card Bash` 直接查牌库。

### ⑥ 日志与回放

每步存原始 JSON（fork 版输出的），可以离线重放渲染器，改了文本格式也能对旧数据重新生成，不用重打。

## 3. 牌库怎么交给 LLM

三种做法：

| 做法 | 优点 | 缺点 |
|---|---|---|
| A. 一局开始时把整个牌库（约 120 张，几千 token）读进上下文 | 之后完全不用查；LLM 选牌时能对比所有牌 | 每局开头固定花几千 token |
| B. 完全按需：遇到不熟的牌才 `inspect` | 最省 | 调用次数多；LLM 可能"以为自己知道"而不查，记错数值 |
| C. **第一次见到某张牌时，在状态里附上它的说明，之后只发名字** | 自动、不会漏、只花需要的 token | 实现稍复杂一点（要记录本局已经展示过哪些） |

**建议 C + B**：默认用 C，LLM 想再看时用 `inspect`。遗物、药水、能力、事件也同样处理。

## 4. 实现顺序

1. 装好 CommunicationMod，跑通"开局 → 收到 JSON → 发命令"
2. 从游戏文件提取牌库（先只做牌库，其他库后补）
3. fork CommunicationMod：先只加牌的动态数字和打乱抽牌堆
4. Bridge 核心 + 战斗渲染 → 能手动打完一场战斗
5. 其他界面、自动处理
6. MCP 封装 → Claude Code 打一局
7. 补其他库、fork 里的低优先级字段
8. 日志、回放 → 打 5 局验收

## 5. 已定事项

1. 游戏端：fork CommunicationMod
2. 牌库交给 LLM：第一次出现时附说明 + `inspect`
3. 编号：用游戏 card id
