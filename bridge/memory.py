"""The run's own memory: what the player decided to remember, kept outside the LLM.

Stored as runs/<run>/memory.json so it survives a restarted Claude or a resumed save.
  plan  - the current build idea (a new one replaces the old)
  route - the current route intention (a new one replaces the old)
  notes - everything else, in order, as free text with the floor it was written on
Every write is also in run.jsonl, so replaced plans and routes are never lost.
"""
import json


class RunMemory:
    REPLACED = ("plan", "route")

    def __init__(self, path=None):
        self.path = path
        self.data = {"plan": None, "route": None, "notes": []}
        if path is not None and path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def write(self, text, tag=None, floor=None):
        if tag in self.REPLACED:
            self.data[tag] = {"text": text, "floor": floor}
        else:
            self.data["notes"].append({"text": text, "tag": tag, "floor": floor})
        if self.path is not None:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def header(self):
        """Lines shown on decision screens."""
        return [f"{tag.title()} (F{self.data[tag]['floor']}): {self.data[tag]['text']}"
                for tag in self.REPLACED if self.data.get(tag)]

    def full(self):
        lines = self.header()
        for note in self.data["notes"]:
            tag = f" [{note['tag']}]" if note.get("tag") else ""
            lines.append(f"F{note['floor']}{tag}: {note['text']}")
        return "\n".join(lines) or "Memory is empty."
