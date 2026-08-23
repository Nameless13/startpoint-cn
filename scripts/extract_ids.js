/**
 * Phase 1: Extract ID sets from CN + GL orderedmap for CDN comparison.
 * Outputs: .database/extracted/cn_ids.json + gl_ids.json
 */
const fs = require("fs");
const path = require("path");

const BASE = path.join(__dirname, "..");
const OUT = path.join(BASE, ".database", "extracted");
const CN = path.resolve(BASE, "..", "wf-assets-cn", "orderedmap");
const GL = path.resolve(BASE, "..", "wf-assets-gl", "orderedmap");

function readJSON(filePath) {
  try { return JSON.parse(fs.readFileSync(filePath, "utf8")); } catch { return null; }
}
function keysOf(obj) { return obj ? Object.keys(obj) : []; }

// Flatten nested quest: {group: {questId: [...]}} or deeper
function flattenQuests(obj) {
  const out = {};
  for (const [, group] of Object.entries(obj)) {
    if (!group || typeof group !== "object") continue;
    for (const [qid, qdata] of Object.entries(group)) {
      if (Array.isArray(qdata)) out[qid] = true;
    }
  }
  return out;
}

// Extract item/rare-group IDs from score_reward and rare_score_reward tables.
// Score reward: [name, "0", cat, itemId, count, field5, "", ""]  → field[3] = itemId
//               [name, "1", "",   "",     "",    "",     groupId, rarity] → field[6] = rareGroupId
// Rare score:   [name, "0", cat, itemId, rate, "false"] → field[3] = itemId
// Clear reward / box reward: different formats, skip item extraction.
function extractRewardItemRefs(filePath) {
  const obj = readJSON(filePath);
  if (!obj) return new Set();
  const ids = new Set();
  for (const [, group] of Object.entries(obj)) {
    if (!group || typeof group !== "object") continue;
    for (const [, entries] of Object.entries(group)) {
      const list = Array.isArray(entries) ? entries : [];
      for (const entry of list) {
        if (!Array.isArray(entry)) continue;
        const t = entry[1];
        if (t === "0" && entry[3]) ids.add(Number(entry[3]));
        else if (t === "1" && entry[6]) {
          const v = Number(entry[6]);
          if (!isNaN(v) && v > 0) ids.add(v);
        }
      }
    }
  }
  return ids;
}

function extractAll(baseDir, label) {
  console.log(`\n=== ${label} ===`);
  const d = {};

  d.items = keysOf(readJSON(path.join(baseDir, "item", "item.json")) || {}).map(Number);
  d.characters = keysOf(readJSON(path.join(baseDir, "character", "character.json")) || {}).map(Number);
  d.equipment = keysOf(readJSON(path.join(baseDir, "item", "equipment.json")) || {}).map(Number);
  d.gacha = keysOf(readJSON(path.join(baseDir, "gacha", "gacha.json")) || {}).map(Number);
  console.log(`  items=${d.items.length} chars=${d.characters.length} equip=${d.equipment.length} gacha=${d.gacha.length}`);

  // Quests
  d.quests = {};
  const qDir = path.join(baseDir, "quest");
  for (const cat of ["main_quest", "ex_quest", "character_quest", "boss_battle_quest"]) {
    const obj = readJSON(path.join(qDir, cat + ".json"));
    if (obj) Object.assign(d.quests, flattenQuests(obj));
  }
  const evDir = path.join(qDir, "event");
  if (fs.existsSync(evDir)) {
    for (const f of fs.readdirSync(evDir).filter((x) => x.endsWith(".json"))) {
      const obj = readJSON(path.join(evDir, f));
      if (obj) Object.assign(d.quests, flattenQuests(obj));
    }
  }
  d.questIds = Object.keys(d.quests).map(Number);
  console.log(`  quests=${d.questIds.length}`);

  // Rewards
  d.scoreRewardGroups = keysOf(readJSON(path.join(baseDir, "reward", "score_reward.json")) || {}).map(Number);
  d.scoreRewardRefs = [...extractRewardItemRefs(path.join(baseDir, "reward", "score_reward.json"))];
  d.rareScoreGroups = keysOf(readJSON(path.join(baseDir, "reward", "rare_score_reward.json")) || {}).map(Number);
  d.rareScoreRefs = [...extractRewardItemRefs(path.join(baseDir, "reward", "rare_score_reward.json"))];
  d.clearRewards = keysOf(readJSON(path.join(baseDir, "reward", "clear_reward.json")) || {}).map(Number);
  d.boxRewards = keysOf(readJSON(path.join(baseDir, "box_gacha", "box_reward.json")) || {}).map(Number);
  console.log(`  scoreReward=${d.scoreRewardGroups.length}(refs:${d.scoreRewardRefs.length}) rareScore=${d.rareScoreGroups.length} clear=${d.clearRewards.length} box=${d.boxRewards.length}`);

  // Shops
  d.shops = {};
  const sDir = path.join(baseDir, "shop");
  if (fs.existsSync(sDir))
    for (const f of fs.readdirSync(sDir).filter((x) => x.endsWith(".json")))
      d.shops[f] = keysOf(readJSON(path.join(sDir, f)) || {}).length;

  return d;
}

// ---- Run ----
console.log("Phase 1: Extracting CDN ID sets");
console.log("CN:", CN, "\nGL:", GL);

const cn = extractAll(CN, "CN");
const gl = extractAll(GL, "GL");

fs.mkdirSync(OUT, { recursive: true });

const makeOut = (d) => ({
  items: d.items,
  characters: d.characters,
  equipment: d.equipment,
  gacha: d.gacha,
  quests: d.questIds,
  scoreRewardGroups: d.scoreRewardGroups,
  scoreRewardRefs: d.scoreRewardRefs,
  rareScoreGroups: d.rareScoreGroups,
  rareScoreRefs: d.rareScoreRefs,
  clearRewards: d.clearRewards,
  boxRewards: d.boxRewards,
  shops: d.shops,
});

fs.writeFileSync(path.join(OUT, "cn_ids.json"), JSON.stringify(makeOut(cn), null, 2));
fs.writeFileSync(path.join(OUT, "gl_ids.json"), JSON.stringify(makeOut(gl), null, 2));
console.log("\nSaved to .database/extracted/");

// ---- Compare ----
console.log("\n=== CN vs GL ===");
const sets = { cnItem: new Set(cn.items), glItem: new Set(gl.items), cnChar: new Set(cn.characters), glChar: new Set(gl.characters), cnQuest: new Set(cn.questIds), glQuest: new Set(gl.questIds), cnGacha: new Set(cn.gacha), glGacha: new Set(gl.gacha) };

function diff(label, a, b) {
  const ao = [...a].filter((x) => !b.has(x)), bo = [...b].filter((x) => !a.has(x));
  console.log(`${label}: CN=${a.size} GL=${b.size}  CN-only=${ao.length}  GL-only=${bo.length}`);
  if (ao.length > 0 && ao.length <= 30) console.log(`  CN-only: ${ao.join(", ")}`);
  if (bo.length > 0 && bo.length <= 30) console.log(`  GL-only: ${bo.join(", ")}`);
}
diff("Items    ", sets.cnItem, sets.glItem);
diff("Characters", sets.cnChar, sets.glChar);
diff("Quests   ", sets.cnQuest, sets.glQuest);
diff("Gacha    ", sets.cnGacha, sets.glGacha);

// Broken refs
const allRefs = new Set([...cn.scoreRewardRefs, ...cn.rareScoreRefs]);
const broken = [...allRefs].filter((id) => !sets.cnItem.has(id) && !new Set(cn.equipment).has(id));
console.log("\n=== CN Internal Integrity ===");
console.log("Total unique item refs (score + rare reward): " + allRefs.size);
console.log("Broken refs (not in items or equipment): " + broken.length);
if (broken.length <= 100) console.log("  IDs: " + broken.sort((a,b)=>a-b).join(", "));
const knownBad = [70022, 70023, 70024];
const ks = knownBad.map((id) => id + "=" + (sets.cnItem.has(id) ? "FOUND" : "MISSING"));
console.log("Known JP items: " + ks.join(", "));
