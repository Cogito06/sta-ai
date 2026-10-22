# sta-ai

LLM agent (and later an RL agent) for Slay the Spire 1. Ironclad, Ascension 0 first.

## Layout

- `docs/` — design: game rules digest, UI vs CommunicationMod info matrix, interface spec, architecture
- `catalog/` — static data: cards, relics, potions, powers, monsters, events (extracted from the game)
- `bridge/` — Python: state model, info filter, history, action executor, auto-handler, renderer
- `mcp_server/` — MCP tools for Claude Code: `start_run`, `continue_run`, `get_state`, `act`, `inspect`, `note`
- `game-mod/` — modified CommunicationMod (Java): exports card face numbers, max energy; hides draw pile order
- `runs/` — logs (not committed)

The game side is a modified copy of [CommunicationMod](https://github.com/ForgottenArbiter/CommunicationMod) (MIT) in `game-mod/`.

## Running

1. `pip install -r requirements.txt` (Python 3.10+).
2. In `%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties` set
   `command=<python.exe> <repo>/bridge/game_link.py` and `runAtGameStart=true`.
3. Start the game with ModTheSpire, loading BaseMod and the CommunicationMod built from `game-mod/`.
4. In this folder, start Claude Code; `.mcp.json` registers the `slay-the-spire` MCP tools.

`python bridge/try_session.py` plays a few steps without Claude to check the connection.
`python -m unittest discover -s tests -t .` runs the tests on recorded states.
