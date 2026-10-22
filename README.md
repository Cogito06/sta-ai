# sts-ai

LLM agent (and later an RL agent) for Slay the Spire 1. Ironclad, Ascension 0 first.

## Layout

- `docs/` — design: game rules digest, UI vs CommunicationMod info matrix, interface spec, architecture
- `catalog/` — static data: cards, relics, potions, powers, monsters, events (extracted from the game)
- `bridge/` — Python: state model, info filter, history, action executor, auto-handler, renderer
- `mcp_server/` — MCP tools for Claude Code: `start_run`, `get_state`, `act`, `inspect`, `note`
- `runs/` — logs (not committed)

The game side is a fork of CommunicationMod: https://github.com/Cogito06/CommunicationMod (branch `sts-ai`).
