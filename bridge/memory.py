"""The run's own memory: what the player decided to remember, kept outside the LLM.

Stored as runs/<run>/memory.json so it survives a restarted Claude or a resumed save.
  plan  - the current build idea (a new one replaces the old)
  route - the current route intention (a new one replaces the old)
  notes - everything else, in order, as free text with the floor it was written on
Every write is also in run.jsonl, so replaced plans and routes are never lost.

Lessons are the one thing that outlives a run: runs/lessons.json, shared by all runs.
"""
import json
import re


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


class Lessons:
    """What the player chose to carry over to later runs (note tag="lesson"), with where it was learned."""

    def __init__(self, path=None):
        self.path = path
        self.items = []
        if path is not None and path.exists():
            self.items = json.loads(path.read_text(encoding="utf-8"))

    def write(self, text, run=None, floor=None):
        self.items.append({"text": text, "run": run, "floor": floor})
        if self.path is not None:
            self.path.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")

    def full(self):
        return "\n".join(f"{i + 1}. ({item['run']}, F{item['floor']}) {item['text']}"
                         for i, item in enumerate(self.items)) or "No lessons yet."


class Guides:
    """One markdown file per question in guides/: the player's current view, and the views it replaced.

    A question can be asked by the humans (a file with an empty view) or by the player itself.
    The files are plain markdown so people can read them, and they live in the repo so the views
    can be followed over time.
    """
    NONE = "(none yet)"

    def __init__(self, folder):
        self.folder = folder

    def path(self, topic):
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
        return self.folder / f"{slug}.md"

    def read(self, topic):
        path = self.path(topic)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        question = text.splitlines()[0].lstrip("# ").strip()
        view = text.split("## Current view", 1)[1].split("## History", 1)[0].strip()
        history = text.split("## History", 1)[1].strip() if "## History" in text else ""
        return {"topic": path.stem, "question": question, "view": view, "history": history,
                "asked_by": "human" if "Asked by: human" in text else "player"}

    def topics(self):
        return [self.read(p.stem) for p in sorted(self.folder.glob("*.md"))] if self.folder.exists() else []

    def write(self, topic, view, question=None, run=None, floor=None):
        old = self.read(topic)
        if old is None and not question:
            raise ValueError(f"No guide '{topic}' yet: give a question to start one.")
        stamp = f"{run or '?'} F{floor if floor is not None else '?'}"
        history = old["history"] if old else ""
        if old and old["view"] != self.NONE:
            history = f"- {' '.join(old['view'].split())} (replaced at {stamp})\n{history}".strip()
        asked_by = old["asked_by"] if old else "player"
        text = (f"# {question or old['question']}\n\nAsked by: {asked_by}\n\n## Current view\n\n"
                f"{view.strip()}\n\n({stamp})\n\n## History\n\n{history}\n")
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path(topic).write_text(text, encoding="utf-8")
        return self.path(topic).stem

    def listing(self):
        guides = self.topics()
        return "\n".join(f"{g['topic']}: {g['question']}" + (" [no view yet]" if g["view"] == self.NONE else "")
                         for g in guides) or "No guides yet."
