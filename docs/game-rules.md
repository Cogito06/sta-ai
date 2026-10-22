# StS1 游戏规则摘要（按"接口要应对什么"整理）

> 目的：接口设计的依据。只写对接口有影响的规则。
> 来源：Slay the Spire Wiki（fandom / wiki.gg）的 Neow、Rest Site、Merchant、Card Rewards、Potions、Gold、Relics、Keys、Act 4、Bosses、Elites、Keywords、Intent、Buffs、Debuffs、Energy、Block、Ironclad 页面；CommunicationMod 源码（GameStateConverter.java、CommandExecutor.java）和 README。
> 标 ⚠ 的条目：wiki 页面没抓到，内容凭我对游戏的了解补的，实现前要在游戏里核对。

---

## 一、一局的结构

| 项 | 规则 | 对接口的影响 |
|---|---|---|
| 层数 | Act 1/2/3 的 Boss 分别在第 16/33/50 层，打完 Boss 后进下一幕。Act 4（52–55 层：休息、商店、精英 Shield+Spear、Corrupt Heart）需要集齐三把钥匙 | "胜利"的定义要说清：打过 Act 3 Boss 还是打过 Heart |
| 地图 | 每幕 15 行节点 + Boss ⚠。第 1 行全是普通怪，第 9 行全是宝箱，第 15 行全是休息点，前 5 行没有精英和休息 ⚠。节点类型：M 怪、E 精英、? 未知、$ 商店、R 休息、T 宝箱 | 选路是长期规划决策，只给"下一步可选节点"不够，**必须能看到整张剩余地图** |
| ? 房间 | 大多数是事件，也可能是怪、商店、宝箱 ⚠（概率随遇到的次数变化） | 进房间后才知道是什么，接口按实际界面处理 |
| 燃烧精英 | 解锁 Act 4 后，每幕有一个带火焰标记的精英，更强，掉 Emerald Key | CommunicationMod 的地图节点只有符号，**看不到燃烧标记**，需要另想办法或暂时忽略 |
| Boss | 开局就知道本幕 Boss 是谁（`act_boss`）。Boss 前一定是休息点 | 地图头部显示 Boss 名 |

## 二、开局：Neow

- 正常开局有 4 个祝福选 1 个。第 1 个和卡牌有关（删 1 张、变 1 张、升 1 张、三选一职业牌、无色牌、随机稀有牌）。第 2 个是非卡牌奖励。第 3 个是"代价 + 收益"组合（代价：减最大 HP、扣血、诅咒、丢光金币；收益：删/变 2 张、250 金、稀有牌、稀有遗物、+最大 HP 等）。第 4 个是换掉初始遗物，拿一个随机 Boss 遗物 ⚠
- 选完后可能接着弹出**选牌界面**（删哪张、变哪张、从三张里选哪张）

**影响**：Neow 是一个事件界面，后面可能跟着牌组选择界面或卡牌奖励界面。这些都是真正的决策。

## 三、战斗规则

### 回合流程
1. 回合开始：格挡清零（有 Barricade、Calipers 等例外），能量回满 3（没用完的能量**不会**留到下回合，除非有 Ice Cream），抽 5 张 ⚠
2. 玩家出牌，用药水（药水不花能量）
3. 结束回合：手牌全部进弃牌堆（Runic Pyramid 例外），**Ethereal（虚无）牌留在手里会被消耗**；手里的诅咒和状态牌在这时触发效果（Burn 扣血、Regret 扣血等）
4. 敌人按意图行动，然后进入下一回合
- 抽牌堆空了就把弃牌堆洗回来 ⚠。手牌上限 10 张，超过的抽牌直接进弃牌堆 ⚠

### 牌
- 类型：Attack（攻击）、Skill（技能）、Power（能力，打出后持续整场战斗）、Status（状态，如 Wound、Dazed、Burn）、Curse（诅咒）
- 关键词：Exhaust（打出后移出本场战斗）、Ethereal（回合结束留在手里就消耗）、Innate（开局必在手牌）、Unplayable（不能打出）、X 费（花光所有能量，比如 Whirlwind）、升级（+）
- 费用可能在战斗中变化（Corruption 让技能 0 费，Enlightenment、Madness 等）

### 伤害和格挡的计算
- 攻击伤害 = (基础 + Strength + Vigor) × Weak 0.75（攻击方有 Weak 时）× Vulnerable 1.5（受击方有 Vulnerable 时），结果向下取整；多段攻击每段单独算
- 格挡 = (基础 + Dexterity) × Frail 0.75（有 Frail 时），向下取整
- 先扣格挡再扣 HP。"失去 X 点 HP"（Offering、Hemokinesis、Bloodletting 等）**无视格挡**
- 敌人有 Intangible 时，所有伤害降为 1

### 敌人
- 意图类型：Attack、Defend、Buff、Debuff、Strong Debuff、以及这些的组合（Attack+Defend 等）、Escape、Sleep、Stun、Unknown
- 攻击意图显示的是**算上力量、虚弱等之后的伤害 × 段数**，CommunicationMod 有这两个数（`move_adjusted_damage`、`move_hits`）
- 敌人身上的能力会显著改变打法：Curl Up、Angry、Thorns、Sharp Hide、Mode Shift（Guardian）、Malleable、Spore Cloud、Artifact、Ritual、Split 等
- **战斗中敌人的数量会变**：Slime 血量过半会分裂成两只，Gremlin Leader 和 Collector 会召唤，Awakened One 会复活
- 敌人会往你的牌堆里塞牌：Sentry 塞 Dazed，Hexaghost 塞 Burn，Slime 塞 Slimed，等等

### 战斗中的"小决策"（打出一张牌后还要再选）
Ironclad 常见的：
- 从手牌里选：Armaments（升级 1 张，升级版升级全部）、True Grit+（消耗 1 张）、Burning Pact（消耗 1 张）、Dual Wield（复制 1 张）、Warcry（放 1 张到抽牌堆顶）
- 从牌堆里选：Headbutt（弃牌堆选 1 张放到抽牌堆顶）、Exhume（从消耗堆拿回 1 张）
- 从生成的牌里选：Attack/Skill/Power/Colorless Potion（三选一）
- 随机效果：Havoc（打出抽牌堆顶的牌）、Infernal Blade（随机攻击牌）、Sword Boomerang（随机目标）、True Grit（没升级时随机消耗）

### Ironclad 起始配置
80 HP，起始遗物 Burning Blood（战斗结束回 6 HP），起始牌组 Strike×5、Defend×4、Bash×1。

## 四、战斗奖励

| 来源 | 奖励 |
|---|---|
| 普通怪 | 10–20 金币、卡牌奖励（三选一，可以跳过）、40% 概率药水（掉了概率 −10%，没掉 +10%） |
| 精英 | 25–35 金币、1 个遗物、卡牌奖励（稀有概率更高）、药水概率同上 |
| Boss（Act 1/2） | 95–105 金币、稀有牌三选一、Boss 遗物三选一（可以不拿）、回满血（A5+ 只回 75% 的已损失 HP） |
| 卡牌稀有度 | 普通怪：普通 60 / 罕见 37 / 稀有 3；精英：50 / 40 / 10。另外有一个"稀有修正值"，从 −5% 开始，每出一张普通牌 +1%，出稀有牌后重置 |
| 卡牌升级概率 | 只有卡牌奖励里的牌会预先升级：Act 1 0%，Act 2 25%，Act 3 50% |
| 遗物修正 | Singing Bowl：可以不拿牌改成 +2 最大 HP。Question Card：多 1 张可选。Busted Crown：少 2 张。Prayer Wheel：多一组卡牌奖励 |

**影响**：奖励界面里可能同时有金币、遗物、药水、卡牌、钥匙等多项。药水槽满了就拿不了药水（CommunicationMod 这时**不会报错**，要接口自己检查）。

## 五、其他房间

- **休息点**：只能选一项：Rest（回 30% 最大 HP）、Smith（升级 1 张牌）。有遗物时多出 Lift（Girya，+1 力量，最多 3 次）、Toke（Peace Pipe，删 1 张牌）、Dig（Shovel，随机遗物）。还有 Recall（拿 Ruby Key）。有些遗物会禁用选项（Coffee Dripper 禁 Rest，Fusion Hammer 禁 Smith）⚠
- **商店**：5 张职业牌（2 攻 2 技 1 能力，其中 1 张半价）、2 张无色牌、3 个遗物、3 瓶药水、删牌服务（75 金起，每用一次 +25，每家店只能删一次）。一次进店可以买多样东西，然后离开
- **宝箱**：1 个遗物（加金币）。如果有 Sapphire Key，**钥匙和遗物只能二选一**
- **Boss 宝箱**：3 个 Boss 遗物选 1 个，也可以都不拿。Boss 遗物往往有代价（比如 Ectoplasm 拿不了金币、Coffee Dripper 不能 Rest、Runic Dome 看不到敌人意图）
- **事件**：每个事件有若干选项，有些选项是灰的（条件不满足）。有些事件有多页，有些事件会接战斗或选牌

## 六、药水

- 3 个槽位（A11+ 只有 2 个），Potion Belt +2
- 大多数只能在战斗中用；Fruit Juice、Blood Potion、Entropic Brew 在战斗外也能用
- 有些需要选目标（Fire Potion 等投掷类）
- 可以随时丢掉

## 七、玩家能看到什么、看不到什么（公平性）

一个人类玩家**能看到**：自己的牌组、抽牌堆里**有哪些牌**（游戏里查看时按顺序打乱显示）、弃牌堆、消耗堆、敌人 HP、格挡、能力、意图（含伤害数字）、地图全图、遗物和药水、所有牌和遗物的说明文字。

人类**看不到**：抽牌堆的顺序、敌人下下回合的行动、未来的卡牌奖励、? 房间里是什么。

**CommunicationMod 的情况**：
- 它会把**抽牌堆按实际顺序**发出来（源码注释："The order of the draw pile is not currently randomized when sent to the client"）。这是人类看不到的信息，**接口必须隐藏顺序，只给牌的数量**，否则 LLM 等于作弊，实验结论也会失真
- 它**不提供**牌、遗物、能力、药水的说明文字，也不给牌的伤害和格挡数字。人类能看到这些，所以**接口要自己准备一张数据表补上**
- 它提供敌人最近两次行动的编号（`last_move_id`、`second_last_move_id`）。人类可以通过记忆知道这些，所以可以给
- 有 Runic Dome 时意图全部变成 `NONE`，和游戏一致

## 八、随机性和种子

- 开局可以指定种子：`start ironclad 0 SEED`（种子是游戏里显示的字母数字串）
- StS1 把不同用途的随机数分开（地图、卡牌奖励、怪物、洗牌、事件等各自一条）⚠，所以同一个种子下地图和大部分奖励是固定的，但战斗里的随机结果会受你之前的操作影响
- **影响**：同种子对比实验是可行的（比如"同一张地图，换一种选牌策略"），但不能指望两局完全一样
