import unittest

from dashboard.server import chosen_node, visited_path


def node(x, y, children):
    return {"x": x, "y": y, "symbol": "M", "children": [{"x": cx, "y": cy} for cx, cy in children]}


# Act 1 map: (0,0) -> (0,1) -> (1,2) -> (1,3); (2,0) -> (1,1) -> (1,2)
MAP = [node(0, 0, [(0, 1)]), node(2, 0, [(1, 1)]), node(0, 1, [(1, 2)]), node(1, 1, [(1, 2)]),
       node(1, 2, [(1, 3)]), node(1, 3, [])]


def map_screen(current, next_nodes, floor):
    return {"act": 1, "floor": floor, "screen_type": "MAP",
            "screen_state": {"current_node": {"x": current[0], "y": current[1]},
                             "next_nodes": [{"x": x, "y": y, "symbol": "M"} for x, y in next_nodes]}}


class DashboardPathTest(unittest.TestCase):
    def test_chosen_node_by_column_and_index(self):
        gs = map_screen((0, -1), [(0, 0), (2, 0)], 0)
        self.assertEqual(chosen_node(gs, "choose x2"), (2, 0))
        self.assertEqual(chosen_node(gs, "choose 0"), (0, 0))
        self.assertIsNone(chosen_node(gs, "choose x5"))

    def test_path_fills_rooms_walked_without_a_map_screen(self):
        states = [map_screen((0, -1), [(0, 0), (2, 0)], 0),
                  {"act": 1, "floor": 1, "screen_type": "NONE"},
                  {"act": 1, "floor": 2, "screen_type": "NONE"},
                  {"act": 1, "floor": 3, "screen_type": "NONE"},
                  {"act": 1, "floor": 4, "screen_type": "NONE"}]
        log = [{"step": 1}, {"step": 2, "input": "choose x2"}, {"step": 3}, {"step": 4}, {"step": 5}]
        path = visited_path(log, states, {1: MAP})[1]
        self.assertEqual([(n["x"], n["y"]) for n in path], [(2, 0), (1, 1), (1, 2), (1, 3)])


if __name__ == "__main__":
    unittest.main()
