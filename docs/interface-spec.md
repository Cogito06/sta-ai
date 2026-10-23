# StS1 LLM 游戏接口规格（草案 v0.6）

> 状态：待 cogito 审阅。审阅通过前不写代码。
> 依据：[game-rules.md](game-rules.md)（游戏规则摘要）和 [info-matrix.md](info-matrix.md)（人类 UI 与 CommunicationMod 的信息对照表）。接口给 LLM 的信息以对照表为准。
> 范围：Phase 0，Ironclad A0，真实游戏 + CommunicationMod，Claude Code 通过 MCP 工具来玩。
> 已定：胜利 = 打过 Act 3 Boss；思考过程只在关键决策时记录；游戏内名称用英文；只有"没有选择"的步骤才自动处理；回合中有新牌进入手牌时停下。

---

## 0. 设计原则

1. **信息和人类玩家一样多，不多也不少。** 人能看到的都给（包括牌和遗物的说明文字，CommunicationMod 不给，我们自己补）；人看不到的一律不给（抽牌堆顺序，CommunicationMod 会泄露，我们要藏起来）。这样 LLM 的成绩才能和人比，实验结论才可信。
2. **凡是有选择，就交给 LLM。** 接口只替它做"唯一选项"的事。
3. **接口只给事实，不替 LLM 思考。** 游戏界面本身显示的数字（比如牌上算好力量的伤害、敌人意图伤害）照样给；游戏不显示的推算（能不能斩杀、最优出牌顺序）不放在接口里，留给以后 LLM 自己造的工具。这样"有没有计算工具"可以作为实验变量。
4. **省 token。** 默认紧凑，要细节时用 `inspect` 查。
5. **动作空间和以后的 RL 共用。**

## 1. 目标与非目标

| # | 目标 | 验收 |
|---|---|---|
| G1 | 能完整打一局，覆盖所有界面（见第 4 节界面清单） | 连续 5 局无人工干预、不卡死 |
| G2 | 省调用、省 token | 战斗状态 ≤ 约 800 字符；平均每层 ≤ 约 6 次工具调用 |
| G3 | 可复现、可对比 | 每局记录种子；同种子地图和奖励一致 |
| G4 | 每步都有结构化日志，供"假设→实验→结论"使用 | 每局一个 JSONL + 汇总 |
| G5 | 动作层和 CommunicationMod 解耦，以后能接 sts_lightspeed | 规范动作枚举（第 6 节） |

不做：其他角色和进阶；策略库、计算工具、自我进化循环本身；RL 训练；截图识别；多局并行。

## 2. 结构

```
Slay the Spire + CommunicationMod   ←→  stdin/stdout JSON
        ▼
Bridge（Python 常驻进程）
  ├─ 解析状态 → 规范状态（隐藏抽牌堆顺序）
  ├─ 规范动作 → CommunicationMod 命令（处理下标换算）
  ├─ 自动处理无选择步骤
  └─ 日志
        ▼
MCP Server：状态 → 紧凑文本；文本动作 → 规范动作
        ▼
Claude Code
```

**数值和说明文字**：静态说明来自牌库等数据库，动态数字来自游戏补丁。见 [architecture.md](architecture.md)。

## 接口原则（2026-10-22 定）

照游戏 UI 的形式来：屏幕上直接摆着的、每次都会变的东西主动给；人类要点开才能看的东西做成查询接口（`inspect`），查不查由 LLM 自己决定。地图每一幕第一次进地图界面时给一次全图，之后用 `inspect map` 查（含走过的路线）。接口里不放任何策略提示或强制要求，LLM 会不会规划路线、写笔记、查记忆，都是它自己的策略，只作为观察结果统计。

## 3. Input：LLM 发什么

### 3.1 工具（5 个）

| 工具 | 参数 | 作用 |
|---|---|---|
| `start_run` | `seed=null, overwrite=false` | 开新局（Ironclad A0）。不给种子就随机，返回种子。有存档时拒绝，除非 overwrite=true |
| `continue_run` | — | 继续存档里的那局（等同主菜单的 Continue），日志接着写进同种子的 run 目录 |
| `get_state` | — | 当前状态文本 |
| `act` | `actions: str` | 执行一个或一串动作。主力工具 |
| `inspect` | `what: str` | 只读查询：`deck`、`draw`、`discard`、`exhaust`、`relics`、`potions`、`map`、`card <名>`、`relic <名>`、`power <名>`、`enemy <编号>`。不改变游戏 |
| `note` | `text`, `tag=null` | 往日志写备注（假设、理由、教训）。不改变游戏 |

### 3.2 动作

用 `;` 分隔，可以一次给一串：

| 动作 | 写法 | 何时用 |
|---|---|---|
| 出牌 | `play <牌字母> [敌人编号]` | 战斗 |
| 结束回合 | `end` | 战斗。总是序列的最后一条 |
| 用药水 | `potion <槽> [敌人编号]` | 战斗；Fruit Juice 等在战斗外也能用 |
| 丢药水 | `drop <槽>` | 任何时候 |
| 选择 | `choose <编号>` | 所有编号列表：地图、事件、奖励、商店、休息、Boss 遗物、选牌 |
| 确认 | `confirm` | 多选界面选完后；商店/奖励界面"离开" |
| 跳过 | `skip` | 跳过卡牌奖励、跳过 Boss 遗物、取消 |

**编号规则**：
- 手牌用字母 a–j。字母绑定在牌的 uuid 上，一个回合内不变；打出 `a` 后 `b` 仍是 `b`，新进手牌的牌拿下一个没用过的字母。
- 敌人编号从 0 开始，**整场战斗不变**。死掉的敌人保留编号显示为 dead；分裂或召唤出的新敌人拿新编号。（CommunicationMod 本身就是按这个规则编号的，不用换算。）
- 其他列表从 0 开始，以当前界面显示为准。
- Bridge 负责换算成 CommunicationMod 的下标（它的出牌下标从 1 开始，其他从 0 开始）。

### 3.3 序列执行：什么时候停下

`act` 逐条执行。出现以下任一情况就**停下**，返回当前状态，剩下的动作作废，并说明停在哪一条、为什么：

| 停下的原因 | 对应规则 |
|---|---|
| 动作非法（能量不够、目标已死、牌不能打） | — |
| 弹出了选择界面（从手牌选、从牌堆选、三选一） | Armaments、True Grit+、Burning Pact、Dual Wield、Warcry、Headbutt、Exhume、发现类药水 |
| **有新牌进入手牌**（抽牌、生成、拿回） | Pommel Strike、Shrug It Off、Battle Trance、Power Through、Infernal Blade、Exhume 等 |
| 敌人数量变了（分裂、召唤、复活） | Slime 分裂、Gremlin Leader、Collector、Awakened One |
| 出现了随机结果，影响后续计划 | Havoc、Sword Boomerang、未升级的 True Grit |
| 战斗结束、玩家死亡 | — |

`end` 之后敌人行动、新回合开始，返回新回合状态（包括敌人这回合做了什么）。

### 3.4 自动处理（只处理没有选择的步骤）

| 情况 | 处理 |
|---|---|
| 奖励里的金币 | 自动拿 |
| 奖励里的遗物（普通怪/精英掉落） | 自动拿 |
| 奖励里的药水，槽有空位 | 自动拿 |
| 奖励里的药水，槽满了 | **交给 LLM**（丢一瓶换，还是不要） |
| 卡牌奖励 | 自动打开选卡界面；选哪张、跳过**交给 LLM** |
| 商店房间 | 自动走到商人面前打开商店；买什么、离开**交给 LLM**（离开商店后自动回地图） |
| 宝箱 | 自动打开；有 Sapphire Key 和遗物二选一时**交给 LLM** |
| 地图下一步只有一个节点 | 自动走 |
| 纯过场按钮（继续、离开空界面） | 自动按 |
| 其他一切（Neow、事件、商店、休息、Boss 遗物、选牌） | **交给 LLM** |

自动处理的内容在返回结果里用一行汇总，也写进日志。

### 3.5 每局记忆库（2026-10-22 定）

LLM 自己的想法存在对话之外的 `runs/<这局>/memory.json`，重启 Claude、读档继续都还在。游戏里看得到的东西（地图、走过的路、牌组）不进记忆库，由接口每次直接给。

- 写：`note(text, tag)`。`tag="plan"`（构筑思路）和 `tag="route"`（路线打算）新的覆盖旧的；其他 tag 或不写 tag 的追加成观察笔记。全部是自由文字，以后再加转换器整理成格式化攻略（如"卡组启动条件→卡组配置→卡组打法"）
- 显示：地图、选卡、商店、火堆、Boss 遗物、事件界面头部带当前 plan 和 route。战斗中不显示，LLM 心里没底时自己用 `inspect memory` 查全部
- 不强制、不提示它写，看它自己会不会想到
- 开关：环境变量 `STS_MEMORY=off` 时不回显、`inspect memory` 不可用（日志照记），用于基线评测
- 以后：记忆整理交给 sub agent；跨局策略库另做

**跨局经验库（2026-10-23 定）**：`note(text, tag="lesson")` 写进所有局共用的 `runs/lessons.json`（记下来自哪局、第几层），`inspect lessons` 查阅。开局只提示一句有几条经验，不展示内容，要不要看由 LLM 自己决定。
**攻略文件夹（2026-10-23 定）**：`guides/` 下一个问题一个文件（markdown，在仓库里，方便看它的看法怎么变）。文件里有问题、当前看法、被替换掉的旧看法（带来自哪局、第几层）。问题可以由我们提（比如 `neow-choice`：开局选哪个 Neow 选项），也可以由 LLM 自己提。工具 `guide(topic, view, question)` 写当前看法，旧的自动进历史；`inspect guides` 列出所有问题，`inspect guide <topic>` 查看一篇。开局只列出有哪些攻略，复盘时列出所有问题。和经验库的区别：经验是零散的一条条记录，攻略是针对一个问题的整理过的看法。
**局后复盘**：结算画面附上本局小结（进阶、卡组、遗物、本局记忆、已有经验条数），并说明此时可以写 lesson、不写也行。不给任何策略提示，只提供写经验的时机。`STS_MEMORY=off` 时经验库和复盘一起关闭，用于基线评测。

### 3.6 一个回合怎么跑：增量状态 + 条件指令（v0.5 提议）

问题：Dark Embrace + Corruption、Feel No Pain 之类的抽牌循环里，每抽一张就停一次，会产生大量没必要的思考和调用。

**(1) 增量状态**
- 回合开始发一次**完整状态**（全部手牌、敌人、能量）
- 同一回合内停下后只发**变化**：新进手牌的牌（带新字母）、费用变化、升级、离开手牌的牌、能量、敌人 HP/意图/能力的变化、新出现或死掉的敌人
- LLM 随时可以 `get_state` 要完整状态

**(2) 停下条件可调**
`act(actions, stop_on=...)`，默认 `draw,choice,spawn,random`（即 3.3 的规则）。LLM 判断"新牌不影响计划"时可以设成 `stop_on=choice`，只在必须选择时才停。非法动作、战斗结束、死亡永远会停。

**(3) 可以引用"还没抽到的牌"的条件指令**
除了用字母指定具体某张牌，还可以按规则出牌，执行时按当时手牌匹配：

| 写法 | 意思 |
|---|---|
| `play Strike 0` | 打手里任意一张 Strike，目标 0 |
| `repeat play Skill` | 只要手里还有能打的 Skill 就一直打 |
| `repeat play cost0` | 一直打 0 费的牌 |
| `repeat play Attack 0` | 一直打攻击牌打 0 号；0 号死了就停 |
| `until energy 0` / `until hand empty` | 给 repeat 加终止条件 |

示例（Corruption + Dark Embrace 的回合）：
```
act("repeat play Skill; repeat play Attack 0; end", stop_on="choice")
```
一次调用打完整个回合，返回整个回合的汇总。

- 安全阀：单次 `act` 最多执行 30 个动作；会扣自己血的牌（Hemokinesis、Offering 等）不会被 `repeat` 自动打出，除非明确写名字
- 这些只是"执行 LLM 已经做出的决定"，不替它判断，符合原则 3
- 以后 LLM 自建的工具可以扩展这套指令（比如自己定义宏）

## 4. Output：LLM 收到什么

每次返回三段：**结果**（刚才发生了什么）、**状态**（现在的局面）、**可选动作**（`>` 开头的一行）。

### 4.1 每个界面都有的头部

```
F7 Act1 | HP 62/80 | Gold 99 | Potions: 0 Fire Potion(T) 1 Block Potion 2 -
```
（T = 需要目标）遗物只在开局、获得新遗物时和 `inspect relics` 时显示，因为遗物很少变，每次都给太浪费。

### 4.2 战斗

```
== Combat T3 == Energy 3/3 | Block 5 | Str 2, Vuln 1
Enemies:
 0 Jaw Worm 30/44 Blk 6 | intent ATK 13 | Str 3
 1 Red Louse 9/12 | intent BUFF | Curl Up 5
 2 (dead)
Hand:
 a Strike 1 - 8 dmg
 b Bash 2 - 10 dmg, 2 Vuln
 c Defend 1 - 5 blk
 d Shrug It Off 1 - 8 blk, draw 1
 e Carnage 2 [Ethereal] - 22 dmg
 f Wound [Unplayable]
Draw 12 | Discard 3 | Exhaust 0
> play a-e [0-1] | potion 0 [0-1] | potion 1 | end
```
- 牌的数字**直接取游戏牌面上显示的值**（游戏已算上自己的 Strength、Weak、Dexterity、Frail 和牌自身的成长）
- 牌的效果用简写（`dmg` 伤害、`blk` 格挡、`draw` 抽牌、`Vuln`/`Weak` 给敌人上的状态）；完整说明用 `inspect card Carnage`
- 关键词标在名字后：`[Ethereal]` `[Exhaust]` `[Unplayable]` `[Innate]`；费用 `X` 表示 X 费；费用被改过的显示当前费用
- 敌人意图：`ATK 13` 或 `ATK 6x2`（游戏算好的数），`DEF`、`BUFF`、`DEBUFF`、`STRONG DEBUFF`、`ATK+DEF` 等组合、`SLEEP`、`STUN`、`ESCAPE`、`UNKNOWN`
- 敌人能力带数值列出（`Curl Up 5`、`Thorns 3`、`Mode Shift 30`）；不认识的用 `inspect power <名>`
- **抽牌堆只给张数**；`inspect draw` 给牌的种类和数量（按字母排序，不按顺序）


#### 4.2.1 数值从哪来：只用游戏自己给的（v0.6）

原则：**接口只转述游戏界面上显示的东西，不自己算。** 游戏能做的推算交给 LLM，就像人类玩家自己记、自己算。

- 牌的数值（伤害、格挡、Vuln 层数等）直接用游戏里算好的值。比如 Heavy Blade 吃力量、Body Slam 等于格挡、Rampage 越打越高、升级后数值变化，游戏都已经算好了。
- 问题是原版 CommunicationMod **不导出这些数值和说明文字**，只给名字、费用、是否升级。解决办法：给 CommunicationMod 加一点导出代码（大约十几行 Java，在 `GameStateConverter` 的卡牌、遗物、能力、药水对象里加上游戏当前的数值和说明文字），或者用已经做了这件事的分支（如 CommunicationModPlus，**待核实**）。这样就不需要自建数据表，也不会和游戏算得不一样。
- 遗物计数（Pen Nib 9/10 等）是游戏图标上显示的，照常给。
- 当前打不了的牌标 `[x]`（游戏里这些牌是灰的），房间类型（普通/精英/Boss），照常给。

**去掉的（LLM 自己记、自己算）**：本回合已打几张牌、几张攻击牌；Headbutt / Warcry 放到堆顶的牌；Rampage 被打过几次；手牌数。

**仍然不给**：抽牌堆顺序、敌人以后的行动、本回合总受伤之类的汇总。

**实现时核对**：敌人意图伤害是否已含玩家身上的 Vulnerable（游戏界面显示的是含的）。

### 4.3 `act` 的结果段

```
Done 3/3: Bash→0, Strike→0, end
 You: Jaw Worm 30→14 (+2 Vuln)
 Enemy turn: Jaw Worm ATK 13 → blocked 5, lost 8 HP | Red Louse gained 3 Str
 New turn: drew Defend, Anger, Inflame, Strike, Bash
```
停下时：
```
Done 1/3, stopped after "play d": drew Battle Trance. Replan.
```

### 4.4 地图

每幕第一次进地图时给全图，之后每次只给接下来几步：
```
== Map Act1 == Boss: The Guardian
 15 R R R R
 14 M ? E M
 ...
  1 M M M M
 (全图格式待实现时定，目标是 LLM 能看清每条路径的连接)
Next: 0 M (x1)  1 ? (x3)  2 E (x5)
> choose 0-2
```
已知缺口：CommunicationMod 的地图里**看不到燃烧精英的标记**（Emerald Key）。A0 先不处理钥匙，见第 7 节第 1 个问题。

### 4.5 其他界面

所有非战斗界面都是同一个格式：标题、编号列表、可选动作。

| 界面（CommunicationMod 的 screen_type） | 显示 | 动作 |
|---|---|---|
| EVENT（含 Neow） | 事件名、正文（有的话）、选项文本，灰掉的选项标 `[disabled]` | `choose` |
| CARD_REWARD | 三张牌（带简写效果）、当前牌组摘要；有 Singing Bowl 时多一项 | `choose` / `skip` |
| COMBAT_REWARD | 剩下没自动拿的奖励（药水槽满时的药水、卡牌奖励入口、钥匙） | `choose` / `confirm` |
| SHOP_SCREEN | 牌、遗物、药水（带价格和简写效果），删牌价格 | `choose`（可多次购买）/ `confirm` 离开 |
| REST | 可用选项（Rest 显示能回多少 HP） | `choose` |
| CHEST | 只有钥匙和遗物二选一时才出现 | `choose` |
| BOSS_REWARD | 三个 Boss 遗物（带完整说明，因为代价很重要） | `choose` / `skip` |
| GRID（从牌组里选，比如升级、删除、变化，或 Headbutt、Exhume） | 可选牌、要选几张、用途 | `choose` 若干次，然后 `confirm` |
| HAND_SELECT（从手牌里选） | 手牌、要选几张、能不能选 0 张 | 同上 |
| GAME_OVER | 胜负、层数、分数 | `start_run` |

### 4.6 错误

```
ERR "play b 0": not enough energy (need 2, have 1). Nothing after this was run.
<当前状态>
```
非法动作不改变游戏。药水槽满时买药水、拿药水，CommunicationMod 不会报错，**由 Bridge 提前检查并报错**。

## 5. 参考数据（`inspect` 的内容）

| 查询 | 返回 |
|---|---|
| `card <名>` | 完整说明（当前升级状态），类型、稀有度、关键词，升级后的样子 |
| `relic <名>` / `power <名>` / `potion <名>` | 完整说明；遗物带计数器（如 Pen Nib 4/10） |
| `enemy <编号>` | HP、格挡、所有能力的完整说明、意图、最近两次行动 |
| `deck` | 牌组按类型分组，带升级标记 |
| `map` | 全图 + 当前位置 |

## 6. 规范动作（和 RL 共用）

```
PLAY(hand_index, target | None)   END_TURN
POTION_USE(slot, target | None)   POTION_DISCARD(slot)
CHOOSE(index)                     CONFIRM        SKIP
```
LLM 的文本动作和以后 RL 的输出都转成这套。RL 额外拿到合法动作掩码。

## 7. 日志与指标

- 目录：`runs/<日期时间>_seed-<种子>/` 下放 `run.jsonl`（每步一行）、`raw/`（CommunicationMod 原始 JSON，用于回放）、`summary.json`；总表 `runs/index.csv`
- 每步记录：步号、时间、层、界面、发给 LLM 的状态文本、LLM 的输入、执行了几条、停下原因、自动处理内容、备注
- 每局汇总：种子、接口版本、agent 配置（提示词/策略库版本）、结果、到达层数、死因、每层 HP、击杀精英/Boss 数、最终牌组和遗物、工具调用次数、返回给 LLM 的总字符数、非法动作次数、用时

## 8. 还要你定的事

1. ~~"赢"怎么算~~ → 已定：**打过 Act 3 Boss 即胜利**。钥匙和 Act 4 不追求（Recall 照常作为休息点选项）；打过 Heart 只作额外记录。
2. ~~思考过程怎么记录~~ → 已定：只在关键决策（选牌、选路、事件、Boss 遗物、商店、休息）时用 `note` 记录。后续加"整体思路"（见 3.5）。
3. **第 4.2 节战斗状态的详细程度**：牌带简写效果会多花一些 token，但能减少 `inspect` 调用。你觉得这个密度可以吗？

确认后的实现顺序：CommunicationMod 跑通 → 给它加数值和说明导出 → Bridge 解析和执行 → 战斗文本 → 其余界面 → 自动处理 → 日志 → MCP 封装 → 打 5 局验收。
