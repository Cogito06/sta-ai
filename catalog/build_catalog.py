"""Build the catalog files from raw_catalog.json (dumped by game-mod, see catalogDumpPath).

Keeps what an Ironclad run can meet: red, colorless, curse and status cards, relics
that are not tied to another class, and all potions. Card text gets its numbers filled in
and the game's markup removed, so it reads like the card face.
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
CARD_COLORS = {"RED", "COLORLESS", "CURSE"}
OTHER_CLASS_RELIC_COLORS = {"GREEN", "BLUE", "PURPLE"}


def clean_text(text):
    text = re.sub(r"\s*\bNL\b\s*", " ", text)
    text = re.sub(r"\[[RGBW]\]", "[E]", text)
    text = re.sub(r"#[a-z]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def card_text(values):
    text = values["raw_description"]
    for marker, key in (("!D!", "damage"), ("!B!", "block"), ("!M!", "magic_number")):
        text = text.replace(marker, str(values[key]))
    return clean_text(text)


def card_version(values):
    version = {"name": values["name"], "cost": values["cost"]}
    for key in ("damage", "block", "magic_number"):
        if values[key] >= 0:
            version[key] = values[key]
    version["keywords"] = [k.title() for k in ("exhaust", "ethereal", "innate", "retain") if values[k]]
    version["text"] = card_text(values)
    template = clean_text(values["raw_description"])
    for marker, key in (("!D!", "{damage}"), ("!B!", "{block}"), ("!M!", "{magic_number}")):
        template = template.replace(marker, key)
    version["template"] = template
    return version


def build_cards(raw):
    cards = {}
    for card in raw["cards"]:
        if card["color"] not in CARD_COLORS:
            continue
        entry = {k: card[k] for k in ("id", "color", "type", "rarity", "target")}
        entry["base"] = card_version(card["base"])
        if "upgraded" in card:
            entry["upgraded"] = card_version(card["upgraded"])
        cards[card["id"]] = entry
    return dict(sorted(cards.items()))


def build_relics(raw):
    relics = {}
    for relic in raw["relics"]:
        # The class lists come after the shared ones in the dump, so a class color wins.
        entry = relics.setdefault(relic["id"], {"id": relic["id"], "name": relic["name"], "color": "ANY"})
        if relic["color"] != "ANY":
            entry["color"] = relic["color"]
        else:
            entry["tier"] = relic["tier"]
        entry["text"] = clean_text(relic["description"])
    kept = {k: v for k, v in relics.items() if v["color"] not in OTHER_CLASS_RELIC_COLORS}
    return dict(sorted(kept.items()))


def build_potions(raw):
    potions = {}
    for potion in raw["potions"]:
        potions[potion["id"]] = {
            "id": potion["id"],
            "name": potion["name"],
            "rarity": potion["rarity"],
            "requires_target": potion["requires_target"],
            "text": clean_text(potion["description"]),
        }
    return dict(sorted(potions.items()))


def main():
    raw = json.loads((HERE / "raw_catalog.json").read_text(encoding="utf-8"))
    assert raw["language"] == "ENG", "dump the catalog with the game set to English"
    for name, data in (("cards", build_cards(raw)), ("relics", build_relics(raw)), ("potions", build_potions(raw))):
        (HERE / f"{name}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{name}: {len(data)}")


if __name__ == "__main__":
    main()
