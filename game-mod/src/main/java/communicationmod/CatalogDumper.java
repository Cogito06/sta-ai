package communicationmod;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.megacrit.cardcrawl.cards.AbstractCard;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.helpers.CardLibrary;
import com.megacrit.cardcrawl.helpers.PotionHelper;
import com.megacrit.cardcrawl.helpers.RelicLibrary;
import com.megacrit.cardcrawl.potions.AbstractPotion;
import com.megacrit.cardcrawl.relics.AbstractRelic;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;

/**
 * sts-ai: writes the game's static data (cards with base and upgraded values, relics, potions)
 * to a JSON file, so the catalog comes from the game itself instead of being written by hand.
 * Runs once after the game has initialized when the "catalogDumpPath" option is set.
 */
public class CatalogDumper {
    private static final Logger logger = LogManager.getLogger(CatalogDumper.class.getName());

    public static void dump(String path) {
        HashMap<String, Object> catalog = new LinkedHashMap<>();
        catalog.put("language", Settings.language.name());
        catalog.put("cards", dumpCards());
        catalog.put("relics", dumpRelics());
        catalog.put("potions", dumpPotions());
        Gson gson = new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
        Path out = Paths.get(path);
        try {
            if (out.getParent() != null) {
                Files.createDirectories(out.getParent());
            }
            try (Writer writer = new OutputStreamWriter(Files.newOutputStream(out), StandardCharsets.UTF_8)) {
                gson.toJson(catalog, writer);
            }
            logger.info("Catalog written to " + out.toAbsolutePath());
        } catch (IOException e) {
            logger.error("Could not write catalog to " + path, e);
        }
    }

    private static ArrayList<Object> dumpCards() {
        ArrayList<Object> cards = new ArrayList<>();
        for (AbstractCard libraryCard : CardLibrary.cards.values()) {
            try {
                HashMap<String, Object> json = new LinkedHashMap<>();
                json.put("id", libraryCard.cardID);
                json.put("color", libraryCard.color.name());
                json.put("type", libraryCard.type.name());
                json.put("rarity", libraryCard.rarity.name());
                json.put("target", libraryCard.target.name());
                AbstractCard base = libraryCard.makeCopy();
                json.put("base", convertCardValues(base));
                if (base.canUpgrade()) {
                    AbstractCard upgraded = libraryCard.makeCopy();
                    upgraded.upgrade();
                    json.put("upgraded", convertCardValues(upgraded));
                }
                cards.add(json);
            } catch (Exception e) {
                logger.error("Could not dump card " + libraryCard.cardID, e);
            }
        }
        return cards;
    }

    private static HashMap<String, Object> convertCardValues(AbstractCard card) {
        HashMap<String, Object> json = new LinkedHashMap<>();
        json.put("name", card.name);
        json.put("cost", card.cost);
        json.put("damage", card.baseDamage);
        json.put("block", card.baseBlock);
        json.put("magic_number", card.baseMagicNumber);
        json.put("exhaust", card.exhaust);
        json.put("ethereal", card.isEthereal);
        json.put("innate", card.isInnate);
        json.put("retain", card.selfRetain);
        json.put("raw_description", card.rawDescription);
        return json;
    }

    private static ArrayList<Object> dumpRelics() {
        ArrayList<Object> relics = new ArrayList<>();
        addRelics(relics, RelicLibrary.starterList, null);
        addRelics(relics, RelicLibrary.commonList, null);
        addRelics(relics, RelicLibrary.uncommonList, null);
        addRelics(relics, RelicLibrary.rareList, null);
        addRelics(relics, RelicLibrary.bossList, null);
        addRelics(relics, RelicLibrary.shopList, null);
        addRelics(relics, RelicLibrary.specialList, null);
        addRelics(relics, RelicLibrary.redList, "RED");
        addRelics(relics, RelicLibrary.greenList, "GREEN");
        addRelics(relics, RelicLibrary.blueList, "BLUE");
        addRelics(relics, RelicLibrary.whiteList, "PURPLE");
        return relics;
    }

    private static void addRelics(ArrayList<Object> relics, ArrayList<AbstractRelic> list, String color) {
        for (AbstractRelic relic : list) {
            try {
                HashMap<String, Object> json = new LinkedHashMap<>();
                json.put("id", relic.relicId);
                json.put("name", relic.name);
                json.put("tier", relic.tier.name());
                json.put("color", color == null ? "ANY" : color);
                json.put("description", relic.description);
                relics.add(json);
            } catch (Exception e) {
                logger.error("Could not dump relic " + relic.relicId, e);
            }
        }
    }

    private static ArrayList<Object> dumpPotions() {
        ArrayList<Object> potions = new ArrayList<>();
        for (String id : PotionHelper.getPotions(AbstractPlayer.PlayerClass.IRONCLAD, true)) {
            try {
                AbstractPotion potion = PotionHelper.getPotion(id);
                HashMap<String, Object> json = new LinkedHashMap<>();
                json.put("id", potion.ID);
                json.put("name", potion.name);
                json.put("rarity", potion.rarity.name());
                json.put("potency", potion.getPotency());
                json.put("requires_target", potion.isThrown);
                json.put("description", potion.description);
                potions.add(json);
            } catch (Exception e) {
                logger.error("Could not dump potion " + id, e);
            }
        }
        return potions;
    }
}
