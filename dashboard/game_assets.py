"""Slay the Spire's own art and fonts, read at runtime from the local game install.

Nothing here is copied into the repo: every image is read out of desktop-1.0.jar when the page asks
for it. Point STS_GAME_DIR (or --game-dir) at the install folder when it is not in the default
Steam library. Without the game the dashboard still works, it just shows no game art.
"""
import os
import re
import struct
import threading
import zipfile
from pathlib import Path

DEFAULT_GAME_DIR = r"E:\SteamLibrary\steamapps\common\SlayTheSpire"

# Only art, atlases and fonts leave the jar; never classes or other files.
ALLOWED_PREFIXES = ("images/", "title/", "cards/", "font/", "powers/", "bottomScene/", "cityScene/", "beyondScene/")
ALLOWED_EXTS = (".png", ".jpg", ".atlas", ".otf", ".ttf")

CARD_COLORS = ("red", "green", "blue", "purple", "colorless", "curse", "status")
# AbstractPotion.PotionSize / PotionColor values, as they appear in each potion class's constant pool.
POTION_SHAPES = ("SPHERE", "BOTTLE", "HEART", "SNECKO", "FAIRY", "GHOST", "JAR", "BOLT", "CARD", "MOON", "SPIKY", "EYE",
                 "ANVIL", "S", "M", "T", "H")
POTION_COLORS = ("POISON", "BLUE", "FIRE", "GREEN", "EXPLOSIVE", "WEAK", "FEAR", "STRENGTH", "WHITE", "FAIRY", "ANCIENT",
                 "ELIXIR", "ENERGY", "SWIFT", "FRUIT", "SNECKO", "SMOKE", "STEROID", "SKILL", "ATTACK", "POWER", "NONE")
# Names that are also something else in a potion class (a shape, a card type, "no target"): used only when nothing else is.
WEAK_COLOR_NAMES = ("NONE", "FAIRY", "ATTACK", "SKILL", "POWER")
ATLAS_PAIRS = {"xy": ("x", "y"), "size": ("w", "h"), "orig": ("ow", "oh"), "offset": ("ox", "oy")}


def utf8_constants(data):
    """The Utf8 entries of a class file's constant pool (string literals, names, descriptors)."""
    out = []
    count = struct.unpack_from(">H", data, 8)[0]
    pos, i = 10, 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            length = struct.unpack_from(">H", data, pos)[0]
            out.append(data[pos + 2:pos + 2 + length].decode("utf-8", "replace"))
            pos += 2 + length
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            pos += 2
        elif tag == 15:
            pos += 3
        else:
            break
        i += 1
    return out


def parse_atlas(text):
    """libGDX texture atlas -> {region: {page, x, y, w, h, ow, oh, ox, oy}}."""
    regions, page, current = {}, None, None
    for line in text.splitlines():
        if not line.strip():
            page = None
            continue
        if not line.startswith(" ") and ":" not in line:
            if page is None:
                page = line.strip()
            else:
                current = {"page": page}
                regions[line.strip()] = current
            continue
        if current is not None and line.startswith(" "):
            key, _, value = line.strip().partition(":")
            nums = [v.strip() for v in value.split(",")]
            if key in ATLAS_PAIRS:
                current.update(zip(ATLAS_PAIRS[key], (int(n) for n in nums)))
            elif key == "rotate":
                current["rotate"] = nums[0] == "true"
    return regions


def squash(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


class GameAssets:
    def __init__(self, game_dir=None):
        self.game_dir = Path(game_dir or os.environ.get("STS_GAME_DIR") or DEFAULT_GAME_DIR)
        self.jar_path = self.game_dir / "desktop-1.0.jar"
        self._jar = None
        self._names = None
        self._index = None
        self._lock = threading.Lock()

    @property
    def available(self):
        return self.jar_path.is_file()

    def jar(self):
        if self._jar is None:
            self._jar = zipfile.ZipFile(self.jar_path)
            self._names = set(self._jar.namelist())
        return self._jar

    def read(self, path):
        if not self.available or not path.startswith(ALLOWED_PREFIXES) or not path.lower().endswith(ALLOWED_EXTS):
            return None
        with self._lock:
            jar = self.jar()
            return jar.read(path) if path in self._names else None

    def index(self, catalog):
        """Which game image belongs to each relic and card id (taken from the game's own classes)."""
        if self._index is not None:
            return self._index
        if not self.available:
            self._index = {"available": False}
            return self._index
        with self._lock:
            jar = self.jar()
            relic_ids = set(catalog.get("relics", {}))
            card_ids = set(catalog.get("cards", {}))
            potion_ids = set(catalog.get("potions", {}))
            relics, cards, potions = {}, {}, {}
            atlas = parse_atlas(jar.read("cards/cards.atlas").decode("utf-8"))
            for name in self._names:
                if not name.endswith(".class") or "$" in name:
                    continue
                if name.startswith("com/megacrit/cardcrawl/relics/"):
                    kind, ids = "relic", relic_ids
                elif name.startswith("com/megacrit/cardcrawl/cards/"):
                    kind, ids = "card", card_ids
                elif name.startswith("com/megacrit/cardcrawl/potions/"):
                    kind, ids = "potion", potion_ids
                else:
                    continue
                strings = utf8_constants(jar.read(name))
                own = self._own_id(name, strings, ids)
                if not own:
                    continue
                if kind == "relic":
                    png = next((s for s in strings if s.endswith(".png") and f"images/relics/{s}" in self._names), None)
                    if png:
                        relics[own] = f"images/relics/{png}"
                elif kind == "potion":
                    layers = self._potion_layers(strings)
                    if layers:
                        potions[own] = layers
                else:
                    art = next((s for s in strings if s.split("/")[0] in CARD_COLORS and s in atlas), None)
                    if art:
                        r = atlas[art]
                        cards[own] = {"page": f"cards/{r['page']}", "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]}
            self._index = {"available": True, "relics": relics, "cards": cards, "potions": potions}
        return self._index

    def _potion_layers(self, strings):
        """A potion's shape images and colour name. Small shapes (S/M/T/H) are flat files, the rest have folders."""
        shapes = [s for s in strings if s in POTION_SHAPES]
        # Prefer a named shape: one-letter strings can also be field descriptors.
        shape = next((s for s in shapes if len(s) > 1), shapes[0] if shapes else None)
        colors = [s for s in strings if s in POTION_COLORS]
        color = next((c for c in colors if c not in WEAK_COLOR_NAMES), colors[-1] if colors else "NONE")
        if not shape:
            return None
        if len(shape) == 1:
            paths = {k: f"images/potion/potion_{shape.lower()}_{k}.png" for k in ("liquid", "hybrid", "spots", "glass")}
        else:
            base = f"images/potion/{shape.lower()}/"
            paths = {k: base + f"{'body' if k == 'glass' else k}.png" for k in ("liquid", "hybrid", "spots", "glass")}
        return {"color": color, **{k: v for k, v in paths.items() if v in self._names}}

    @staticmethod
    def _own_id(class_name, strings, ids):
        """A class's own ID among the ids it mentions: the one that matches its class name, else the only one."""
        found = [s for s in strings if s in ids]
        if not found:
            return None
        simple = squash(class_name.rsplit("/", 1)[-1][:-len(".class")])
        return next((s for s in found if squash(s) == simple), found[0] if len(set(found)) == 1 else None)
