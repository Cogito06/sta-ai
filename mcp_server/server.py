"""MCP server that lets Claude Code play Slay the Spire through bridge/game_link.py.

Run the game with CommunicationMod's command set to bridge/game_link.py first; this server
connects to it on localhost:8765.
"""
import functools
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from bridge.session import ActionError, LinkClient, Session  # noqa: E402

mcp = MCPServer("slay-the-spire")
_session = None


def session():
    global _session
    if _session is None:
        _session = Session(LinkClient())
    return _session


def guarded(tool):
    """Errors come back as text the LLM can read instead of failing the tool call."""
    @functools.wraps(tool)
    def wrapper(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except ActionError as e:
            return f"ERR {e}"
        except OSError as e:
            return f"ERR can't reach the game ({e}). Is the game running with CommunicationMod?"
        except Exception:
            return "ERR internal bridge error, please report:\n" + traceback.format_exc(limit=3)
    return wrapper


@mcp.tool()
@guarded
def start_run(seed: str = "", overwrite: bool = False, ascension: int = 0) -> str:
    """Start a new Ironclad run at the given Ascension level (0-20). Optional seed (letters and digits,
    as shown in game). Refuses when a saved run exists, unless overwrite is true (that deletes the saved run)."""
    return session().start_run(seed or None, overwrite, ascension)


@mcp.tool()
@guarded
def continue_run() -> str:
    """Resume the saved run, like the main menu's Continue button."""
    return session().continue_run()


@mcp.tool()
@guarded
def get_state() -> str:
    """Show the current game state."""
    return session().get_state()


@mcp.tool()
@guarded
def act(actions: str, stop_on: str = "") -> str:
    """Do one or more actions, separated by ';'.

    play <hand letter|card name> [enemy]   end   potion <slot> [enemy]   drop <slot>
    choose <n>   confirm   skip   repeat play <Attack|Skill|Power|cost0|card name> [enemy]

    Hand letters stay fixed for the whole turn. A sequence stops early when new cards enter
    the hand, a choice is needed, enemies change, or the combat ends. stop_on: comma-separated
    subset of draw,choice,spawn to stop on (default all three).
    """
    stops = [s.strip() for s in stop_on.split(",") if s.strip()] or None
    return session().act(actions, stops)


@mcp.tool()
@guarded
def inspect(what: str) -> str:
    """Look something up without changing the game: memory, deck, draw, discard, exhaust, relics,
    potions, map, card <name>, relic <name>, enemy <n>."""
    return session().inspect(what)


@mcp.tool()
@guarded
def note(text: str, tag: str = "") -> str:
    """Write something to remember to this run's memory (kept outside the conversation).

    tag="plan" (build idea) and tag="route" (route intention) replace the previous one and are
    shown on map, reward, shop, rest, boss relic and event screens. Any other tag, or none, is
    added to the notes; read everything back with inspect("memory")."""
    return session().note(text, tag or None)


if __name__ == "__main__":
    mcp.run()
