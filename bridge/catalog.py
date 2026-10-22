"""Static game data (catalog/*.json), looked up by the game's own ids."""
import json
import pathlib

CATALOG_DIR = pathlib.Path(__file__).resolve().parent.parent / "catalog"


class Catalog:
    def __init__(self, directory=CATALOG_DIR):
        self.cards = self._load(directory / "cards.json")
        self.relics = self._load(directory / "relics.json")
        self.potions = self._load(directory / "potions.json")

    @staticmethod
    def _load(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def card_version(self, card_id, upgrades=0):
        card = self.cards.get(card_id)
        if card is None:
            return None
        if upgrades and "upgraded" in card:
            return card["upgraded"]
        return card["base"]

    def card_name(self, card_id, upgrades=0, fallback=None):
        version = self.card_version(card_id, upgrades)
        if version is None:
            return fallback or card_id
        if card_id == "Searing Blow" and upgrades > 1:
            return f"Searing Blow+{upgrades}"
        return version["name"]

    def card_text(self, card_id, upgrades=0):
        version = self.card_version(card_id, upgrades)
        return version["text"] if version else None

    def relic_text(self, relic_id):
        relic = self.relics.get(relic_id)
        return relic["text"] if relic else None

    def potion_text(self, potion_id):
        potion = self.potions.get(potion_id)
        return potion["text"] if potion else None
