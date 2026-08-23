/**
 * Layer 1: orderedmap vs server assets — full category comparison
 * Layer 2: orderedmap internal reference integrity
 * Layer 3: server assets internal reference integrity
 *
 * Outputs to .database/extracted/audit_report.json
 */
const fs = require("fs");
const path = require("path");

const BASE = path.join(__dirname, "..");
const OUT = path.join(BASE, ".database", "extracted");
const OM = path.resolve(BASE, "..", "wf-assets-cn", "orderedmap");
const SRV = path.join(BASE, "assets");

function readJSON(p) {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; }
}
function keysOf(obj) { return obj ? Object.keys(obj).map(Number).filter((n) => !isNaN(n)) : []; }
function kv(obj) { return obj ? Object.entries(obj) : []; }

// ============ LAYER 1: Orderedmap vs Server Assets ============

const layer1 = {};

// Category definitions: {label, omFile, srvFile, keyType}
const categories = [
  { label: "items", om: "item/item.json", srv: "item_data.json" },
  { label: "characters", om: "character/character.json", srv: "character.json" },
  { label: "equipment", om: "item/equipment.json", srv: "equipment_ids.json" },
  { label: "gacha", om: "gacha/gacha.json", srv: "gacha.json" },
  { label: "manaNodes", om: "mana_board/mana_node.json", srv: "mana_node.json" },
  { label: "scoreReward", om: "reward/score_reward.json", srv: "score_reward.json" },
  { label: "rareReward", om: "reward/rare_score_reward.json", srv: "rare_score_reward.json" },
  { label: "clearReward", om: "reward/clear_reward.json", srv: "clear_reward.json" },
  { label: "boxReward", om: "box_gacha/box_reward.json", srv: "box_reward.json" },
];

console.log("=== Layer 1: orderedmap vs server assets ===\n");

for (const cat of categories) {
  const omData = readJSON(path.join(OM, cat.om));
  const srvData = readJSON(path.join(SRV, cat.srv));
  const omIds = keysOf(omData);
  const srvIds = keysOf(srvData);
  const omSet = new Set(omIds), srvSet = new Set(srvIds);
  const missFromServer = omIds.filter((id) => !srvSet.has(id));
  const onlyInServer = srvIds.filter((id) => !omSet.has(id));
  layer1[cat.label] = {
    omCount: omIds.length,
    srvCount: srvIds.length,
    missFromServer: missFromServer.length,
    onlyInServer: onlyInServer.length,
    missSamples: missFromServer.slice(0, 30),
    onlySamples: onlyInServer.slice(0, 30),
  };
  console.log(`${cat.label}: om=${omIds.length} srv=${srvIds.length}  missFromServer=${missFromServer.length}  onlyInServer=${onlyInServer.length}`);
}

// Quests: compare flattened quest IDs
console.log("");
function flattenQuests(obj) {
  const out = {};
  for (const [, group] of Object.entries(obj || {})) {
    if (!group || typeof group !== "object") continue;
    for (const [qid, qdata] of Object.entries(group)) {
      if (Array.isArray(qdata)) out[qid] = true;
    }
  }
  return out;
}
const omQuestDirs = ["quest/main_quest", "quest/ex_quest", "quest/character_quest", "quest/boss_battle_quest"];
const srvQuestFiles = ["main_quest", "advent_event_quest", "boss_battle_quest", "carnival_event_quest",
  "story_event_single_quest", "rush_event_quest", "tower_dungeon_event_quest", "world_story_event_quest",
  "score_attack_event_quest", "raid_event_quest", "challenge_dungeon_event_quest",
  "ex_quest", "daily_week_event_quest", "daily_exp_mana_event_quest",
  "expert_single_event_quest", "hard_multi_event_quest", "ranking_event_single_quest",
  "solo_time_attack_event_quest", "world_story_event_boss_battle_quest"];

let omQuests = {};
for (const f of omQuestDirs) {
  const obj = readJSON(path.join(OM, f + ".json"));
  if (obj) Object.assign(omQuests, flattenQuests(obj));
}
// Event quests
const omEvDir = path.join(OM, "quest", "event");
if (fs.existsSync(omEvDir)) {
  for (const f of fs.readdirSync(omEvDir).filter((x) => x.endsWith(".json"))) {
    const obj = readJSON(path.join(omEvDir, f));
    if (obj) Object.assign(omQuests, flattenQuests(obj));
  }
}
const omQIds = new Set(Object.keys(omQuests).map(Number));

let srvQIds = new Set();
for (const f of srvQuestFiles) {
  const obj = readJSON(path.join(SRV, f + ".json"));
  if (!obj) continue;
  // Server quests may be flat or nested
  const first = obj[Object.keys(obj)[0]];
  if (first && typeof first === "object" && !Array.isArray(first)) {
    for (const [, group] of Object.entries(obj)) {
      for (const qid of Object.keys(group || {})) srvQIds.add(Number(qid));
    }
  } else {
    for (const qid of Object.keys(obj)) srvQIds.add(Number(qid));
  }
}
const questMissServer = [...omQIds].filter((id) => !srvQIds.has(id));
const questOnlyServer = [...srvQIds].filter((id) => !omQIds.has(id));
layer1.quests = {
  omCount: omQIds.size, srvCount: srvQIds.size,
  missFromServer: questMissServer.length, onlyInServer: questOnlyServer.length,
  missSamples: questMissServer.slice(0, 50),
  onlySamples: questOnlyServer.slice(0, 50),
};
console.log(`quests: om=${omQIds.size} srv=${srvQIds.size}  missFromServer=${questMissServer.length}  onlyInServer=${questOnlyServer.length}`);

// ============ LAYER 2: Orderedmap Internal Reference Integrity ============

console.log("\n=== Layer 2: orderedmap internal references ===\n");

const omItems = new Set(keysOf(readJSON(path.join(OM, "item/item.json"))));
const omChars = new Set(keysOf(readJSON(path.join(OM, "character/character.json"))));
const omEquip = new Set(keysOf(readJSON(path.join(OM, "item/equipment.json"))));
// Equipment - server format is array
const srvEquipRaw = readJSON(path.join(SRV, "equipment_ids.json"));
const srvEquipArr = Array.isArray(srvEquipRaw) ? srvEquipRaw : keysOf(srvEquipRaw).map(Number).filter(n => !isNaN(n));

function extractRefs(fullPath) {
  const obj = readJSON(fullPath);
  if (!obj) return { items: new Set(), type1Ids: new Set() };
  const items = new Set(), t1 = new Set();
  for (const [, group] of Object.entries(obj)) {
    if (!group || typeof group !== "object") continue;
    for (const [, entries] of Object.entries(group)) {
      for (const e of (Array.isArray(entries) ? entries : [])) {
        if (!Array.isArray(e)) continue;
        if (e[1] === "0" && e[3]) items.add(Number(e[3]));
        else if (e[1] === "1" && e[6]) t1.add(Number(e[6]));
      }
    }
  }
  return { items, type1Ids: t1 };
}

const srRefs = extractRefs(path.join(OM, "reward", "score_reward.json"));
const rrRefs = extractRefs(path.join(OM, "reward", "rare_score_reward.json"));

// Check score reward item refs
const srBroken = [...srRefs.items].filter((id) => !omItems.has(id) && !omEquip.has(id));
// Check score reward type1 refs (rare pool groups)
const srType1Broken = [...srRefs.type1Ids].filter((id) => {
  const rrFile = path.join(OM, "reward", "rare_score_reward.json");
  const rrData = readJSON(rrFile);
  return !rrData || !(String(id) in rrData);
});

// Check rare reward refs
const rrBroken = [...rrRefs.items].filter((id) => !omItems.has(id) && !omEquip.has(id));

// Gacha -> character refs
const gachaData = readJSON(path.join(OM, "gacha", "gacha.json")) || {};
const gachaCharRefs = new Set();
for (const [, g] of Object.entries(gachaData)) {
  if (!Array.isArray(g)) continue;
  // Gacha format: array of values, character IDs appear in certain positions
  // Fields 15-20+ seem to be character IDs for featured characters
  for (let i = 15; i < g.length && i < 25; i++) {
    const v = Number(g[i]);
    if (!isNaN(v) && v > 0 && v < 1000000) gachaCharRefs.add(v);
  }
}
const gachaBrokenChars = [...gachaCharRefs].filter((id) => !omChars.has(id));

const layer2 = {
  scoreReward_brokenItems: srBroken.length,
  scoreReward_brokenSamples: srBroken.slice(0, 30),
  scoreReward_brokenRareGroups: srType1Broken.length,
  scoreReward_brokenRareSamples: srType1Broken.slice(0, 30),
  rareReward_brokenItems: rrBroken.length,
  rareReward_brokenSamples: rrBroken.slice(0, 30),
  gacha_brokenChars: gachaBrokenChars.length,
  gacha_brokenSamples: gachaBrokenChars.slice(0, 30),
};
console.log(`score_reward: broken items=${srBroken.length}  broken rare groups=${srType1Broken.length}`);
console.log(`rare_reward: broken items=${rrBroken.length}`);
console.log(`gacha->char: broken=${gachaBrokenChars.length}`);

// ============ LAYER 3: Server Assets Internal Reference Integrity ============

console.log("\n=== Layer 3: server assets internal references ===\n");

const srvItems = new Set(keysOf(readJSON(path.join(SRV, "item_data.json"))));
const srvChars = new Set(keysOf(readJSON(path.join(SRV, "character.json"))));
const srvEquip = new Set(keysOf(readJSON(path.join(SRV, "equipment_ids.json"))));

// Check server score reward refs
const srvSR = extractRefs(path.join(SRV, "score_reward.json"));
const srvRR = extractRefs(path.join(SRV, "rare_score_reward.json"));
const srvCR = extractRefs(path.join(SRV, "clear_reward.json"));
const srvBR = extractRefs(path.join(SRV, "box_reward.json"));

function checkServerRefs(label, refSet) {
  const broken = [...refSet.items].filter((id) => !srvItems.has(id) && !srvEquip.has(id));
  const type1Broken = [...refSet.type1Ids].filter((id) => {
    const rrData = readJSON(path.join(SRV, "rare_score_reward.json"));
    return !rrData || !(String(id) in rrData);
  });
  console.log(`${label}: broken items=${broken.length}  broken rare groups=${type1Broken.length}`);
  return { brokenItems: broken, brokenRare: type1Broken };
}

const l3sr = checkServerRefs("score_reward", srvSR);
const l3rr = checkServerRefs("rare_reward", srvRR);
const l3cr = checkServerRefs("clear_reward", srvCR);
const l3br = checkServerRefs("box_reward", srvBR);

// Server gacha -> chars
const srvGacha = readJSON(path.join(SRV, "gacha.json")) || {};
const srvGachaCharRefs = new Set();
for (const [, g] of Object.entries(srvGacha)) {
  if (!Array.isArray(g)) continue;
  for (let i = 15; i < g.length && i < 25; i++) {
    const v = Number(g[i]);
    if (!isNaN(v) && v > 0 && v < 1000000) srvGachaCharRefs.add(v);
  }
}
const srvGachaBroken = [...srvGachaCharRefs].filter((id) => !srvChars.has(id));

// Server event quest -> reward group refs
const srvQuestGroupRefs = {};
for (const f of srvQuestFiles) {
  const obj = readJSON(path.join(SRV, f + ".json"));
  if (!obj) continue;
  for (const [qid, qdata] of Object.entries(obj)) {
    if (!qdata || typeof qdata !== "object") continue;
    // Check for scoreRewardGroupId field
    if (qdata.scoreRewardGroupId) {
      const gid = Number(qdata.scoreRewardGroupId);
      const srExists = String(gid) in (readJSON(path.join(SRV, "score_reward.json")) || {});
      if (!srExists) {
        if (!srvQuestGroupRefs[qid]) srvQuestGroupRefs[qid] = { missingGroups: [], file: f };
        srvQuestGroupRefs[qid].missingGroups.push(gid);
      }
    }
  }
}
const questGroupIssues = Object.keys(srvQuestGroupRefs);
console.log(`quests with missing scoreRewardGroup: ${questGroupIssues.length}`);

const layer3 = {
  scoreReward_brokenItems: l3sr.brokenItems.length,
  scoreReward_brokenRare: l3sr.brokenRare.length,
  rareReward_brokenItems: l3rr.brokenItems.length,
  clearReward_brokenItems: l3cr.brokenItems.length,
  boxReward_brokenItems: l3br.brokenItems.length,
  gacha_brokenChars: srvGachaBroken.length,
  questMissingGroups: questGroupIssues.length,
  questMissingDetails: questGroupIssues.slice(0, 20).map((q) => ({
    questId: q,
    ...srvQuestGroupRefs[q],
  })),
  // Collect ALL broken item IDs across all reward tables
  allBrokenItemRefs: [...new Set([
    ...l3sr.brokenItems,
    ...l3rr.brokenItems,
    ...l3cr.brokenItems,
    ...l3br.brokenItems,
  ])].sort((a, b) => a - b),
};

// ============ WRITE REPORT ============

const report = { layer1, layer2, layer3 };
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, "audit_report.json"), JSON.stringify(report, null, 2));
console.log("\nReport saved to .database/extracted/audit_report.json");

// Summary
console.log("\n====== SUMMARY ======");
console.log(`Layer 1 (coverage gaps):`);
for (const [k, v] of Object.entries(layer1)) {
  if (v.missFromServer > 0) console.log(`  ${k}: ${v.missFromServer} missing from server (${v.omCount} in orderedmap, ${v.srvCount} in server)`);
}
console.log(`\nLayer 2 (orderedmap integrity):`);
console.log(`  score_reward broken items: ${layer2.scoreReward_brokenItems}`);
console.log(`  score_reward broken rare groups: ${layer2.scoreReward_brokenRareGroups}`);
console.log(`  rare_reward broken items: ${layer2.rareReward_brokenItems}`);
console.log(`  gacha broken char refs: ${layer2.gacha_brokenChars}`);
console.log(`\nLayer 3 (server integrity):`);
console.log(`  total broken item refs: ${layer3.allBrokenItemRefs.length}`);
console.log(`  broken IDs: ${layer3.allBrokenItemRefs.join(", ")}`);
console.log(`  score_reward broken: ${layer3.scoreReward_brokenItems}`);
console.log(`  gacha broken chars: ${layer3.gacha_brokenChars}`);
console.log(`  quests with missing groups: ${layer3.questMissingGroups}`);
