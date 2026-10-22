"""One run as the LLM sees it: text actions in, text state out.

Implements docs/interface-spec.md section 3: the action language, whole-turn sequences that
stop when something unplanned happens, auto-handling of steps that have no choice, and the
per-run log.
"""
import datetime
import json
import pathlib
import re
import socket
import time

from bridge.render import Renderer

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_ACTIONS = 30
DEFAULT_STOP_ON = {"draw", "choice", "spawn"}
# Cards that cost HP; `repeat` never plays them unless they are named.
SELF_DAMAGE = {"Hemokinesis", "Offering", "Bloodletting", "J.A.X.", "Combust", "Brutality"}
CHOICE_SCREENS = {"HAND_SELECT", "GRID", "CARD_REWARD"}
ROOMS = {"M": "Monster", "E": "Elite", "?": "Unknown", "$": "Shop", "R": "Rest", "T": "Treasure"}


class ActionError(Exception):
    pass


class LinkClient:
    """Talks to bridge/game_link.py over localhost."""

    def __init__(self, host="127.0.0.1", port=8765):
        self.address = (host, port)
        self.connect()

    def connect(self):
        self.sock = socket.create_connection(self.address, timeout=60)
        self.file = self.sock.makefile("rwb")

    def _request(self, request):
        for attempt in (1, 2):
            try:
                self.file.write((json.dumps(request) + "\n").encode("utf-8"))
                self.file.flush()
                line = self.file.readline()
                if not line:
                    raise ConnectionError("the game link closed the connection")
                return json.loads(line)
            except OSError:
                # The game (and its link) may have been restarted: reconnect once.
                if attempt == 2:
                    raise
                self.connect()

    def send(self, command):
        return self._request({"send": command})

    def get(self):
        return self._request({"get": True})


def game_state(message):
    return message.get("game_state", {}) if message else {}


def combat_of(message):
    return game_state(message).get("combat_state")


class Session:
    def __init__(self, link, renderer=None):
        self.link = link
        self.renderer = renderer or Renderer()
        self.message = link.get()
        self.skipped_card_floor = None
        self.left_shop_floor = None
        self.run_dir = None
        self.step = 0

    # ---------- logging ----------

    def start_log(self, seed, resume=False):
        self.step = 0
        if resume:
            earlier = sorted((ROOT / "runs").glob(f"*_seed-{seed}"))
            if earlier:
                self.run_dir = earlier[-1]
                self.step = len(list((self.run_dir / "raw").glob("*.json")))
                return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = ROOT / "runs" / f"{stamp}_seed-{seed}"
        (self.run_dir / "raw").mkdir(parents=True, exist_ok=True)

    def log(self, **entry):
        if self.run_dir is None:
            return
        self.step += 1
        entry = {"step": self.step, "t": datetime.datetime.now().isoformat(timespec="seconds"),
                 "floor": game_state(self.message).get("floor"),
                 "screen": game_state(self.message).get("screen_type"), **entry}
        (self.run_dir / "raw" / f"{self.step:05d}.json").write_text(json.dumps(self.message), encoding="utf-8")
        with open(self.run_dir / "run.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---------- talking to the game ----------

    def send(self, command):
        reply = self.link.send(command)
        if "error" in reply:
            raise ActionError(reply["error"])
        self.message = reply
        self.wait_for_intents()
        return reply

    def wait_for_intents(self):
        """At the start of a combat the game can report intents before they are rolled."""
        for _ in range(5):
            combat = combat_of(self.message)
            if not combat or not any(m["intent"] == "DEBUG" and not m["is_gone"] for m in combat["monsters"]):
                return
            reply = self.link.send("wait 30")
            if "error" not in reply:
                self.message = reply

    def available(self):
        return self.message.get("available_commands", [])

    def text(self):
        return self.renderer.render(self.message)

    # ---------- tools ----------

    def start_run(self, seed=None, overwrite=False):
        if self.message.get("in_game"):
            raise ActionError("A run is in progress. Finish it, or abandon it from the game menu first.")
        if "continue" in self.available() and not overwrite:
            raise ActionError("There is a saved run. Use continue_run to resume it, "
                              "or start_run with overwrite to replace it.")
        command = "start ironclad 0" + (f" {seed}" if seed else "")
        self.renderer = Renderer(self.renderer.catalog, self.renderer.card_text_mode)
        self.send(command)
        self.start_log(game_state(self.message).get("seed"))
        result = []
        auto = self.safe_auto_handle(result)
        self.log(input=f"start_run {seed or ''}".strip(), auto=auto)
        return self.compose(result, auto)

    def continue_run(self):
        if self.message.get("in_game"):
            # Attaching to a run that is already open in the game: keep logging into its directory.
            self.message = self.link.get()
            if self.run_dir is None:
                self.start_log(game_state(self.message).get("seed"), resume=True)
            return self.text()
        for _ in range(15):
            # Right after the game starts the main menu can take a few seconds to offer Continue.
            if "continue" in self.available() or self.message.get("in_game"):
                break
            time.sleep(1)
            self.message = self.link.get()
        if "continue" not in self.available():
            raise ActionError("There is no saved run to continue.")
        self.renderer = Renderer(self.renderer.catalog, self.renderer.card_text_mode)
        self.send("continue")
        self.start_log(game_state(self.message).get("seed"), resume=True)
        result = []
        auto = self.safe_auto_handle(result)
        self.log(input="continue_run", auto=auto)
        return self.compose(result, auto)

    def get_state(self):
        self.message = self.link.get()
        return self.text()

    def note(self, text, tag=None):
        self.log(note=text, tag=tag)
        return "Noted."

    def act(self, actions, stop_on=None):
        stop_on = set(stop_on) if stop_on else DEFAULT_STOP_ON
        steps = [s.strip() for s in re.split(r"[;\n]", actions) if s.strip()]
        if not steps:
            return "ERR no actions given.\n" + self.text()
        done, result = [], []
        self.drawn = []
        stop_reason = None
        try:
            for i, step in enumerate(steps):
                words = step.split()
                if words[0] == "repeat":
                    count, stop_reason = self.repeat(words[1:], stop_on, result)
                    result.append(f"\"{step}\" played {count} card(s).")
                    done.append(f"{step} ({count}x)")
                else:
                    stop_reason = self.do(words, stop_on, result)
                    done.append(step)
                if len(done) >= MAX_ACTIONS:
                    stop_reason = f"limit of {MAX_ACTIONS} actions"
                if stop_reason:
                    if i < len(steps) - 1:
                        result.insert(0, f"Done {i + 1}/{len(steps)}, stopped after \"{step}\": {stop_reason}.")
                    else:
                        result.insert(0, f"Done {len(steps)}/{len(steps)} ({stop_reason}).")
                    break
            else:
                result.insert(0, f"Done {len(steps)}/{len(steps)}.")
        except ActionError as e:
            result.insert(0, f"ERR \"{step}\": {e}. Nothing after this was run.")
        auto = self.safe_auto_handle(result)
        self.log(input=actions, executed=len(done), stop_reason=stop_reason, auto=auto)
        return self.compose(result, auto)

    def safe_auto_handle(self, result):
        try:
            return self.auto_handle()
        except ActionError as e:
            result.append(f"ERR during automatic steps: {e}.")
            return []

    def compose(self, result, auto):
        # One line for all cards drawn during the sequence instead of one per play.
        # Cards drawn during the sequence that are still in hand (not the ones already played or discarded).
        hand = {c["uuid"] for c in (combat_of(self.message) or {}).get("hand", [])}
        drawn = [name for uuid, name in getattr(self, "drawn", []) if uuid in hand]
        lines = list(result)
        if drawn:
            lines.insert(1 if lines else 0, "New in hand: " + ", ".join(drawn) + ".")
        if auto:
            lines.append("[auto] " + ", ".join(auto))
        lines.append(self.text())
        return "\n".join(lines)

    # ---------- single actions ----------

    def do(self, words, stop_on, result):
        verb, args = words[0].lower(), words[1:]
        before = self.message
        if verb == "play":
            self.send(self.play_command(args))
        elif verb == "end":
            self.send("end")
            return None
        elif verb == "potion":
            self.send(self.potion_command(args))
        elif verb == "drop":
            self.send(f"potion discard {self.potion_slot(args)}")
        elif verb == "choose":
            screen = game_state(before).get("screen_type")
            picked = self.picked_card(before, args)
            self.choose(args)
            if picked:
                result.append(f"Selected {picked}.")
            if screen == "SHOP_SCREEN" and game_state(self.message).get("screen_type") == "SHOP_SCREEN":
                result.append("Bought. Shop numbers have changed.")
                return "shop numbers changed"
        elif verb == "confirm":
            self.send(self.pick_available("confirm", "proceed"))
        elif verb == "skip":
            if game_state(before).get("screen_type") == "CARD_REWARD":
                self.skipped_card_floor = game_state(before).get("floor")
            self.send(self.pick_available("skip", "cancel", "leave", "return", "proceed"))
            if game_state(before).get("screen_type") == "SHOP_SCREEN":
                self.left_shop_floor = game_state(before).get("floor")
            if game_state(before).get("screen_type") == "SHOP_SCREEN" and game_state(self.message).get("screen_type") == "SHOP_ROOM" \
                    and "proceed" in self.available():
                self.send("proceed")
        else:
            raise ActionError(f"unknown action '{verb}'")
        return self.check_stop(before, stop_on, result)

    def picked_card(self, message, args):
        gs = game_state(message)
        ss = gs.get("screen_state") or {}
        cards = ss.get("cards") if gs.get("screen_type") == "GRID" else ss.get("hand") if gs.get("screen_type") == "HAND_SELECT" else None
        if not cards or not args or not args[0].isdigit() or int(args[0]) >= len(cards):
            return None
        c = cards[int(args[0])]
        return self.renderer.catalog.card_name(c["id"], c.get("upgrades", 0), c.get("name"))

    def potion_slot(self, args):
        potions = game_state(self.message).get("potions", [])
        if not args or not args[0].isdigit():
            raise ActionError("give the potion slot number")
        slot = int(args[0])
        if slot >= len(potions) or potions[slot]["id"] == "Potion Slot":
            raise ActionError(f"no potion in slot {slot}")
        return slot

    def potion_command(self, args):
        slot = self.potion_slot(args)
        potion = game_state(self.message)["potions"][slot]
        if not potion.get("requires_target"):
            return f"potion use {slot}"
        target = self.check_target(args[1] if len(args) > 1 else None, potion["name"])
        return f"potion use {slot} {target}"

    def check_target(self, target, what):
        """A living enemy's index; the only living enemy when none is given."""
        combat = combat_of(self.message)
        if not combat:
            raise ActionError(f"{what} needs an enemy, and there is no combat")
        alive = [j for j, m in enumerate(combat["monsters"]) if not m["is_gone"]]
        if target is None:
            if len(alive) != 1:
                raise ActionError(f"{what} needs a target")
            return alive[0]
        if not target.isdigit() or int(target) not in alive:
            raise ActionError(f"enemy {target} is not a living enemy (living: {', '.join(map(str, alive))})")
        return int(target)

    def pick_available(self, *names):
        for name in names:
            if name in self.available():
                return name
        raise ActionError(f"none of {', '.join(names)} is possible here")

    def choose(self, args):
        if not args or not args[0].isdigit():
            raise ActionError("choose needs a number")
        gs = game_state(self.message)
        choices = gs.get("choice_list")
        if choices is not None and int(args[0]) >= len(choices):
            raise ActionError(f"choose 0 to {len(choices) - 1}" if choices else "nothing to choose here")
        if gs.get("screen_type") == "MAP" and gs["screen_state"].get("boss_available"):
            self.send("choose boss")
        elif gs.get("screen_type") == "MAP":
            self.remember_node(gs, int(args[0]))
            self.send(f"choose {args[0]}")
        else:
            self.send(f"choose {args[0]}")

    def remember_node(self, gs, i):
        nodes = gs["screen_state"].get("next_nodes", [])
        if i < len(nodes):
            self.renderer.visit(nodes[i]["x"], nodes[i]["y"], gs["act"])

    def hand_index(self, ref):
        combat = combat_of(self.message)
        if not combat:
            raise ActionError("not in combat")
        hand = combat["hand"]
        labels = self.renderer.label_hand(combat)
        if ref in labels:
            return labels.index(ref)
        name = ref.lower()
        for i, card in enumerate(hand):
            card_name = self.renderer.catalog.card_name(card["id"], card.get("upgrades", 0), card.get("name"))
            if name in (card["id"].lower(), card_name.lower(), card_name.lower().rstrip("+")) and card.get("is_playable"):
                return i
        raise ActionError(f"no card '{ref}' in hand")

    def play_command(self, args):
        if not args:
            raise ActionError("play needs a card")
        # Card names can have spaces: the target, if any, is the last word when it is a number.
        target = args[-1] if len(args) > 1 and args[-1].isdigit() else None
        ref = " ".join(args[:-1] if target else args)
        i = self.hand_index(ref)
        card = combat_of(self.message)["hand"][i]
        if not card.get("is_playable"):
            raise ActionError(f"{card['name']} can't be played now")
        if card.get("has_target"):
            return f"play {i + 1} {self.check_target(target, card['name'])}"
        return f"play {i + 1}"

    def repeat(self, args, stop_on, result):
        """repeat play <Attack|Skill|Power|cost0|name> [target]"""
        if not args or args[0] != "play" or len(args) < 2:
            raise ActionError("use: repeat play <Attack|Skill|Power|cost0|card name> [target]")
        target = args[-1] if len(args) > 2 and args[-1].isdigit() else None
        rule = " ".join(args[1:-1] if target else args[1:]).lower()
        count = 0
        while count < MAX_ACTIONS:
            combat = combat_of(self.message)
            if not combat or "play" not in self.available():
                return count, None
            pick = None
            for card in combat["hand"]:
                name = self.renderer.catalog.card_name(card["id"], card.get("upgrades", 0), card.get("name"))
                if not card.get("is_playable"):
                    continue
                named = rule in (card["id"].lower(), name.lower(), name.lower().rstrip("+"))
                if card["id"] in SELF_DAMAGE and not named:
                    continue
                if (named or card["type"].lower() == rule or (rule == "cost0" and card["cost"] == 0)):
                    pick = card
                    break
            if pick is None:
                return count, None
            label = self.renderer.label_hand(combat)[combat["hand"].index(pick)]
            if pick.get("has_target") and target is not None and combat["monsters"][int(target)]["is_gone"]:
                return count, f"target {target} is dead"
            stop = self.do(["play", label] + ([target] if target else []), stop_on - {"draw"}, result)
            count += 1
            if stop:
                return count, stop
        return count, f"limit of {MAX_ACTIONS} actions"

    def check_stop(self, before, stop_on, result):
        gs = game_state(self.message)
        if gs.get("screen_type") == "GAME_OVER":
            return "game over"
        old, new = combat_of(before), combat_of(self.message)
        if old and not new or (old and gs.get("screen_type") == "COMBAT_REWARD"):
            return "combat won"
        if not new:
            return None
        if "choice" in stop_on and gs.get("screen_type") in CHOICE_SCREENS \
                and gs.get("screen_type") != game_state(before).get("screen_type"):
            return "a choice is needed"
        if old:
            if "spawn" in stop_on and len(new["monsters"]) != len(old["monsters"]):
                result.append("Enemies changed.")
                return "enemies changed"
            old_ids = {c["uuid"] for c in old["hand"]}
            added = [c for c in new["hand"] if c["uuid"] not in old_ids]
            if added:
                self.drawn += [(c["uuid"], self.renderer.catalog.card_name(c["id"], c.get("upgrades", 0), c.get("name")))
                               for c in added]
                if "draw" in stop_on:
                    return "new cards in hand, replan"
            if all(m["is_gone"] for m in new["monsters"]):
                return "combat won"
        return None

    # ---------- auto-handling (steps with no choice) ----------

    def auto_handle(self):
        done = []
        for _ in range(20):
            gs = game_state(self.message)
            screen = gs.get("screen_type")
            if screen == "COMBAT_REWARD":
                rewards = gs["screen_state"].get("rewards", [])
                free_slots = sum(1 for p in gs.get("potions", []) if p["id"] == "Potion Slot")
                pick = None
                for i, reward in enumerate(rewards):
                    kind = reward["reward_type"]
                    if kind in ("GOLD", "STOLEN_GOLD", "RELIC") or (kind == "POTION" and free_slots > 0):
                        pick = (i, reward)
                        break
                if pick:
                    i, reward = pick
                    self.send(f"choose {i}")
                    done.append(self.describe_reward(reward))
                    continue
                waiting = [r for r in rewards if not (r["reward_type"] == "CARD" and self.skipped_card_floor == gs["floor"])]
                cards = [i for i, r in enumerate(rewards) if r["reward_type"] == "CARD" and r in waiting]
                if cards:
                    # Opening the card reward is not a choice yet: show the cards right away.
                    self.send(f"choose {cards[0]}")
                    done.append("opened card reward")
                    continue
                if not waiting and "proceed" in self.available():
                    self.send("proceed")
                    continue
                return done
            if screen == "SHOP_ROOM" and "choose" in self.available() and not self.left_shop_floor == gs.get("floor"):
                self.send("choose 0")
                done.append("went to the merchant")
                continue
            if screen == "CHEST" and not gs["screen_state"].get("chest_open"):
                self.send("choose 0")
                done.append("opened chest")
                continue
            ss = gs.get("screen_state") or {}
            if screen == "MAP" and ss.get("boss_available") and gs.get("choice_list") == ["boss"]:
                self.send("choose boss")
                done.append("only one path: Boss")
                continue
            if screen == "MAP" and len(ss.get("next_nodes", [])) == 1 and not ss.get("boss_available"):
                node = ss["next_nodes"][0]
                self.remember_node(gs, 0)
                self.send("choose 0")
                done.append(f"only one path: F{gs['floor'] + 1} {ROOMS.get(node['symbol'], node['symbol'])}")
                continue
            choices = gs.get("choice_list")
            if screen == "EVENT" and choices and len(choices) == 1:
                option = next((o["text"] for o in ss.get("options", []) if "choice_index" in o), choices[0])
                self.send("choose 0")
                done.append(f"event {ss.get('event_name', '')}: {option}".replace("event : ", "event: "))
                continue
            if screen == "REST" and choices and len(choices) == 1:
                self.send("choose 0")
                done.append(f"rest site: {choices[0]} (only option)")
                continue
            if screen == "GRID" and ss.get("confirm_up") and not ss.get("any_number") \
                    and len(ss.get("selected_cards", [])) == ss.get("num_cards", 1) and "confirm" in self.available():
                purpose = "upgraded" if ss.get("for_upgrade") else "transformed" if ss.get("for_transform") \
                    else "removed" if ss.get("for_purge") else "selected"
                names = self.renderer.pile(ss["selected_cards"])
                self.send("confirm")
                done.append(f"{purpose} {names}")
                continue
            if screen == "SHOP_SCREEN" and choices == [] and self.left_shop_floor != gs.get("floor"):
                self.left_shop_floor = gs.get("floor")
                self.send(self.pick_available("leave", "cancel", "return", "skip"))
                done.append("left the shop (nothing affordable)")
                continue
            if screen not in ("GAME_OVER", "SHOP_SCREEN", "GRID", "HAND_SELECT") and not combat_of(self.message) \
                    and "proceed" in self.available() and "choose" not in self.available():
                self.send("proceed")
                continue
            return done
        return done

    @staticmethod
    def describe_reward(reward):
        kind = reward["reward_type"]
        if kind in ("GOLD", "STOLEN_GOLD"):
            return f"+{reward.get('gold')} Gold"
        if kind == "RELIC":
            return f"relic {reward['relic']['name']}"
        if kind == "POTION":
            return f"potion {reward['potion']['name']}"
        return kind.lower()

    # ---------- inspect ----------

    def inspect(self, what):
        gs = game_state(self.message)
        combat = gs.get("combat_state") or {}
        words = what.strip().split(maxsplit=1) or [""]
        key, arg = words[0].lower(), (words[1] if len(words) > 1 else "")
        cat = self.renderer.catalog
        if key == "deck":
            return "Deck: " + self.renderer.pile(gs.get("deck", []))
        if key in ("draw", "discard", "exhaust"):
            return f"{key.title()} pile: " + self.renderer.pile(combat.get(f"{key}_pile", []))
        if key == "relics":
            return "\n".join(self.renderer.relic_line(r, always_text=True) for r in gs.get("relics", []))
        if key == "potions":
            return "\n".join(f"{i} {p['name']} - {cat.potion_text(p['id']) or ''}" for i, p in enumerate(gs.get("potions", [])))
        if key == "map":
            return "\n".join(self.renderer.map_rows(gs))
        if key == "card":
            for card_id, card in cat.cards.items():
                if arg.lower().rstrip("+") in (card_id.lower(), card["base"]["name"].lower()):
                    up = card.get("upgraded")
                    return f"{card['base']['name']} ({card['type'].title()}, {card['rarity'].title()}): {card['base']['text']}" + (
                        f"\nUpgraded: {up['text']}" + (f" Cost {up['cost']}." if up["cost"] != card["base"]["cost"] else "") if up else "")
            return f"Unknown card '{arg}'."
        if key == "relic":
            for relic in cat.relics.values():
                if arg.lower() in (relic["id"].lower(), relic["name"].lower()):
                    return f"{relic['name']}: {relic['text']}"
            return f"Unknown relic '{arg}'."
        if key == "enemy" and arg.isdigit() and combat:
            if int(arg) >= len(combat["monsters"]):
                return f"No enemy {arg}."
            monster = combat["monsters"][int(arg)]
            return self.renderer.monster_line(int(arg), monster)
        return "Use: deck, draw, discard, exhaust, relics, potions, map, card <name>, relic <name>, enemy <n>."
