# 信息对照表：人类 UI 与 CommunicationMod

> 用途：接口设计的依据。接口给 LLM 的信息 = **人类在 UI 上能看到的**。
> - CommunicationMod 缺的 → 给 mod 打补丁补上
> - CommunicationMod 多给的（人看不到的）→ 接口藏起来
> 来源：CommunicationMod 源码 `GameStateConverter.java`、`CommandExecutor.java`、`ChoiceScreenUtils.java` 和 README；UI 部分是我对游戏界面的了解，⚠ 表示需要进游戏核对。

图例：✓ 已有　✗ 缺，要补　⚠ 多给了，要藏　— 不需要

---

## 1. 任何界面都有（顶栏）

| 人类 UI 上能看到 | CommunicationMod 字段 | 状态 |
|---|---|---|
| 角色、HP / 最大 HP、金币 | `class`、`current_hp`、`max_hp`、`gold` | ✓ |
| 层数、Act、进阶等级 | `floor`、`act`、`ascension_level` | ✓ |
| 本幕 Boss（地图上的 Boss 图标） | `act_boss` | ✓ |
| 遗物图标和计数（Pen Nib 9 等） | `relics[].name / counter` | ✓ |
| **遗物说明**（鼠标悬停） | 无 | ✗ 要补 |
| 遗物已失效 / 已用过的灰色状态（Lizard Tail、Centennial Puzzle 等） | 部分通过 `counter`（如 -2）⚠ | 待核对 |
| 药水图标 | `potions[].name / can_use / can_discard / requires_target` | ✓ |
| **药水说明** | 无 | ✗ 要补 |
| 钥匙 | `keys` | ✓（A0 不追求） |
| 牌组（点开查看，含升级） | `deck[]` 名字、升级次数、类型、稀有度 | ✓ |
| **牌的说明和数值**（牌面文字） | 无 | ✗ 要补 |
| 种子 | `seed`（内部长整数，不是游戏显示的字母串） | — 日志用，不给 LLM |

## 2. 战斗

| 人类 UI 上能看到 | CommunicationMod 字段 | 状态 |
|---|---|---|
| 能量 | `player.energy` | ✓（上限没给，⚠ 需要从遗物推断或补） |
| 自己的格挡、能力和层数 | `player.block`、`player.powers[].name / amount` | ✓ |
| **能力说明**（悬停） | 无 | ✗ 要补 |
| 手牌：名字、费用、升级、是否发光（能打） | `hand[]` 的 `name / cost / upgrades / is_playable / has_target / exhausts / ethereal` | ✓ |
| **手牌上的数字**（已算上力量、虚弱等的伤害、格挡） | 无 | ✗ 要补，直接导出游戏算好的值 |
| 抽牌堆、弃牌堆、消耗堆的张数 | 三个列表的长度 | ✓ |
| 抽牌堆里有哪些牌（点开查看，**游戏里是打乱顺序显示的**） | `draw_pile[]`，**按真实顺序** | ⚠ 要藏顺序，只给内容 |
| 弃牌堆、消耗堆里有哪些牌 | `discard_pile[]`、`exhaust_pile[]` | ✓ |
| 敌人：名字、HP、格挡 | `monsters[].name / current_hp / max_hp / block` | ✓ |
| 敌人意图图标和伤害数字（含段数） | `intent`、`move_adjusted_damage`、`move_hits` | ✓（是否已算上玩家的易伤，⚠ 待核对） |
| 敌人能力图标和层数 | `monsters[].powers[]` | ✓ |
| **敌人能力说明** | 无 | ✗ 要补 |
| 敌人行动时头上冒出的招式名（如 "Bellow"） | 无，只有数字 `move_id` | ✗ 可选，优先级低 |
| 敌人死亡、逃跑、"半死"等待复活 | `is_gone`、`half_dead` | ✓ |
| 敌人身上的数字变化、伤害飘字 | 无（只有前后两个状态） | — 接口对比前后状态生成"刚才发生了什么"，等同于看动画 |
| 打出牌后弹出的选择框（选手牌、选牌堆、三选一） | `screen_type` = `HAND_SELECT` / `GRID` / `CARD_REWARD`，带 `max_cards`、`can_pick_zero` 等 | ✓ |
| 回合数 | `turn` | ✓（UI 不直接显示，但人自己知道，可以给） |

**CommunicationMod 多给的，人看不到**

| 字段 | 处理 |
|---|---|
| `draw_pile` 的真实顺序 | ⚠ 藏起来：只给按名字排序的内容 |
| `move_id`、`last_move_id`、`second_last_move_id`（招式编号） | ⚠ 不给。人只能靠记忆，LLM 也自己记 |
| `move_base_damage`（未修正的伤害） | ⚠ 不给，UI 只显示修正后的数字 |
| `uuid`、`limbo`、`current_action`、`action_phase` | — 内部使用，不给 LLM |

## 3. 地图

| 人类 UI 上能看到 | CommunicationMod 字段 | 状态 |
|---|---|---|
| 整张地图：每个节点的类型和连线 | `map[]` 的 `x / y / symbol / children / parents` | ✓ |
| 当前位置、下一步可选节点 | `current_node`、`next_nodes`；选择列表是 `x=1` 这种格式 | ✓ |
| 已经走过的路径（地图上的划线） | 无访问标记 | ✗ 接口自己记录走过的节点（这是人也看得到的，不算推算） |
| Boss 节点 | 只有 `boss_available` 和选项 `boss` | ✓ 够用 |
| **燃烧精英的火焰标记** | 无 | ✗ 要补（A0 不追钥匙，优先级低） |

## 4. 非战斗界面

| 界面 | 人类 UI 上能看到 | CommunicationMod | 状态 |
|---|---|---|---|
| 事件（含 Neow） | 事件名、配图旁的正文、每个选项的完整文字（含代价和收益）、灰掉的选项 | `event_name`、`options[].text / disabled / label`；`body_text` **对非配图事件是空的** | ✓ 选项；✗ 部分事件正文要补 |
| Match and Keep 小游戏 | 翻开的牌 | **不传**（README 已知问题） | ✗ 要补，或交给 LLM 盲选 ⚠ |
| 卡牌奖励 | 三张牌的牌面（含说明、是否升级），Singing Bowl 按钮，跳过按钮 | `cards[]`（无说明）、`bowl_available`、`skip_available` | ✗ 说明要补 |
| 战斗奖励 | 金币数、遗物、药水、卡牌、钥匙 | `rewards[]` 带 `gold / relic / potion / link` | ✓ |
| 商店 | 所有商品和价格（买不起的显示为红色价格）、删牌价格、打折标签 | `cards / relics / potions[].price`、`purge_cost`；**选择列表只含买得起的** | ✓ 价格；接口显示全部商品，买不起的标出来 |
| 休息点 | 可用的选项按钮（Rest、Smith、Lift、Toke、Dig、Recall），被遗物禁用的选项 | `rest_options`（选项名） | ✓（被禁用的选项是否出现 ⚠ 待核对） |
| 宝箱 | 宝箱类型、打开后的遗物和金币 | `chest_type`、`chest_open`，之后进入奖励界面 | ✓ |
| Boss 遗物 | 三个遗物及说明 | `relics[]`（无说明） | ✗ 说明要补 |
| 从牌组选牌（升级、删除、变化） | 所有可选牌、要选几张、升级时的预览 | `cards[]`、`num_cards`、`any_number`、`for_upgrade / for_transform / for_purge` | ✓；升级预览随牌的说明一起补 |
| 结算 | 胜负、分数 | `victory`、`score` | ✓ |

## 5. 总结：要给 CommunicationMod 补的东西

按优先级：

1. **牌的当前数值和说明文字**（伤害、格挡、magic number、完整描述，含升级后的版本），直接导出游戏 UI 上显示的值
2. **遗物、能力、药水的说明文字**
3. **抽牌堆不按真实顺序发送**（也可以在接口里藏，补丁里做更保险）
4. **事件正文**（非配图事件）
5. 能量上限
6. 燃烧精英标记、敌人招式名、Match and Keep 状态（优先级低）

需要藏的：抽牌堆顺序、招式编号、未修正伤害、内部字段。
接口自己记录（人能从 UI 看到的历史）：地图上走过的路径。
