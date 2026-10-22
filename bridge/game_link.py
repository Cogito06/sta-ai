"""Process that CommunicationMod starts (set it as the mod's `command`).

It holds the pipe to the game and serves it on localhost, so the MCP server that Claude
Code starts can talk to the game. Protocol on the socket: one JSON object per line.
  {"send": "<command>"}  -> sends the command, replies with the next state (or error) from the game
  {"get": true}          -> replies with the latest state without sending anything
Every message from the game is also appended to runs/link/<timestamp>.jsonl.
"""
import datetime
import json
import pathlib
import queue
import socketserver
import sys
import threading

HOST, PORT = "127.0.0.1", 8765
REPLY_TIMEOUT = 30.0
ROOT = pathlib.Path(__file__).resolve().parent.parent


class GameLink:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest = None
        self.incoming = queue.Queue()
        log_dir = ROOT / "runs" / "link"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log = open(log_dir / f"{datetime.datetime.now():%Y%m%d_%H%M%S}.jsonl", "a", encoding="utf-8")

    def read_game(self):
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            message = json.loads(line)
            if "error" not in message:
                self.latest = message
            self.log.write(line + "\n")
            self.log.flush()
            self.incoming.put(message)

    def send(self, command):
        with self.lock:
            while not self.incoming.empty():
                self.incoming.get_nowait()
            print(command, flush=True)
            try:
                return self.incoming.get(timeout=REPLY_TIMEOUT)
            except queue.Empty:
                return {"error": f"no reply from the game within {REPLY_TIMEOUT:.0f}s", "timeout": True}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        for raw in self.rfile:
            request = json.loads(raw)
            if "send" in request:
                reply = self.server.link.send(request["send"])
            else:
                reply = self.server.link.latest or {"error": "no state from the game yet"}
            self.wfile.write((json.dumps(reply) + "\n").encode("utf-8"))
            self.wfile.flush()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    link = GameLink()
    # CommunicationMod waits for "ready" before it starts sending states.
    print("ready", flush=True)
    threading.Thread(target=link.read_game, daemon=True).start()
    with Server((HOST, PORT), Handler) as server:
        server.link = link
        server.serve_forever()


if __name__ == "__main__":
    main()
