"""Builders for made-up CommunicationMod messages, shaped like GameStateConverter's output."""
import copy
import itertools

_uuid = itertools.count(1)

SLOT = {"id": "Potion Slot", "name": "Potion Slot", "requires_target": False, "can_use": False, "can_discard": False}


def card(card_id, name=None, cost=1, type="ATTACK", upgrades=0, playable=True, target=None, uuid=None, **values):
    from bridge.catalog import Catalog
    known = _catalog().cards.get(card_id)
    if name is None:
        name = _catalog().card_name(card_id, upgrades, card_id)
    if known and target is None:
        target = known["target"] in ("ENEMY", "SELF_AND_ENEMY")
    if known:
        type = known["type"]
    result = {"id": card_id, "name": name, "cost": cost, "type": type, "upgrades": upgrades, "rarity": "COMMON",
              "uuid": uuid or f"u{next(_uuid)}", "is_playable": playable, "has_target": bool(target),
              "exhausts": False, "ethereal": False}
    result.update(values)
    return result


_cat = None


def _catalog():
    global _cat
    if _cat is None:
        from bridge.catalog import Catalog
        _cat = Catalog()
    return _cat


def monster(name, hp, max_hp=None, intent="ATTACK", damage=-1, hits=1, block=0, gone=False, half_dead=False,
            powers=(), monster_id=None):
    return {"id": monster_id or name.replace(" ", ""), "name": name, "current_hp": hp, "max_hp": max_hp or hp,
            "intent": intent, "move_id": 1, "move_base_damage": damage, "move_adjusted_damage": damage,
            "move_hits": hits, "block": block, "is_gone": gone, "half_dead": half_dead, "powers": list(powers)}


def power(power_id, amount, name=None):
    return {"id": power_id, "name": name or power_id, "amount": amount}


def potion(potion_id, name=None, target=False):
    return {"id": potion_id, "name": name or potion_id, "requires_target": target, "can_use": True, "can_discard": True}


def message(screen="NONE", screen_state=None, commands=("state",), choices=None, combat=None, **gs):
    state = {"screen_type": screen, "screen_state": screen_state or {}, "seed": 42, "floor": 5, "act": 1,
             "act_boss": "Hexaghost", "current_hp": 60, "max_hp": 80, "gold": 150, "class": "IRONCLAD",
             "ascension_level": 0, "room_type": "MonsterRoom", "room_phase": "COMBAT" if combat else "COMPLETE",
             "potions": [dict(SLOT), dict(SLOT), dict(SLOT)], "relics": [{"id": "Burning Blood", "name": "Burning Blood", "counter": -1}],
             "deck": [card("Strike_R") for _ in range(5)] + [card("Defend_R", type="SKILL") for _ in range(4)] + [card("Bash", cost=2)],
             "map": [], "keys": {"ruby": False, "emerald": False, "sapphire": False}}
    if choices is not None:
        state["choice_list"] = list(choices)
    if combat is not None:
        state["combat_state"] = combat
    state.update(gs)
    return {"available_commands": list(commands), "ready_for_command": True, "in_game": True, "game_state": state}


def combat(hand, monsters, energy=3, turn=1, block=0, powers=(), draw=5, discard=0, exhaust=0):
    return {"hand": hand, "monsters": monsters, "turn": turn,
            "player": {"energy": energy, "max_energy": 3, "block": block, "powers": list(powers),
                       "current_hp": 60, "max_hp": 80, "orbs": []},
            "draw_pile": [card("Strike_R") for _ in range(draw)], "discard_pile": [card("Strike_R") for _ in range(discard)],
            "exhaust_pile": [card("Strike_R") for _ in range(exhaust)], "limbo": [], "cards_discarded_this_turn": 0,
            "times_damaged": 0}


def combat_message(hand, monsters, commands=("play", "end", "potion", "state"), **kw):
    combat_kw = {k: kw.pop(k) for k in list(kw) if k in ("energy", "turn", "block", "powers", "draw", "discard", "exhaust")}
    return message("NONE", commands=commands, combat=combat(hand, monsters, **combat_kw), **kw)


class ScriptedGame:
    """A fake link. `step(message, command)` returns the next message or {"error": ...}."""

    def __init__(self, first, step):
        self.message = first
        self.step = step
        self.sent = []

    def get(self):
        return copy.deepcopy(self.message)

    def send(self, command):
        if command.startswith("wait"):
            return copy.deepcopy(self.message)
        self.sent.append(command)
        reply = self.step(copy.deepcopy(self.message), command)
        if "error" not in reply:
            self.message = reply
        return copy.deepcopy(reply)


class SimpleCombat:
    """Tiny rules engine: playing a card removes it, spends energy and deals its damage to the target.

    Enough to test the action language without the real game. Extra effects per card id can be
    added with `effects[card_id] = fn(message, card, target)`.
    """

    def __init__(self, effects=None):
        self.effects = effects or {}

    def __call__(self, msg, command):
        gs = msg["game_state"]
        cs = gs.get("combat_state")
        words = command.split()
        if words[0] == "play":
            if not cs:
                return {"error": "Invalid command: play"}
            i = int(words[1]) - 1
            if i < 0 or i >= len(cs["hand"]):
                return {"error": f"Invalid card index {words[1]}"}
            c = cs["hand"][i]
            target = int(words[2]) if len(words) > 2 else None
            if c["has_target"] and (target is None or target >= len(cs["monsters"]) or cs["monsters"][target]["is_gone"]):
                return {"error": "Invalid target"}
            if not c["has_target"] and target is not None:
                return {"error": "Card does not take a target"}
            cost = c["cost"] if c["cost"] >= 0 else cs["player"]["energy"]
            if cost > cs["player"]["energy"] or not c["is_playable"]:
                return {"error": "Card can't be played"}
            cs["player"]["energy"] -= cost
            del cs["hand"][i]
            if c.get("damage", -1) >= 0:
                victims = [cs["monsters"][target]] if target is not None else [m for m in cs["monsters"] if not m["is_gone"]]
                for m in victims:
                    m["current_hp"] = max(0, m["current_hp"] - c["damage"])
                    if m["current_hp"] == 0:
                        m["is_gone"] = True
            if c.get("block", -1) >= 0:
                cs["player"]["block"] += c["block"]
            if c["id"] in self.effects:
                msg = self.effects[c["id"]](msg, c, target) or msg
            if all(m["is_gone"] and not m.get("half_dead") for m in cs["monsters"]):
                msg = message("COMBAT_REWARD", {"rewards": [{"reward_type": "GOLD", "gold": 15}]},
                              commands=("choose", "proceed", "state"), choices=["gold"])
            return msg
        if words[0] == "end":
            cs["turn"] += 1
            cs["player"]["energy"] = 3
            cs["hand"] = [card("Strike_R", damage=6) for _ in range(5)]
            return msg
        if words[0] in ("choose", "proceed") and gs["screen_type"] == "COMBAT_REWARD":
            if words[0] == "choose":
                del gs["screen_state"]["rewards"][int(words[1])]
                del gs["choice_list"][int(words[1])]
                return msg
            return message("MAP", {"next_nodes": [{"x": 1, "y": 5, "symbol": "M"}, {"x": 2, "y": 5, "symbol": "?"}],
                                   "boss_available": False}, commands=("choose",), choices=["x=1", "x=2"])
        if words[0] == "potion":
            slot = int(words[2])
            if gs["potions"][slot]["id"] == "Potion Slot":
                return {"error": "No potion in that slot"}
            gs["potions"][slot] = dict(SLOT)
            return msg
        return {"error": f"Invalid command: {command}"}
