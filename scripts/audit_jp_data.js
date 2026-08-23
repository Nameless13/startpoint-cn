/**
 * Full JP data contamination audit:
 *   1. CN vs GL ID comparison
 *   2. Reference integrity (P0: broken refs → C8601)
 *   3. Risk classification (P0/P1/P2)
 *
 * Outputs to .database/extracted/audit_*.json
 */
const fs = require("fs");
const path = require("path");

const BASE = path.join(__dirname, "..");
const OUT = path.join(BASE, ".database", "extracted");
const CN = path.resolve(BASE, "..", "wf-assets-cn", "orderedmap");
const GL = path.resolve(BASE, "..", "wf-assets-gl", "orderedmap");

function rd(p) {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return null; }
}
function keys(obj) { return obj ? Object.keys(obj).map(Number).filter((n) => !isNaN(n)) : []; }

// ===== 1. Build ID sets from both orderedmaps =====

function buildSets(baseDir, label) {
  console.log(`  Building ${label} sets...`);
  const s = {};

  s.items = new Set(keys(rd(path.join(baseDir, "item", "item.json"))));
  s.characters = new Set(keys(rd(path.join(baseDir, "character", "character.json"))));
  s.equipment = new Set(keys(rd(path.join(baseDir, "item", "equipment.json"))));
  s.gacha = new Set(keys(rd(path.join(baseDir, "gacha", "gacha.json"))));
  s.scoreRewardGroups = new Set(keys(rd(path.join(baseDir, "reward", "score_reward.json"))));
  s.rareRewardGroups = new Set(keys(rd(path.join(baseDir, "reward", "rare_score_reward.json"))));
  s.clearRewards = new Set(keys(rd(path.join(baseDir, "reward", "clear_reward.json"))));

  // Flatten quests
  s.quests = new Set();
  for (const cat of ["main_quest", "ex_quest", "character_quest", "boss_battle_quest"]) {
    const obj = rd(path.join(baseDir, "quest", cat + ".json"));
    if (!obj) continue;
    for (const [, g] of Object.entries(obj)) {
      if (!g || typeof g !== "object") continue;
      for (const [qid, qd] of Object.entries(g))
        if (Array.isArray(qd)) s.quests.add(Number(qid));
    }
  }
  const evDir = path.join(baseDir, "quest", "event");
  if (fs.existsSync(evDir)) {
    for (const f of fs.readdirSync(evDir).filter((x) => x.endsWith(".json"))) {
      const obj = rd(path.join(evDir, f));
      if (!obj) continue;
      for (const [, g] of Object.entries(obj)) {
        if (!g || typeof g !== "object") continue;
        for (const [qid, qd] of Object.entries(g))
          if (Array.isArray(qd)) s.quests.add(Number(qid));
      }
    }
  }

  console.log(`    items=${s.items.size} chars=${s.characters.size} equip=${s.equipment.size} gacha=${s.gacha.size} quests=${s.quests.size}`);
  return s;
}

// ===== 2. ID comparison =====

function diffSet(label, cnSet, glSet) {
  const cnOnly = [...cnSet].filter((x) => !glSet.has(x)).sort((a, b) => a - b);
  const glOnly = [...glSet].filter((x) => !cnSet.has(x)).sort((a, b) => a - b);
  const shared = [...cnSet].filter((x) => glSet.has(x));
  return { cnCount: cnSet.size, glCount: glSet.size, cnOnly, glOnly, sharedCount: shared.length };
}

// ===== 3. Reference integrity =====

/** Parse reward entries: score_reward nested format */
function extractRewardRefs(dir, file) {
  const obj = rd(path.join(dir, file));
  if (!obj) return { itemRefs: new Map(), rareRefs: new Map() };
  const itemRefs = new Map(); // itemId → [{source: "score_reward", groupId, position}]
  const rareRefs = new Map(); // rareGroupId → [{source, groupId, position}]
  for (const [gid, group] of Object.entries(obj)) {
    if (!group || typeof group !== "object") continue;
    for (const [pos, entries] of Object.entries(group)) {
      const list = Array.isArray(entries) ? entries : [];
      for (const e of list) {
        if (!Array.isArray(e)) continue;
        const t = e[1];
        if (t === "0" && e[3]) {
          const id = Number(e[3]);
          if (!itemRefs.has(id)) itemRefs.set(id, []);
          const refs = itemRefs.get(id);
          if (refs.length < 5) refs.push({ source: file.replace(".json", ""), groupId: Number(gid), position: Number(pos) });
        } else if (t === "1" && e[6]) {
          const id = Number(e[6]);
          if (!rareRefs.has(id)) rareRefs.set(id, []);
          const refs = rareRefs.get(id);
          if (refs.length < 5) refs.push({ source: file.replace(".json", ""), groupId: Number(gid), position: Number(pos) });
        }
      }
    }
  }
  return { itemRefs, rareRefs };
}

/** Extract gacha → character refs */
function extractGachaCharRefs(dir) {
  const obj = rd(path.join(dir, "gacha", "gacha.json"));
  if (!obj) return new Map();
  const refs = new Map();
  for (const [gid, g] of Object.entries(obj)) {
    if (!Array.isArray(g)) continue;
    // Extract character IDs from various positions
    for (let i = 15; i < g.length && i < 30; i++) {
      const cid = Number(g[i]);
      if (!isNaN(cid) && cid > 0 && cid < 999999) {
        if (!refs.has(cid)) refs.set(cid, []);
        const r = refs.get(cid);
        if (r.length < 3) r.push({ source: "gacha", gachaId: Number(gid) });
      }
    }
  }
  return refs;
}

/** Extract quest → scoreRewardGroup refs */
function extractQuestGroupRefs(dir) {
  const refs = new Map();
  const evDir = path.join(dir, "quest", "event");
  if (!fs.existsSync(evDir)) return refs;
  for (const f of fs.readdirSync(evDir).filter((x) => x.endsWith(".json"))) {
    const obj = rd(path.join(evDir, f));
    if (!obj) continue;
    for (const [, g] of Object.entries(obj)) {
      if (!g || typeof g !== "object") continue;
      for (const [qid, qd] of Object.entries(g)) {
        if (!Array.isArray(qd)) continue;
        // scoreRewardGroupId position varies by quest type
        // Try multiple common positions
        for (const pos of [70, 71, 72, 76, 69, 66, 65]) {
          if (qd[pos] && qd[pos] !== "" && qd[pos] !== "0" && qd[pos] !== "(None)") {
            const gid = Number(qd[pos]);
            if (!isNaN(gid) && gid > 0) {
              if (!refs.has(gid)) refs.set(gid, []);
              const r = refs.get(gid);
              if (r.length < 3) r.push({ source: f.replace(".json", ""), questId: Number(qid) });
              break;
            }
          }
        }
      }
    }
  }
  return refs;
}

/** Check broken refs and classify */
function checkBroken(label, refMap, validSet, alternateSet) {
  const broken = [];
  for (const [id, sources] of refMap) {
    const idNum = Number(id);
    if (validSet.has(idNum)) continue;
    if (alternateSet && alternateSet.has(idNum)) continue;
    broken.push({ id: idNum, sources });
  }
  return broken;
}

// ===== 4. Risk classification =====

/** Read item date data to classify JP vs CN timing */
function getItemDate(dir, id) {
  const obj = rd(path.join(dir, "item", "item.json"));
  if (!obj || !obj[String(id)]) return null;
  const fields = obj[String(id)];
  // items have nested array: [[field0, field1, ...]]
  const inner = fields[0];
  const start = inner[19] || null;
  const end = inner[20] || null;
  return { start, end };
}

function getCharDate(dir, id) {
  const obj = rd(path.join(dir, "character", "character.json"));
  if (!obj || !obj[String(id)]) return null;
  const fields = obj[String(id)][0];
  // Character dates might be in different positions
  return { start: fields[19] || null, end: fields[20] || null };
}

// ===== MAIN =====

console.log("=== JP Data Contamination Audit ===\n");
fs.mkdirSync(OUT, { recursive: true });

// Step 1: Build sets
console.log("Step 1: Building ID sets...");
const cn = buildSets(CN, "CN");
const gl = buildSets(GL, "GL");

// Step 2: Compare
console.log("\nStep 2: CN vs GL comparison...");
const comparison = {
  items: diffSet("items", cn.items, gl.items),
  characters: diffSet("characters", cn.characters, gl.characters),
  equipment: diffSet("equipment", cn.equipment, gl.equipment),
  gacha: diffSet("gacha", cn.gacha, gl.gacha),
  quests: diffSet("quests", cn.quests, gl.quests),
  scoreRewardGroups: diffSet("scoreReward", cn.scoreRewardGroups, gl.scoreRewardGroups),
};

// Step 3: Reference integrity (P0 checks)
console.log("\nStep 3: Reference integrity...");

// Score reward → item refs
const srRefs = extractRewardRefs(CN, "reward/score_reward.json");
const rrRefs = extractRewardRefs(CN, "reward/rare_score_reward.json");
const crRefs = extractRewardRefs(CN, "reward/clear_reward.json");

// Combine all item refs (score + rare + clear)
const allItemRefs = new Map();
for (const refMap of [srRefs.itemRefs, rrRefs.itemRefs, crRefs.itemRefs]) {
  for (const [id, sources] of refMap) {
    if (!allItemRefs.has(id)) allItemRefs.set(id, []);
    allItemRefs.get(id).push(...sources);
  }
}

const allRareRefs = new Map();
for (const refMap of [srRefs.rareRefs, rrRefs.rareRefs]) {
  for (const [id, sources] of refMap) {
    if (!allRareRefs.has(id)) allRareRefs.set(id, []);
    allRareRefs.get(id).push(...sources);
  }
}

// Check: score reward → item exists?
const p0_brokenItemRefs = checkBroken("score→item", allItemRefs, cn.items, cn.equipment);
console.log(`  score→item broken: ${p0_brokenItemRefs.length}`);

// Check: rare pool group → exists in rare_reward?
for (const [id, sources] of allRareRefs) {
  if (!cn.rareRewardGroups.has(Number(id))) {
    if (!p0_brokenItemRefs.find((x) => x.id === Number(id))) {
      p0_brokenItemRefs.push({ id: Number(id), sources: sources.map((s) => ({ ...s, note: "rare group not found" })) });
    }
  }
}

// Gacha → character refs
const gachaCharRefs = extractGachaCharRefs(CN);
const p0_brokenGachaChars = checkBroken("gacha→char", gachaCharRefs, cn.characters);
console.log(`  gacha→char broken: ${p0_brokenGachaChars.length}`);

// Quest → scoreRewardGroup refs
const questGroupRefs = extractQuestGroupRefs(CN);
const p0_brokenQuestGroups = [];
for (const [gid, sources] of questGroupRefs) {
  const gidNum = Number(gid);
  if (!cn.scoreRewardGroups.has(gidNum)) {
    p0_brokenQuestGroups.push({ id: gidNum, sources });
  }
}
console.log(`  quest→group broken: ${p0_brokenQuestGroups.length}`);

// ===== Step 4: Risk classification =====
console.log("\nStep 4: Risk classification...");

const P0 = []; // Will cause C8601
const P1 = []; // JP items with definition but CDN display data unknown
const P2 = []; // Redundant data, not referenced

// P0: broken refs
for (const r of p0_brokenItemRefs) {
  P0.push({ type: "broken_ref", category: "item", id: r.id, sources: r.sources });
}
for (const r of p0_brokenGachaChars) {
  P0.push({ type: "broken_ref", category: "character", id: r.id, sources: r.sources });
}
for (const r of p0_brokenQuestGroups) {
  P0.push({ type: "broken_ref", category: "scoreRewardGroup", id: r.id, sources: r.sources });
}

// P1: CN-only items that ARE referenced by reward tables → might work but CDN display uncertain
const cnOnlyItemSet = new Set(comparison.items.cnOnly);
for (const [id, sources] of allItemRefs) {
  if (cnOnlyItemSet.has(Number(id)) && !P0.find((x) => x.id === Number(id))) {
    const date = getItemDate(CN, id);
    P1.push({ type: "cn_only_item_referenced", id: Number(id), sources, date, risk: "CDN display data may be missing" });
  }
}

// P1: CN-only characters referenced by gacha
const cnOnlyCharSet = new Set(comparison.characters.cnOnly);
for (const [id, sources] of gachaCharRefs) {
  if (cnOnlyCharSet.has(Number(id)) && !P0.find((x) => x.id === Number(id))) {
    P1.push({ type: "cn_only_char_referenced", id: Number(id), sources, risk: "May work if CDN has display data" });
  }
}

// P2: CN-only items/characters/gacha NOT referenced by any system
for (const id of comparison.items.cnOnly) {
  if (!allItemRefs.has(id) && !P0.find((x) => x.id === id) && !P1.find((x) => x.id === id)) {
    if (P2.length < 200) P2.push({ type: "cn_only_unreferenced", category: "item", id });
  }
}
for (const id of comparison.characters.cnOnly) {
  if (!gachaCharRefs.has(id) && !P0.find((x) => x.id === id) && !P1.find((x) => x.id === id)) {
    if (P2.length < 200) P2.push({ type: "cn_only_unreferenced", category: "character", id });
  }
}
for (const id of comparison.gacha.cnOnly) {
  if (P2.length < 200) P2.push({ type: "cn_only_unreferenced", category: "gacha", id });
}

console.log(`  P0 (will crash): ${P0.length}`);
console.log(`  P1 (referenced, display uncertain): ${P1.length}`);
console.log(`  P2 (unreferenced redundancy): ${P2.length}`);

// ===== Write reports =====

fs.writeFileSync(path.join(OUT, "audit_cn_only.json"), JSON.stringify({
  items: comparison.items.cnOnly,
  characters: comparison.characters.cnOnly,
  equipment: comparison.equipment.cnOnly,
  gacha: comparison.gacha.cnOnly,
  quests: comparison.quests.cnOnly,
  scoreRewardGroups: comparison.scoreRewardGroups.cnOnly,
}, null, 2));

fs.writeFileSync(path.join(OUT, "audit_broken_refs.json"), JSON.stringify({
  P0_brokenItemRefs: p0_brokenItemRefs.slice(0, 200),
  P0_brokenGachaChars: p0_brokenGachaChars.slice(0, 200),
  P0_brokenQuestGroups: p0_brokenQuestGroups.slice(0, 200),
}, null, 2));

fs.writeFileSync(path.join(OUT, "audit_risk.json"), JSON.stringify({
  P0: P0.slice(0, 500),
  P1: P1.slice(0, 500),
  P2: P2.slice(0, 500),
  summary: { P0: P0.length, P1: P1.length, P2: P2.length, totalCNOnlyItems: comparison.items.cnOnly.length, totalCNOnlyChars: comparison.characters.cnOnly.length },
}, null, 2));

console.log(`\nReports saved:`);
console.log(`  ${path.join(OUT, "audit_cn_only.json")}`);
console.log(`  ${path.join(OUT, "audit_broken_refs.json")}`);
console.log(`  ${path.join(OUT, "audit_risk.json")}`);

// Quick summary
console.log(`\n====== SUMMARY ======`);
console.log(`P0 (C8601 crashes): ${P0.length}`);
if (P0.length <= 30) P0.forEach((r) => console.log(`  ${r.category || r.type} #${r.id} → ${JSON.stringify(r.sources?.slice(0, 3))}`));
console.log(`P1 (display uncertain): ${P1.length}`);
if (P1.length <= 20) P1.forEach((r) => console.log(`  item #${r.id} (date: ${r.date?.start}~${r.date?.end})`));
console.log(`P2 (redundant): ${P2.length} items/chars/gachas`);
