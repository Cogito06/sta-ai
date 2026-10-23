"""The action language and auto-handling against a small scripted game."""
import unittest

from bridge.session import MAX_ACTIONS, ActionError, Session
from tests.states import SLOT, ScriptedGame, SimpleCombat, card, combat_message, message, monster, potion


def strike():
    return card("Strike_R", damage=6)


def defend():
    return card("Defend_R", type="SKILL", block=5)


def session_for(first, step=None):
    game = ScriptedGame(first, step or SimpleCombat())
    return Session(game), game


class PlayTest(unittest.TestCase):
    def test_two_enemies_need_a_target(self):
        session, game = session_for(combat_message([strike()], [monster("Louse", 12), monster("Louse", 12)]))
        out = session.act("play a")
        self.assertIn("needs a target", out)
        self.assertEqual(game.sent, [])

    def test_single_living_enemy_is_the_default_target(self):
        first = combat_message([strike()], [monster("Louse", 0, 12, gone=True), monster("Louse", 12)])
        session, game = session_for(first)
        session.act("play a")
        self.assertEqual(game.sent, ["play 1 1"])

    def test_dead_target_is_refused_before_reaching_the_game(self):
        first = combat_message([strike(), strike()], [monster("Louse", 0, 12, gone=True), monster("Louse", 12)])
        session, game = session_for(first)
        out = session.act("play a 0")
        self.assertIn("ERR", out)
        self.assertEqual(game.sent, [])

    def test_target_out_of_range_is_refused(self):
        session, game = session_for(combat_message([strike()], [monster("Louse", 12)]))
        out = session.act("play a 3")
        self.assertIn("ERR", out)
        self.assertEqual(game.sent, [])

    def test_letters_stay_with_cards_after_playing(self):
        session, game = session_for(combat_message([strike(), defend(), strike()], [monster("Cultist", 50)]))
        session.act("play a 0; play c 0; play b")
        self.assertEqual(game.sent, ["play 1 0", "play 2 0", "play 1"])

    def test_names_and_letters_mix(self):
        session, game = session_for(combat_message([defend(), strike()], [monster("Cultist", 50)]))
        session.act("play Strike 0; play a")
        self.assertEqual(game.sent, ["play 2 0", "play 1"])

    def test_name_with_spaces_and_target(self):
        hand = [strike(), card("Pommel Strike", damage=9, magic_number=1)]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50), monster("Cultist", 50)]))
        session.act("play pommel strike 1")
        self.assertEqual(game.sent, ["play 2 1"])

    def test_unknown_card_and_unknown_verb(self):
        session, game = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        self.assertIn("no card 'Bludgeon'", session.act("play Bludgeon"))
        self.assertIn("unknown action 'dance'", session.act("dance"))
        self.assertEqual(game.sent, [])

    def test_error_stops_the_rest_of_the_sequence(self):
        session, game = session_for(combat_message([strike(), strike()], [monster("Cultist", 50)]))
        out = session.act("play a 0; play z 0; play b 0")
        self.assertIn("Nothing after this was run", out)
        self.assertEqual(game.sent, ["play 1 0"])

    def test_unplayable_card_by_letter(self):
        hand = [card("Wound", cost=-2, type="STATUS", playable=False), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]))
        self.assertIn("can't be played", session.act("play a"))

    def test_not_enough_energy_reports_the_game_error(self):
        hand = [card("Bash", cost=2, damage=8, magic_number=2), card("Bash", cost=2, damage=8, magic_number=2)]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]))
        out = session.act("play a 0; play b 0")
        self.assertIn("ERR \"play b 0\"", out)

    def test_killing_the_last_enemy_stops_the_sequence(self):
        session, game = session_for(combat_message([strike(), strike()], [monster("Louse", 5)]))
        out = session.act("play a 0; play b 0; end")
        self.assertIn("combat won", out)
        self.assertEqual(game.sent[0], "play 1 0")
        self.assertNotIn("end", game.sent)

    def test_end_turn_shows_new_turn(self):
        session, game = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        out = session.act("end")
        self.assertIn("T2", out)
        self.assertIn(" a Strike", out)


class StopTest(unittest.TestCase):
    def test_draw_stops_the_sequence(self):
        def draw(msg, c, target):
            msg["game_state"]["combat_state"]["hand"].append(card("Bash", cost=2, damage=8, magic_number=2))
        hand = [card("Pommel Strike", damage=9, magic_number=1), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]), SimpleCombat({"Pommel Strike": draw}))
        out = session.act("play a 0; play b 0")
        self.assertIn("New in hand: Bash", out)
        self.assertIn("stopped after \"play a 0\"", out)
        self.assertEqual(game.sent, ["play 1 0"])

    def test_draw_does_not_stop_when_disabled(self):
        def draw(msg, c, target):
            msg["game_state"]["combat_state"]["hand"].append(defend())
        hand = [card("Pommel Strike", damage=9, magic_number=1), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]), SimpleCombat({"Pommel Strike": draw}))
        session.act("play a 0; play b 0", stop_on=["choice", "spawn"])
        self.assertEqual(len(game.sent), 2)

    def test_spawn_stops_the_sequence(self):
        def split(msg, c, target):
            cs = msg["game_state"]["combat_state"]
            cs["monsters"][0].update(is_gone=True, current_hp=0)
            cs["monsters"] += [monster("Slime", 30), monster("Slime", 30)]
        session, game = session_for(combat_message([card("Bash", cost=2, damage=8, magic_number=2), strike()],
                                                   [monster("Slime Boss", 70, 140)]), SimpleCombat({"Bash": split}))
        out = session.act("play a 0; play b 0")
        self.assertIn("enemies changed", out)
        self.assertEqual(len(game.sent), 1)

    def test_choice_screen_stops_the_sequence(self):
        def armaments(msg, c, target):
            hand = msg["game_state"]["combat_state"]["hand"]
            return message("HAND_SELECT", {"hand": hand, "selected": [], "max_cards": 1, "can_pick_zero": False},
                           commands=("choose",), choices=[h["name"].lower() for h in hand],
                           combat=msg["game_state"]["combat_state"])
        hand = [card("Armaments", type="SKILL", block=5), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]), SimpleCombat({"Armaments": armaments}))
        out = session.act("play a; play b 0")
        self.assertIn("a choice is needed", out)
        self.assertIn("Choose 1 card", out)


class RepeatTest(unittest.TestCase):
    def test_repeat_plays_attacks_until_none_left(self):
        hand = [strike(), defend(), strike(), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)], energy=3))
        out = session.act("repeat play Attack 0")
        self.assertEqual(game.sent, ["play 1 0", "play 2 0", "play 2 0"])
        self.assertIn("played 3 card(s)", out)

    def test_repeat_skips_self_damage_cards(self):
        hand = [card("Hemokinesis", damage=15, magic_number=2), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]))
        session.act("repeat play Attack 0")
        self.assertEqual(game.sent, ["play 2 0"])

    def test_repeat_by_name_plays_self_damage(self):
        hand = [card("Hemokinesis", damage=15, magic_number=2), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]))
        session.act("repeat play Hemokinesis 0")
        self.assertEqual(game.sent, ["play 1 0"])

    def test_repeat_stops_when_target_dies(self):
        hand = [strike(), strike(), strike()]
        session, game = session_for(combat_message(hand, [monster("Louse", 6), monster("Louse", 20)]))
        out = session.act("repeat play Strike 0; play b 1")
        self.assertEqual(game.sent, ["play 1 0"])
        self.assertIn("target 0 is dead", out)

    def test_repeat_cost0(self):
        hand = [card("Anger", cost=0, damage=6), strike(), card("Anger", cost=0, damage=6)]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)], energy=0))
        session.act("repeat play cost0 0")
        self.assertEqual(game.sent, ["play 1 0", "play 2 0"])

    def test_bad_repeat_syntax(self):
        session, game = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        self.assertIn("ERR", session.act("repeat Strike"))

    def test_action_limit(self):
        def anger(msg, c, target):
            msg["game_state"]["combat_state"]["hand"].append(card("Anger", cost=0, damage=1))
        session, game = session_for(combat_message([card("Anger", cost=0, damage=1)], [monster("Cultist", 999)]),
                                    SimpleCombat({"Anger": anger}))
        out = session.act("repeat play Anger 0")
        self.assertEqual(len(game.sent), MAX_ACTIONS)
        self.assertIn(f"limit of {MAX_ACTIONS}", out)


class PotionTest(unittest.TestCase):
    def test_potion_with_target(self):
        first = combat_message([strike()], [monster("Cultist", 50), monster("Cultist", 50)],
                               potions=[potion("Fire Potion", target=True), dict(SLOT), dict(SLOT)])
        session, game = session_for(first)
        session.act("potion 0 1")
        self.assertEqual(game.sent, ["potion use 0 1"])

    def test_empty_potion_slot(self):
        session, game = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        out = session.act("potion 1")
        self.assertIn("ERR", out)

    def test_target_potion_without_target_and_one_enemy(self):
        first = combat_message([strike()], [monster("Cultist", 50)],
                               potions=[potion("Fire Potion", target=True), dict(SLOT), dict(SLOT)])
        session, game = session_for(first)
        session.act("potion 0")
        self.assertEqual(game.sent, ["potion use 0 0"])

    def test_potion_without_number(self):
        session, game = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        self.assertIn("ERR", session.act("potion"))
        self.assertIn("ERR", session.act("drop"))


class ScreenActionTest(unittest.TestCase):
    def test_choose_needs_a_number(self):
        first = message("EVENT", {"event_name": "X", "options": []}, commands=("choose",), choices=["a", "b"])
        session, game = session_for(first, lambda m, c: m)
        self.assertIn("choose needs a number", session.act("choose first"))

    def test_choose_out_of_range(self):
        first = message("EVENT", {"event_name": "X", "options": []}, commands=("choose",), choices=["a", "b"])
        session, game = session_for(first, lambda m, c: m)
        out = session.act("choose 5")
        self.assertIn("ERR", out)
        self.assertEqual(game.sent, [])

    def test_choose_boss(self):
        first = message("MAP", {"next_nodes": [], "boss_available": True}, commands=("choose",), choices=["boss"])
        session, game = session_for(first, lambda m, c: message("NONE"))
        session.act("choose 0")
        self.assertEqual(game.sent, ["choose boss"])

    def test_skip_card_reward_then_rewards_close(self):
        rewards = message("COMBAT_REWARD", {"rewards": [{"reward_type": "CARD"}]}, commands=("choose", "proceed"),
                          choices=["card"])
        reward_screen = message("CARD_REWARD", {"cards": [strike()], "bowl_available": False, "skip_available": True},
                                commands=("choose", "skip"), choices=["strike"])

        def step(m, command):
            if command == "skip":
                return rewards
            if command == "proceed":
                return message("MAP", {"next_nodes": [{"x": 1, "y": 5, "symbol": "M"}, {"x": 2, "y": 5, "symbol": "?"}],
                                       "boss_available": False}, commands=("choose",), choices=["x=1", "x=2"])
            return {"error": command}
        session, game = session_for(reward_screen, step)
        out = session.act("skip")
        self.assertEqual(game.sent, ["skip", "proceed"])
        self.assertIn("== Map", out)


class AutoTest(unittest.TestCase):
    def test_takes_gold_relic_and_potion_then_leaves_card(self):
        rewards = [{"reward_type": "GOLD", "gold": 20}, {"reward_type": "POTION", "potion": potion("Block Potion")},
                   {"reward_type": "RELIC", "relic": {"id": "Anchor", "name": "Anchor", "counter": -1}},
                   {"reward_type": "CARD"}]

        def step(m, command):
            if m["game_state"]["screen_type"] != "COMBAT_REWARD":
                return m
            rs = m["game_state"]["screen_state"]["rewards"]
            if rs[int(command.split()[1])]["reward_type"] == "CARD":
                return message("CARD_REWARD", {"cards": [strike()]}, commands=("choose", "skip"), choices=["strike"])
            i = int(command.split()[1])
            taken = rs.pop(i)
            if taken["reward_type"] == "POTION":
                m["game_state"]["potions"][0] = taken["potion"]
            m["game_state"]["choice_list"] = [r["reward_type"].lower() for r in rs]
            return m
        first = combat_message([strike()], [monster("Louse", 5)])
        session, game = session_for(first)
        game.step = step
        game.message = message("COMBAT_REWARD", {"rewards": rewards}, commands=("choose", "proceed"),
                               choices=["gold", "potion", "relic", "card"])
        session.message = game.get()
        auto = session.auto_handle()
        self.assertEqual(auto[:3], ["+20 Gold", "potion Block Potion", "relic Anchor"])

    def test_potion_left_when_slots_full(self):
        full = [potion("Fire Potion", target=True), potion("Block Potion"), potion("Swift Potion")]
        first = message("COMBAT_REWARD", {"rewards": [{"reward_type": "POTION", "potion": potion("Ancient Potion")}]},
                        commands=("choose", "proceed"), choices=["potion"], potions=full)
        session, game = session_for(first, lambda m, c: {"error": "should not be called"})
        self.assertEqual(session.auto_handle(), [])
        self.assertEqual(game.sent, [])

    def test_single_path_and_single_event_option(self):
        one_path = message("MAP", {"next_nodes": [{"x": 3, "y": 2, "symbol": "M"}], "boss_available": False},
                           commands=("choose",), choices=["x=3"])
        event = message("EVENT", {"event_name": "Neow", "options": [{"text": "[Talk]", "choice_index": 0}]},
                        commands=("choose",), choices=["talk"])
        two = message("EVENT", {"event_name": "Neow", "options": [{"text": "A", "choice_index": 0},
                                                                   {"text": "B", "choice_index": 1}]},
                      commands=("choose",), choices=["a", "b"])
        replies = iter([event, two])
        session, game = session_for(one_path, lambda m, c: next(replies))
        self.assertEqual(session.auto_handle(), ["only one path: F6 Monster", "event Neow: [Talk]"])
        self.assertEqual(game.sent, ["choose 0", "choose 0"])

    def test_chest_is_opened(self):
        chest = message("CHEST", {"chest_type": "SmallChest", "chest_open": False}, commands=("choose", "proceed"),
                        choices=["open"])
        opened = message("COMBAT_REWARD", {"rewards": [{"reward_type": "RELIC", "relic": {"id": "Anchor", "name": "Anchor", "counter": -1}}]},
                         commands=("choose", "proceed"), choices=["relic"])
        done = message("CHEST", {"chest_type": "SmallChest", "chest_open": True}, commands=("proceed",), choices=[])
        replies = iter([opened, message("COMBAT_REWARD", {"rewards": []}, commands=("proceed",), choices=[]), done,
                        message("MAP", {"next_nodes": [{"x": 1, "y": 3, "symbol": "M"}, {"x": 2, "y": 3, "symbol": "E"}],
                                        "boss_available": False}, commands=("choose",), choices=["x=1", "x=2"])])
        session, game = session_for(chest, lambda m, c: next(replies))
        auto = session.auto_handle()
        self.assertEqual(auto[:2], ["opened chest", "relic Anchor"])
        self.assertEqual(game.sent, ["choose 0", "choose 0", "proceed", "proceed"])

    def test_shop_room_opens_the_merchant(self):
        room = message("SHOP_ROOM", {}, commands=("choose", "proceed"), choices=["shop"], room_type="ShopRoom")
        shop = message("SHOP_SCREEN", {"cards": [dict(card("Anger", cost=0), price=40)], "relics": [], "potions": [],
                                       "purge_available": False}, commands=("choose", "leave"), choices=["anger"])
        session, game = session_for(room, lambda m, c: shop)
        self.assertEqual(session.auto_handle(), ["went to the merchant"])

    def test_card_reward_is_opened(self):
        rewards = message("COMBAT_REWARD", {"rewards": [{"reward_type": "CARD"}]}, commands=("choose", "proceed"),
                          choices=["card"])
        cards = message("CARD_REWARD", {"cards": [strike()]}, commands=("choose", "skip"), choices=["strike"])
        session, game = session_for(rewards, lambda m, c: cards)
        self.assertEqual(session.auto_handle(), ["opened card reward"])
        self.assertEqual(game.sent, ["choose 0"])


class InspectTest(unittest.TestCase):
    def setUp(self):
        hand = [strike()]
        cm = combat_message(hand, [monster("Cultist", 50)], discard=2,
                            potions=[potion("Fire Potion", target=True), dict(SLOT), dict(SLOT)])
        self.session, _ = session_for(cm)

    def test_every_inspect_topic(self):
        s = self.session
        self.assertTrue(s.inspect("deck").startswith("Deck: "))
        self.assertIn("Strike x5", s.inspect("deck"))
        self.assertEqual(s.inspect("draw"), "Draw pile: Strike x5")
        self.assertEqual(s.inspect("discard"), "Discard pile: Strike x2")
        self.assertEqual(s.inspect("exhaust"), "Exhaust pile: (empty)")
        self.assertIn("Burning Blood - ", s.inspect("relics"))
        self.assertIn("0 Fire Potion - Deal 20 damage", s.inspect("potions"))
        self.assertIn("Bash", s.inspect("card bash"))
        self.assertIn("Upgraded:", s.inspect("card Bash+"))
        self.assertIn("Unknown card", s.inspect("card Zap"))
        self.assertIn("Anchor:", s.inspect("relic anchor"))
        self.assertIn("Cultist", s.inspect("enemy 0"))

    def test_bad_inspect(self):
        s = self.session
        self.assertTrue(s.inspect("enemy 7").startswith("No enemy"))
        self.assertTrue(s.inspect("nonsense").startswith("Use:"))
        self.assertTrue(s.inspect("").startswith("Use:"))


if __name__ == "__main__":
    unittest.main()


class PlaytestFindingsTest(unittest.TestCase):
    """Problems found while playing a whole act through the MCP tools."""

    def test_hand_select_choose_then_confirm_runs_both(self):
        hand = [strike(), defend()]
        screen = message("HAND_SELECT", {"hand": hand, "selected": [], "max_cards": 1, "can_pick_zero": False},
                         commands=("choose",), choices=["strike", "defend"],
                         combat=combat_message(hand, [monster("Cultist", 50)])["game_state"]["combat_state"])

        def step(m, command):
            if command.startswith("choose"):
                m["available_commands"] = ["choose", "confirm"]
                return m
            return combat_message([strike()], [monster("Cultist", 50)])
        session, game = session_for(screen, step)
        session.act("choose 1; confirm")
        self.assertEqual(game.sent, ["choose 1", "confirm"])

    def test_skip_on_rewards_uses_proceed(self):
        first = message("COMBAT_REWARD", {"rewards": [{"reward_type": "CARD"}]}, commands=("choose", "proceed"),
                        choices=["card"])
        session, game = session_for(first, lambda m, c: message("MAP", {"next_nodes": [{"x": 1, "y": 2, "symbol": "M"},
                                                                                        {"x": 2, "y": 2, "symbol": "$"}]},
                                                                  commands=("choose",), choices=["x=1", "x=2"]))
        self.assertNotIn("ERR", session.act("skip"))
        self.assertEqual(game.sent, ["proceed"])

    def test_leaving_the_shop_goes_back_to_the_map(self):
        shop = message("SHOP_SCREEN", {"cards": [], "relics": [], "potions": [], "purge_available": False},
                       commands=("choose", "leave"), choices=[])
        room = message("SHOP_ROOM", {}, commands=("choose", "proceed"), choices=["shop"])
        map_ = message("MAP", {"next_nodes": [{"x": 1, "y": 2, "symbol": "M"}, {"x": 2, "y": 2, "symbol": "$"}]},
                       commands=("choose",), choices=["x=1", "x=2"])
        replies = iter([room, map_])
        session, game = session_for(shop, lambda m, c: next(replies))
        session.act("skip")
        self.assertEqual(game.sent, ["leave", "proceed"])

    def test_visited_rooms_of_every_kind_are_marked(self):
        nodes = [{"x": 1, "y": 0, "symbol": "M", "children": [{"x": 1, "y": 1}]},
                 {"x": 2, "y": 0, "symbol": "$", "children": [{"x": 1, "y": 1}]},
                 {"x": 1, "y": 1, "symbol": "?", "children": []}]
        first = message("MAP", {"next_nodes": nodes[:2], "boss_available": False}, commands=("choose",),
                        choices=["x=1", "x=2"], map=nodes)
        session, game = session_for(first, lambda m, c: message("SHOP_ROOM", {}, commands=("choose", "proceed"),
                                                                 choices=["shop"], map=nodes))
        session.act("choose 1")
        self.assertIn("2$*", session.inspect("map"))

    def test_empty_act(self):
        session, game = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        self.assertTrue(session.act("  ").startswith("ERR"))

    def test_choice_screen_in_combat_shows_enemies(self):
        hand = [strike()]
        screen = message("HAND_SELECT", {"hand": hand, "selected": [], "max_cards": 1, "can_pick_zero": True},
                         commands=("choose",), choices=["strike"],
                         combat=combat_message(hand, [monster("Cultist", 50, intent="BUFF")])["game_state"]["combat_state"])
        session, _ = session_for(screen)
        self.assertIn(" 0 Cultist 50/50 | intent BUFF", session.text())

    def test_reward_cards_have_no_unplayable_flag(self):
        text = session_for(message("CARD_REWARD", {"cards": [card("Bash", cost=2, playable=False)]},
                                   commands=("choose", "skip"), choices=["bash"]))[0].text()
        self.assertNotIn("can't play", text)

    def test_continue_while_in_game_starts_logging(self):
        session, _ = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        import tempfile, pathlib
        from bridge import session as session_module
        with tempfile.TemporaryDirectory() as tmp:
            old = session_module.ROOT
            session_module.ROOT = pathlib.Path(tmp)
            try:
                session.continue_run()
                self.assertIsNotNone(session.run_dir)
                self.assertTrue(str(session.run_dir).endswith("_seed-42"))
            finally:
                session_module.ROOT = old


class SecondRunFindingsTest(unittest.TestCase):
    """Problems found while winning a whole run through the MCP tools."""

    def test_single_card_grid_confirms_itself_and_says_what(self):
        grid = message("GRID", {"cards": [strike(), card("Demon Form", cost=3, type="POWER")], "selected_cards": [],
                                "num_cards": 1, "any_number": False, "for_upgrade": True, "confirm_up": False},
                       commands=("choose",), choices=["strike", "demon form"])

        def step(m, command):
            if command == "choose 1":
                m["game_state"]["screen_state"].update(confirm_up=True, selected_cards=[m["game_state"]["screen_state"]["cards"][1]])
                m["available_commands"] = ["confirm", "cancel"]
                return m
            return message("MAP", {"next_nodes": [{"x": 1, "y": 7, "symbol": "M"}, {"x": 2, "y": 7, "symbol": "E"}]},
                           commands=("choose",), choices=["x=1", "x=2"])
        session, game = session_for(grid, step)
        out = session.act("choose 1")
        self.assertEqual(game.sent, ["choose 1", "confirm"])
        self.assertIn("Selected Demon Form.", out)
        self.assertIn("upgraded Demon Form", out)

    def test_boss_only_path_is_automatic(self):
        first = message("MAP", {"next_nodes": [], "boss_available": True}, commands=("choose",), choices=["boss"])
        session, game = session_for(first, lambda m, c: combat_message([strike()], [monster("Hexaghost", 250)]))
        self.assertEqual(session.auto_handle(), ["only one path: Boss"])
        self.assertEqual(game.sent, ["choose boss"])

    def test_rest_site_with_one_option(self):
        first = message("REST", {}, commands=("choose",), choices=["rest"])
        session, game = session_for(first, lambda m, c: message("REST", {}, commands=("proceed",), choices=[]))
        self.assertIn("rest site: rest (only option)", session.auto_handle())

    def test_buying_stops_the_sequence(self):
        shop = message("SHOP_SCREEN", {"cards": [dict(card("Anger", cost=0), price=40), dict(card("Inflame"), price=50)],
                                       "relics": [], "potions": [], "purge_available": False},
                       commands=("choose", "leave"), choices=["anger", "inflame"])

        def step(m, command):
            ss = m["game_state"]["screen_state"]
            del ss["cards"][0]
            m["game_state"]["choice_list"] = ["inflame"]
            return m
        session, game = session_for(shop, step)
        out = session.act("choose 0; choose 1")
        self.assertEqual(game.sent, ["choose 0"])
        self.assertIn("Shop numbers have changed", out)

    def test_map_marks_reset_each_act(self):
        from bridge.render import Renderer
        r = Renderer()
        node = {"x": 1, "y": 0, "symbol": "M", "children": []}
        r.render(message("MAP", {"current_node": {"x": 1, "y": 0}, "next_nodes": [], "boss_available": False}, map=[node], act=1))
        text = r.render(message("MAP", {"current_node": {"x": 0, "y": -1}, "next_nodes": [], "boss_available": False}, map=[node], act=2))
        self.assertNotIn("1M*", text)

    def test_full_map_once_per_act_then_on_request(self):
        node = {"x": 1, "y": 0, "symbol": "M", "children": []}
        msg = message("MAP", {"next_nodes": [node, dict(node, x=2)], "boss_available": False}, map=[node])
        session, _ = session_for(msg)
        self.assertIn("1M>", session.text())
        self.assertNotIn("1M>", session.text())
        self.assertIn("1M>", session.inspect("map"))

    def test_drawn_then_discarded_cards_are_not_reported(self):
        def draw(msg, c, target):
            msg["game_state"]["combat_state"]["hand"].append(card("Bash", cost=2, damage=8, magic_number=2))
        hand = [card("Pommel Strike", damage=9, magic_number=1), strike()]
        session, game = session_for(combat_message(hand, [monster("Cultist", 50)]), SimpleCombat({"Pommel Strike": draw}))
        out = session.act("play a 0; end", stop_on=["choice"])
        self.assertNotIn("New in hand", out)

    def test_reviving_darkling(self):
        from bridge.render import Renderer
        line = Renderer().monster_line(1, monster("Darkling", 0, 50, gone=True, half_dead=True))
        self.assertIn("reviving", line)


class MemoryTest(unittest.TestCase):
    def setUp(self):
        import pathlib, tempfile
        from bridge import session as session_module
        self.tmp = tempfile.TemporaryDirectory()
        self.module, self.old_root = session_module, session_module.ROOT
        session_module.ROOT = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.module.ROOT = self.old_root
        self.tmp.cleanup()

    def map_message(self):
        return message("MAP", {"next_nodes": [{"x": 1, "y": 2, "symbol": "M"}, {"x": 2, "y": 2, "symbol": "E"}],
                               "boss_available": False}, commands=("choose",), choices=["x=1", "x=2"])

    def test_plan_and_route_show_on_decision_screens_and_persist(self):
        session, _ = session_for(self.map_message())
        session.continue_run()
        session.note("Strength build: Demon Form, Heavy Blade.", "plan")
        session.note("Shop at x4 then elite.", "route")
        session.note("Route changed: rest first.", "route")
        session.note("Lagavulin wakes after 3 turns.")
        text = session.text()
        self.assertIn("Plan (F5): Strength build", text)
        self.assertIn("Route (F5): Route changed", text)
        self.assertNotIn("Shop at x4", text)
        self.assertNotIn("Lagavulin", text)
        again, _ = session_for(self.map_message())
        again.continue_run()
        memory = again.inspect("memory")
        self.assertIn("Strength build", memory)
        self.assertIn("F5: Lagavulin wakes after 3 turns.", memory)

    def test_lessons_outlive_the_run(self):
        session, _ = session_for(self.map_message())
        session.continue_run()
        session.note("Card-adding decks: don't stop on draw.", "lesson")
        self.assertNotIn("Card-adding", session.inspect("memory"))
        later, _ = session_for(self.map_message())
        lessons = later.inspect("lessons")
        self.assertIn("F5) Card-adding decks: don't stop on draw.", lessons)

    def test_game_over_shows_a_review(self):
        session, _ = session_for(message("GAME_OVER", {"victory": True, "score": 800}, commands=("proceed",)))
        session.continue_run()
        session.note("Exhaust build.", "plan")
        text = session.text()
        self.assertIn("== Run review ==", text)
        self.assertIn("Plan (F5): Exhaust build.", text)
        self.assertIn('tag="lesson"', text)

    def test_guides_keep_the_current_view_and_history(self):
        from bridge.session import ActionError
        session, _ = session_for(self.map_message())
        session.continue_run()
        with self.assertRaises(ActionError):
            session.guide("neow", "Take the card.")
        session.guide("Neow choice", "Take the rare card.", "Which Neow option?")
        session.guide("neow-choice", "Take max HP on Ascension.")
        text = session.inspect("guide neow-choice")
        self.assertIn("Which Neow option?", text)
        self.assertIn("Current view:\nTake max HP on Ascension.", text)
        self.assertIn("Take the rare card.", text.split("Earlier views:")[1])
        self.assertIn("neow-choice: Which Neow option?", session.inspect("guides"))

    def test_memory_hidden_in_combat_and_when_off(self):
        import os
        session, _ = session_for(combat_message([strike()], [monster("Cultist", 50)]))
        session.continue_run()
        session.note("Kill the cultist first.", "plan")
        self.assertNotIn("Kill the cultist", session.text())
        os.environ["STS_MEMORY"] = "off"
        try:
            off, _ = session_for(self.map_message())
            off.continue_run()
            off.note("x", "plan")
            self.assertNotIn("Plan", off.text())
            self.assertEqual(off.inspect("memory"), "Memory is off for this run.")
        finally:
            del os.environ["STS_MEMORY"]


class OverlayTest(unittest.TestCase):
    def test_deck_view_opened_by_a_human_is_closed_first(self):
        first = combat_message([strike()], [monster("Cultist", 50)], is_screen_up=True, screen_name="MASTER_DECK_VIEW")

        def step(m, command):
            if command == "key CANCEL":
                m["game_state"].update(is_screen_up=False, screen_name="NONE")
                return m
            return SimpleCombat()(m, command)
        session, game = session_for(first, step)
        out = session.act("play a 0")
        self.assertEqual(game.sent, ["key CANCEL", "play 1 0"])
        self.assertIn("Closed the master deck view", out)


class ThirdRunFindingsTest(unittest.TestCase):
    def test_awakened_one_phase_one_is_not_a_win(self):
        def kill(msg, c, target):
            msg["game_state"]["combat_state"]["monsters"][0].update(is_gone=True, half_dead=True, current_hp=0)
        session, game = session_for(combat_message([card("Bash", cost=2, damage=8, magic_number=2), strike()],
                                                   [monster("Awakened One", 5, 300)]), SimpleCombat({"Bash": kill}))
        out = session.act("play a 0; play b 0")
        self.assertNotIn("combat won", out)

    def test_grid_that_closes_itself_waits_for_the_card(self):
        grid = message("GRID", {"cards": [strike()], "selected_cards": [], "num_cards": 1, "any_number": False},
                       commands=("choose",), choices=["strike"])
        event = message("EVENT", {"event_name": "Duplicator", "options": [{"text": "[Leave]", "choice_index": 0}]},
                        commands=("choose",), choices=["leave"])
        session, game = session_for(grid, lambda m, c: event)
        sent = []
        original = game.send
        game.send = lambda c: (sent.append(c), original(c))[1]
        session.act("choose 0")
        self.assertEqual(sent[:2], ["choose 0", "wait 150"])

    def test_new_relic_from_an_event_is_named(self):
        event = message("EVENT", {"event_name": "Tomb", "options": [{"text": "[Open]", "choice_index": 0},
                                                                    {"text": "[Leave]", "choice_index": 1}]},
                        commands=("choose",), choices=["open", "leave"])

        def step(m, c):
            m["game_state"]["relics"].append({"id": "Anchor", "name": "Anchor", "counter": -1})
            m["game_state"]["choice_list"] = ["leave", "x"]
            return m
        session, game = session_for(event, step)
        self.assertIn("New relic: Anchor - Start each combat with 10 Block.", session.act("choose 0"))
