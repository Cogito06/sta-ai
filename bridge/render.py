"""Turns a CommunicationMod message into the compact English text the LLM reads.

Follows docs/interface-spec.md section 4 and docs/info-matrix.md: only what a human can see
in the game UI. The draw pile is shown by count and contents, never in order; monster move ids
and base damage are not shown.

A Renderer lives for one run: it remembers which cards/relics/potions the LLM has already seen
(their full text is shown only the first time), the hand letters of the current turn, and the
map path walked so far.
"""
import string

from bridge.catalog import Catalog

ROOM_NAMES = {"MonsterRoom": "Monster", "MonsterRoomElite": "Elite", "MonsterRoomBoss": "Boss"}
INTENT_NAMES = {
    "ATTACK": "ATK", "ATTACK_BUFF": "ATK+BUFF", "ATTACK_DEBUFF": "ATK+DEBUFF", "ATTACK_DEFEND": "ATK+DEF",
    "BUFF": "BUFF", "DEBUFF": "DEBUFF", "STRONG_DEBUFF": "STRONG DEBUFF", "DEFEND": "DEF",
    "DEFEND_DEBUFF": "DEF+DEBUFF", "DEFEND_BUFF": "DEF+BUFF", "ESCAPE": "ESCAPE", "MAGIC": "MAGIC",
    "SLEEP": "SLEEP", "STUN": "STUN", "UNKNOWN": "UNKNOWN", "NONE": "NONE", "DEBUG": "(not shown yet)",
}
# Powers whose amount is meaningful even when it is -1.
SIGNED_POWERS = {"Strength", "Dexterity", "Focus"}
HAND_LETTERS = string.ascii_lowercase


def cost_text(cost):
    if cost == -1:
        return "X"
    if cost == -2:
        return "-"
    return str(cost)


def powers_text(powers):
    parts = []
    for power in powers:
        amount = power.get("amount", -1)
        if amount == -1 and power["id"] not in SIGNED_POWERS:
            parts.append(power["name"])
        else:
            parts.append(f"{power['name']} {amount}")
    return ", ".join(parts)


class Renderer:
    def __init__(self, catalog=None, card_text="combat"):
        """card_text: "combat" = full card text the first time a card shows in each combat,
        "first" = only the first time in the run, "always" = every time."""
        self.catalog = catalog or Catalog()
        self.card_text_mode = card_text
        self.seen = set()
        self.combat_seen = set()
        self.in_combat = False
        self.hand_labels = {}
        self.hand_turn = None
        self.path = []

    # ---------- shared pieces ----------

    def header(self, gs):
        potions = []
        for i, potion in enumerate(gs.get("potions", [])):
            if potion["id"] == "Potion Slot":
                potions.append(f"{i} -")
            else:
                potions.append(f"{i} {potion['name']}{'(T)' if potion.get('requires_target') else ''}")
        # The top bar shows the ascension level only when it is above 0.
        asc = f" A{gs['ascension_level']}" if gs.get("ascension_level") else ""
        return (f"F{gs['floor']} Act{gs['act']}{asc} | HP {gs['current_hp']}/{gs['max_hp']} | Gold {gs['gold']}"
                f" | Potions: {' '.join(potions) if potions else 'none'}")

    def visit(self, x, y, act=None):
        if act is not None and act != getattr(self, "path_act", act):
            self.path = []
        if act is not None:
            self.path_act = act
        if (x, y) not in self.path:
            self.path.append((x, y))

    def first_time(self, key):
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    def card_numbers(self, card):
        parts = []
        if card.get("damage", -1) >= 0:
            parts.append(f"{card['damage']} dmg")
        if card.get("block", -1) >= 0:
            parts.append(f"{card['block']} blk")
        if card.get("magic_number", -1) >= 0:
            parts.append(f"M{card['magic_number']}")
        return ", ".join(parts)

    def card_face(self, card):
        """Card text with the numbers currently shown on the card face."""
        version = self.catalog.card_version(card["id"], card.get("upgrades", 0))
        if version is None:
            return None
        # Cards outside combat (rewards, shop, deck) report -1 until the game computes them;
        # the card face then shows the catalog value.
        values = {}
        for key in ("damage", "block", "magic_number"):
            value = card.get(key, -1)
            values[key] = value if value is not None and value >= 0 else version.get(key)
        try:
            return version["template"].format(**values)
        except (KeyError, IndexError):
            return version["text"]

    def card_line(self, card, label, show_cost=True, always_text=False, in_hand=False):
        name = self.catalog.card_name(card["id"], card.get("upgrades", 0), card.get("name"))
        parts = [f"{label} {name}" if label != "" else name]
        if show_cost:
            parts.append(cost_text(card.get("cost", -2)))
        flags = []
        if card.get("ethereal"):
            flags.append("Ethereal")
        if card.get("exhausts"):
            flags.append("Exhaust")
        if in_hand and card.get("is_playable") is False:
            flags.append("can't play")
        if flags:
            parts.append(f"[{', '.join(flags)}]")
        key = ("card", card["id"], card.get("upgrades", 0))
        if self.card_text_mode == "combat" and self.in_combat:
            fresh = key not in self.combat_seen
            self.combat_seen.add(key)
            self.seen.add(key)
        else:
            fresh = self.first_time(key)
        show_text = always_text or self.card_text_mode == "always" or fresh
        face = self.card_face(card) if show_text else None
        if face:
            parts.append(f"- {face}")
        else:
            numbers = self.card_numbers(card)
            if numbers:
                parts.append(f"- {numbers}")
        return " ".join(parts)

    def relic_line(self, relic, always_text=False):
        line = relic["name"]
        if relic.get("counter", -1) >= 0:
            line += f" ({relic['counter']})"
        if always_text or self.first_time(("relic", relic["id"])):
            text = self.catalog.relic_text(relic["id"])
            if text:
                line += f" - {text}"
        return line

    # ---------- combat ----------

    def label_hand(self, combat):
        if combat["turn"] != self.hand_turn:
            self.hand_turn = combat["turn"]
            self.hand_labels = {}
        used = set(self.hand_labels.values())
        for card in combat["hand"]:
            if card["uuid"] not in self.hand_labels:
                if len(used) == len(HAND_LETTERS):
                    # A long draw loop used every letter: free those of cards that left the hand.
                    in_hand = {c["uuid"] for c in combat["hand"]}
                    self.hand_labels = {u: l for u, l in self.hand_labels.items() if u in in_hand}
                    used = set(self.hand_labels.values())
                letter = next(c for c in HAND_LETTERS if c not in used)
                self.hand_labels[card["uuid"]] = letter
                used.add(letter)
        return [self.hand_labels[c["uuid"]] for c in combat["hand"]]

    def monster_line(self, i, monster):
        name = f" {i} {monster['name']}"
        if monster.get("half_dead"):
            return f"{name} (reviving) {monster['current_hp']}/{monster['max_hp']}"
        if monster.get("is_gone"):
            return f"{name} (dead)"
        line = f"{name} {monster['current_hp']}/{monster['max_hp']}"
        if monster.get("block"):
            line += f" Blk {monster['block']}"
        intent = INTENT_NAMES.get(monster["intent"], monster["intent"])
        damage = monster.get("move_adjusted_damage", -1)
        if damage is not None and damage >= 0 and monster["intent"].startswith("ATTACK"):
            hits = monster.get("move_hits", 1)
            amount = f"{damage}x{hits}" if hits > 1 else str(damage)
            intent = intent.replace("ATK", f"ATK {amount}", 1)
        line += f" | intent {intent}"
        if monster.get("powers"):
            line += f" | {powers_text(monster['powers'])}"
        return line

    def combat(self, gs):
        combat = gs["combat_state"]
        player = combat["player"]
        room = ROOM_NAMES.get(gs.get("room_type"), gs.get("room_type"))
        me = f"== Combat T{combat['turn']} ({room}) == Energy {player['energy']}/{player.get('max_energy', '?')}"
        me += f" | Block {player['block']}"
        if player.get("powers"):
            me += f" | {powers_text(player['powers'])}"
        lines = [me, "Enemies:"]
        lines += [self.monster_line(i, m) for i, m in enumerate(combat["monsters"])]
        labels = self.label_hand(combat)
        lines.append(f"Hand ({len(combat['hand'])}/10):")
        # Listed in letter order: once cards come and go the game's hand order mixes the letters up.
        hand = sorted(zip(combat["hand"], labels), key=lambda pair: HAND_LETTERS.index(pair[1]))
        lines += [" " + self.card_line(card, label, in_hand=True) for card, label in hand]
        lines.append(f"Draw {len(combat['draw_pile'])} | Discard {len(combat['discard_pile'])}"
                     f" | Exhaust {len(combat['exhaust_pile'])}")
        counters = [self.relic_line(r) for r in gs.get("relics", []) if r.get("counter", -1) >= 0]
        if counters:
            lines.append("Relic counters: " + "; ".join(counters))
        return lines

    def pile(self, cards):
        """Pile contents sorted by name, never in draw order."""
        counts = {}
        for card in cards:
            name = self.catalog.card_name(card["id"], card.get("upgrades", 0), card.get("name"))
            counts[name] = counts.get(name, 0) + 1
        return ", ".join(f"{n} x{c}" if c > 1 else n for n, c in sorted(counts.items())) or "(empty)"

    # ---------- other screens ----------

    def event(self, gs):
        ss = gs["screen_state"]
        lines = [f"== Event: {ss.get('event_name', '?')} =="]
        if ss.get("body_text"):
            lines.append(ss["body_text"].strip())
        for option in ss.get("options", []):
            text = option["text"].strip()
            if option.get("disabled") or "choice_index" not in option:
                lines.append(f" - {text} [disabled]")
            else:
                lines.append(f" {option['choice_index']} {text}")
        return lines

    def map_rows(self, gs):
        nodes = {(n["x"], n["y"]): n for n in gs.get("map", [])}
        rows = {}
        for (x, y), node in sorted(nodes.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            children = ",".join(str(c["x"]) for c in node.get("children", []))
            mark = "*" if (x, y) in self.path else ""
            rows.setdefault(y, []).append(f"{x}{node['symbol']}{mark}>{children}")
        return [f"  {y + 1:>2}: " + "  ".join(rows[y]) for y in sorted(rows, reverse=True)]

    @staticmethod
    def map_legend():
        return [" Rows from the top (floor in act: column+room>next columns; * = visited).",
                " Rooms: M monster, E elite, ? unknown, $ shop, R rest, T treasure."]

    def map_screen(self, gs):
        ss = gs["screen_state"]
        current = ss.get("current_node")
        if getattr(self, "path_act", gs["act"]) != gs["act"]:
            self.path = []
        self.path_act = gs["act"]
        if current and current.get("y", -1) >= 0:
            self.visit(current["x"], current["y"], gs["act"])
        lines = [f"== Map Act{gs['act']} == Boss: {gs.get('act_boss', '?')}"]
        # The whole map once per act; after that it is one inspect away, like a human opening it.
        if self.first_time(("map", gs["act"])):
            lines += self.map_legend() + self.map_rows(gs)
        if ss.get("boss_available"):
            lines.append("Next: 0 Boss")
        else:
            nxt = [f"{i} {n['symbol']}(x{n['x']})" for i, n in enumerate(ss.get("next_nodes", []))]
            lines.append("Next (choose <n> or choose x<column>): " + "  ".join(nxt))
        return lines

    def card_reward(self, gs):
        ss = gs["screen_state"]
        deck = gs.get("deck", [])
        lines = [f"== Card Reward == Deck {len(deck)}: {self.pile(deck)}"]
        for i, card in enumerate(ss.get("cards", [])):
            lines.append(f" {i} " + self.card_line(card, "", always_text=True))
        if ss.get("bowl_available"):
            lines.append(f" {len(ss.get('cards', []))} Singing Bowl: +2 Max HP instead")
        return lines

    def combat_reward(self, gs):
        lines = ["== Rewards =="]
        for i, reward in enumerate(gs["screen_state"].get("rewards", [])):
            kind = reward["reward_type"]
            if kind in ("GOLD", "STOLEN_GOLD"):
                desc = f"{reward.get('gold')} Gold"
            elif kind == "RELIC":
                desc = "Relic: " + self.relic_line(reward["relic"], always_text=True)
            elif kind == "POTION":
                potion = reward["potion"]
                desc = f"Potion: {potion['name']} - {self.catalog.potion_text(potion['id']) or ''}".rstrip(" -")
            elif kind == "CARD":
                desc = "Card reward (choose to see the cards)"
            elif kind == "SAPPHIRE_KEY":
                desc = f"Sapphire Key (instead of {reward['link']['name']})"
            else:
                desc = kind.title()
            lines.append(f" {i} {desc}")
        return lines

    def shop(self, gs):
        # Same order and affordability rule as the mod's choice list: purge, cards, relics, potions.
        ss = gs["screen_state"]
        gold = gs["gold"]
        lines = ["== Shop =="]
        next_index = 0

        def tag(price):
            nonlocal next_index
            if price > gold:
                return " -", f"{price}g (can't afford)"
            next_index += 1
            return f" {next_index - 1}", f"{price}g"

        purge = None
        if ss.get("purge_available"):
            purge = tag(ss["purge_cost"])
        if ss.get("cards"):
            lines.append("Cards:")
        for item in ss.get("cards", []):
            i, price = tag(item["price"])
            lines.append(f"{i} [{price}] " + self.card_line(item, "", always_text=True))
        if ss.get("relics"):
            lines.append("Relics:")
        for item in ss.get("relics", []):
            i, price = tag(item["price"])
            lines.append(f"{i} [{price}] " + self.relic_line(item, always_text=True))
        if ss.get("potions"):
            lines.append("Potions:")
        for item in ss.get("potions", []):
            i, price = tag(item["price"])
            lines.append(f"{i} [{price}] {item['name']} - {self.catalog.potion_text(item['id']) or ''}")
        if purge:
            lines.append(f"{purge[0]} [{purge[1]}] Remove a card")
        lines.append("skip: leave the shop")
        return lines

    def rest(self, gs):
        lines = ["== Rest Site =="]
        for i, option in enumerate(gs.get("choice_list", [])):
            desc = option.title()
            if option == "rest":
                heal = min(int(gs["max_hp"] * 0.3), gs["max_hp"] - gs["current_hp"])
                desc += f" (heal {heal})"
            lines.append(f" {i} {desc}")
        return lines

    def boss_reward(self, gs):
        lines = ["== Boss Relic =="]
        for i, relic in enumerate(gs["screen_state"].get("relics", [])):
            lines.append(f" {i} " + self.relic_line(relic, always_text=True))
        return lines

    def grid(self, gs):
        ss = gs["screen_state"]
        purpose = ("upgrade" if ss.get("for_upgrade") else "transform" if ss.get("for_transform")
                   else "remove" if ss.get("for_purge") else "select")
        count = "any number of" if ss.get("any_number") else str(ss.get("num_cards", 1))
        lines = self.enemies_brief(gs) + [f"== Choose {count} card(s) to {purpose} =="]
        for i, card in enumerate(ss.get("cards", [])):
            lines.append(f" {i} " + self.card_line(card, "", show_cost=True))
        if ss.get("selected_cards"):
            lines.append("Selected: " + self.pile(ss["selected_cards"]))
        if ss.get("confirm_up"):
            lines.append("Selection complete: confirm to finish")
        return lines

    def enemies_brief(self, gs):
        combat = gs.get("combat_state")
        if not combat:
            return []
        player = combat["player"]
        lines = [f"(in combat T{combat['turn']}: Energy {player['energy']}/{player.get('max_energy', '?')}, Block {player['block']})"]
        return lines + [self.monster_line(i, m) for i, m in enumerate(combat["monsters"])]

    def hand_select(self, gs):
        ss = gs["screen_state"]
        count = f"up to {ss.get('max_cards')}" if ss.get("can_pick_zero") or ss.get("max_cards", 1) > 1 else "1"
        lines = self.enemies_brief(gs) + [f"== Choose {count} card(s) from your hand"
                 f"{' (at least 1)' if not ss.get('can_pick_zero') and ss.get('max_cards', 1) > 1 else ''} =="]
        for i, card in enumerate(ss.get("hand", [])):
            lines.append(f" {i} " + self.card_line(card, ""))
        if ss.get("selected"):
            lines.append("Selected: " + self.pile(ss["selected"]))
        return lines

    def game_over(self, gs):
        ss = gs["screen_state"]
        return [f"== Game Over: {'VICTORY' if ss.get('victory') else 'DEFEAT'} == Floor {gs['floor']} | Score {ss.get('score')}"]

    SCREENS = {"EVENT": event, "MAP": map_screen, "CARD_REWARD": card_reward, "COMBAT_REWARD": combat_reward,
               "SHOP_SCREEN": shop, "REST": rest, "BOSS_REWARD": boss_reward, "GRID": grid,
               "HAND_SELECT": hand_select, "GAME_OVER": game_over}

    def render(self, message):
        if not message.get("in_game"):
            return "Main menu."
        gs = message["game_state"]
        in_combat = bool(gs.get("combat_state"))
        if in_combat and not self.in_combat:
            self.combat_seen = set()
        self.in_combat = in_combat
        lines = [self.header(gs)]
        screen = gs.get("screen_type")
        if screen in self.SCREENS:
            lines += self.SCREENS[screen](self, gs)
        elif gs.get("combat_state"):
            lines += self.combat(gs)
        else:
            lines += self.generic(gs, message.get("available_commands", []))
        return "\n".join(lines)

    def generic(self, gs, commands):
        """Screens with no special view (shop room, chest, ...): list the raw choices."""
        names = {"SHOP_ROOM": "Shop room", "CHEST": "Treasure", "COMPLETE": "Room cleared", "NONE": "Waiting"}
        lines = [f"== {names.get(gs.get('screen_type'), gs.get('screen_type'))} =="]
        lines += [f" {i} {choice}" for i, choice in enumerate(gs.get("choice_list", []))]
        # In the action language, confirm covers proceed and skip covers leave/cancel/return.
        exits = sorted({"confirm" if c in ("proceed", "confirm") else "skip" for c in commands
                        if c in ("proceed", "confirm", "skip", "leave", "cancel", "return")})
        if exits:
            lines.append("Or: " + ", ".join(exits))
        return lines
