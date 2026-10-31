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
# libGDX's named colours and the game's Settings colours that potions use, as rrggbbaa.
NAMED_COLORS = {
    "CLEAR": "00000000", "BLACK": "000000ff", "WHITE": "ffffffff", "LIGHT_GRAY": "bfbfbfff", "GRAY": "7f7f7fff",
    "DARK_GRAY": "3f3f3fff", "BLUE": "0000ffff", "NAVY": "00007fff", "ROYAL": "4169e1ff", "SLATE": "708090ff",
    "SKY": "87ceebff", "CYAN": "00ffffff", "TEAL": "007f7fff", "GREEN": "00ff00ff", "CHARTREUSE": "7fff00ff",
    "LIME": "32cd32ff", "FOREST": "228b22ff", "OLIVE": "6b8e23ff", "YELLOW": "ffff00ff", "GOLD": "ffd700ff",
    "GOLDENROD": "daa520ff", "ORANGE": "ffa500ff", "BROWN": "8b4513ff", "TAN": "d2b48cff", "FIREBRICK": "b22222ff",
    "RED": "ff0000ff", "SCARLET": "ff341cff", "CORAL": "ff7f50ff", "SALMON": "fa8072ff", "PINK": "ff69b4ff",
    "MAGENTA": "ff00ffff", "PURPLE": "a020f0ff", "VIOLET": "ee82eeff", "MAROON": "b03060ff",
    "RED_TEXT_COLOR": "ff6563ff", "GREEN_TEXT_COLOR": "7fff00ff", "GOLD_COLOR": "efc851ff",
}
# AbstractPotion.initializeColor(): (liquid, hybrid, spots) for each PotionColor; None means that layer is not drawn.
POTION_COLOR_TABLE = {
    "BLUE": ("SKY", None, None), "WHITE": ("WHITE", "LIGHT_GRAY", None), "FAIRY": ("CLEAR", None, "WHITE"),
    "ENERGY": ("GOLD", None, None), "EXPLOSIVE": ("ORANGE", None, None), "FIRE": ("RED", "ORANGE", None),
    "GREEN": ("CHARTREUSE", None, None), "POISON": ("LIME", None, "FOREST"), "STRENGTH": ("DARK_GRAY", None, "CORAL"),
    "STEROID": ("DARK_GRAY", "CORAL", None), "SWIFT": ("0d429dff", None, "CYAN"), "WEAK": ("VIOLET", "MAROON", None),
    "FEAR": ("BLACK", "SCARLET", None), "ELIXIR": ("GOLD", None, "DARK_GRAY"), "ANCIENT": ("GOLD", "CYAN", None),
    "FRUIT": ("ORANGE", "LIME", None), "SNECKO": ("GREEN_TEXT_COLOR", "GOLD_COLOR", None), "SMOKE": ("GRAY", "DARK_GRAY", None),
    "ATTACK": ("RED_TEXT_COLOR", "FIREBRICK", None), "SKILL": ("FOREST", "CHARTREUSE", None), "POWER": ("NAVY", "SKY", None),
}
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


def read_class(data):
    """Constant pool and method code of a class file: (pool, {(name, descriptor): code bytes})."""
    count = struct.unpack_from(">H", data, 8)[0]
    pool, pos, i = [None] * count, 10, 1
    while i < count:
        tag = data[pos]
        if tag == 1:
            n = struct.unpack_from(">H", data, pos + 1)[0]
            pool[i] = ("utf8", data[pos + 3:pos + 3 + n].decode("utf-8", "replace"))
            pos += 3 + n
        elif tag == 3:
            pool[i] = ("int", struct.unpack_from(">i", data, pos + 1)[0])
            pos += 5
        elif tag == 4:
            pool[i] = ("float", struct.unpack_from(">f", data, pos + 1)[0])
            pos += 5
        elif tag in (5, 6):
            pos += 9
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            pool[i] = (tag, struct.unpack_from(">H", data, pos + 1)[0])
            pos += 3
        elif tag in (9, 10, 11, 12, 17, 18):
            pool[i] = (tag, *struct.unpack_from(">HH", data, pos + 1))
            pos += 5
        elif tag == 15:
            pos += 4
        else:
            raise ValueError(f"constant tag {tag}")
        i += 1

    def utf(k):
        return pool[k][1]

    pos += 6
    pos += 2 + 2 * struct.unpack_from(">H", data, pos)[0]  # interfaces

    def members(pos, keep):
        """Walk a fields or methods table starting at its count; returns the position after it."""
        count = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        for _ in range(count):
            _, name, desc, attrs = struct.unpack_from(">HHHH", data, pos)
            pos += 8
            for _ in range(attrs):
                aname, alen = struct.unpack_from(">HI", data, pos)
                if keep is not None and utf(aname) == "Code":
                    # Code: max_stack u2, max_locals u2, code_length u4, code
                    code_len = struct.unpack_from(">I", data, pos + 10)[0]
                    keep[(utf(name), utf(desc))] = data[pos + 14:pos + 14 + code_len]
                pos += 6 + alen
        return pos

    pos = members(pos, None)  # fields
    methods = {}
    members(pos, methods)
    return pool, methods


def member_ref(pool, index):
    """(class, name, descriptor) of a field or method reference."""
    _, cls, nat = pool[index]
    _, name, desc = pool[nat]
    return pool[pool[cls][1]][1], pool[name][1], pool[desc][1]


# Operand bytes after each JVM opcode a constructor can use (switches and wide are not expected there).
OPERANDS = {**{op: 1 for op in (0x10, 0x12, 0x15, 0x16, 0x17, 0x18, 0x19, 0x36, 0x37, 0x38, 0x39, 0x3a, 0xa9, 0xbc)},
            **{op: 2 for op in (0x11, 0x13, 0x14, 0x84, 0xb2, 0xb3, 0xb4, 0xb5, 0xb6, 0xb7, 0xb8, 0xbb, 0xbd, 0xc0, 0xc1,
                                0xc6, 0xc7, *range(0x99, 0xa9))},
            0xc5: 3, 0xb9: 4, 0xba: 4, 0xc8: 4, 0xc9: 4}


def potion_colors(data):
    """The (liquid, hybrid, spots) colours a potion's constructor passes to AbstractPotion: names, rrggbbaa or None.

    Potions either name a PotionColor (looked up in POTION_COLOR_TABLE) or pass three Color objects:
    new Color(int rgba8888), a named libGDX/Settings colour, or null."""
    pool, methods = read_class(data)
    code = methods.get(("<init>", "()V"))
    if code is None:
        return None
    args, last_int, pos = [], 0, 0
    while pos < len(code):
        op = code[pos]
        if op in (0x12, 0x13):  # ldc, ldc_w
            k = code[pos + 1] if op == 0x12 else struct.unpack_from(">H", code, pos + 1)[0]
            if pool[k] and pool[k][0] == "int":
                last_int = pool[k][1]
        elif op == 0x01:  # aconst_null
            args.append(None)
        elif op == 0xb2:  # getstatic
            cls, name, _ = member_ref(pool, struct.unpack_from(">H", code, pos + 1)[0])
            if cls.endswith("$PotionColor"):
                return POTION_COLOR_TABLE.get(name, ("RED", None, "RED"))
            if name in NAMED_COLORS:
                args.append(name)
        elif op == 0xb7:  # invokespecial
            cls, name, desc = member_ref(pool, struct.unpack_from(">H", code, pos + 1)[0])
            if cls == "com/badlogic/gdx/graphics/Color" and desc == "(I)V":
                args.append(f"{last_int & 0xffffffff:08x}")
            elif cls.endswith("/AbstractPotion") and name == "<init>":
                return tuple(args[-3:]) if desc.count("Color;") == 3 else None
        pos += 1 + OPERANDS.get(op, 0)
    return None


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
                data = jar.read(name)
                strings = utf8_constants(data)
                own = self._own_id(name, strings, ids)
                if not own:
                    continue
                if kind == "relic":
                    png = next((s for s in strings if s.endswith(".png") and f"images/relics/{s}" in self._names), None)
                    if png:
                        relics[own] = f"images/relics/{png}"
                elif kind == "potion":
                    layers = self._potion_layers(strings, data)
                    if layers:
                        potions[own] = layers
                else:
                    art = next((s for s in strings if s.split("/")[0] in CARD_COLORS and s in atlas), None)
                    if art:
                        r = atlas[art]
                        cards[own] = {"page": f"cards/{r['page']}", "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"]}
            self._index = {"available": True, "relics": relics, "cards": cards, "potions": potions}
        return self._index

    def _potion_layers(self, strings, data):
        """A potion's shape images and its layers' colours. Small shapes (S/M/T/H) are flat files, the rest have folders."""
        shapes = [s for s in strings if s in POTION_SHAPES]
        # Prefer a named shape: one-letter strings can also be field descriptors.
        shape = next((s for s in shapes if len(s) > 1), shapes[0] if shapes else None)
        if not shape:
            return None
        if len(shape) == 1:
            paths = {k: f"images/potion/potion_{shape.lower()}_{k}.png" for k in ("liquid", "hybrid", "spots", "glass")}
        else:
            base = f"images/potion/{shape.lower()}/"
            paths = {k: base + f"{'body' if k == 'glass' else k}.png" for k in ("liquid", "hybrid", "spots", "glass")}
        colors = potion_colors(data) or ("RED", None, "RED")
        tint = {k: None if c is None else "#" + NAMED_COLORS.get(c, c) for k, c in zip(("liquid", "hybrid", "spots"), colors)}
        return {"tint": tint, **{k: v for k, v in paths.items() if v in self._names}}

    @staticmethod
    def _own_id(class_name, strings, ids):
        """A class's own ID among the ids it mentions: the one that matches its class name, else the only one."""
        found = [s for s in strings if s in ids]
        if not found:
            return None
        simple = squash(class_name.rsplit("/", 1)[-1][:-len(".class")])
        return next((s for s in found if squash(s) == simple), found[0] if len(set(found)) == 1 else None)
