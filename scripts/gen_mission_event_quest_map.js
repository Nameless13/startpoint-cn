/**
 * Generate mission_event_quest_map.json from cat3 mission data + CDN quest data.
 * Maps each mission pattern to its quest IDs and quest categories.
 * Run: node scripts/gen_mission_event_quest_map.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const CDN = path.resolve(ROOT, "..", "wf-assets-cn", "orderedmap", "quest");
const IN = path.join(ROOT, "assets", "mission_event.json");
const OUT = path.join(ROOT, "assets", "mission_event_quest_map.json");

// ─── CDN quest file readers ───

function readJSON(filePath) {
    try { return JSON.parse(fs.readFileSync(filePath, "utf8")); } catch { return null; }
}

/** Extract all quest_ids from a nested stage_group → difficulty → rows structure */
function collectQuestsFromKeyed(data, key) {
    if (!data || !data[key]) return [];
    const ids = [];
    for (const [, rows] of Object.entries(data[key])) {
        if (rows[0] && rows[0][0]) ids.push(Number(rows[0][0]));
    }
    return ids;
}

/** Extract quest_ids from boss_battle's double-nested structure: {col: {stage_group: {diff: [row]}}} */
function collectBossBattleQuests(data, stageGroup) {
    if (!data) return [];
    for (const [, inner] of Object.entries(data)) {
        if (inner && inner[stageGroup]) {
            return collectQuestsFromKeyed(inner, stageGroup);
        }
    }
    return [];
}

/** Collect ALL quest_ids from boss_battle's double-nested structure */
function collectAllBossBattleQuests(data) {
    if (!data) return [];
    const ids = [];
    for (const [, inner] of Object.entries(data)) {
        for (const [, diffMap] of Object.entries(inner)) {
            for (const [, rows] of Object.entries(diffMap)) {
                if (rows[0] && rows[0][0]) ids.push(Number(rows[0][0]));
            }
        }
    }
    return ids;
}

/** Extract quest_ids from a flat keyed structure */
function collectQuestsFromFlat(data, key) {
    if (!data || !data[key]) return [];
    const ids = [];
    for (const [, rows] of Object.entries(data[key])) {
        if (rows[0] && rows[0][0]) ids.push(Number(rows[0][0]));
    }
    return ids;
}

/** Extract a single quest_id from a keyed structure (for ranking_event_single) */
function getSingleQuest(data, key) {
    if (!data || !data[key]) return [];
    // ranking_event_single has {folder_key: {sub: [row]}}; take the first sub-entry
    for (const [, rows] of Object.entries(data[key])) {
        if (rows[0] && rows[0][0]) return [Number(rows[0][0])];
    }
    return [];
}

/** Collect ALL quest_ids from a folder (for challenge_dungeon) */
function collectAllFromFolder(data, folder) {
    if (!data || !data[folder]) return [];
    const ids = [];
    for (const [, rows] of Object.entries(data[folder])) {
        if (rows[0] && rows[0][0]) ids.push(Number(rows[0][0]));
    }
    return ids;
}

// ─── CDN file paths ───

const BOSS_BATTLE = readJSON(path.join(CDN, "boss_battle_quest.json"));
const ADVENT_EVENT = readJSON(path.join(CDN, "event", "advent_event_quest.json"));
const CHALLENGE_DUNGEON = readJSON(path.join(CDN, "event", "challenge_dungeon_event_quest.json"));
const RANKING_EVENT = readJSON(path.join(CDN, "event", "ranking_event_single_quest.json"));
const WORLD_STORY_BOSS = readJSON(path.join(CDN, "event", "world_story_event_boss_battle_quest.json"));
const CARNIVAL = readJSON(path.join(CDN, "event", "carnival_event_quest.json"));
const RAID = readJSON(path.join(CDN, "event", "raid_event_quest.json"));
const RUSH = readJSON(path.join(CDN, "event", "rush_event_quest.json"));

// ─── Main generation ───

const missions = readJSON(IN);
if (!missions) { console.error("Failed to read " + IN); process.exit(1); }

const result = {};
let mapped = 0;
let skipped = 0;

for (const [mid, rows] of Object.entries(missions)) {
    const r = rows[0];
    const pattern = String(r[0] || "");
    if (!pattern || pattern === "(None)") continue;

    const c7 = r[7] || "";
    const c8 = r[8] || "";
    const c9 = r[9] || "";

    let questIds = [];
    let categories = [];
    let countMode = "single";  // 'single' for finished-based, 'multi' for multi_clear_count

    switch (c7) {
        case "2": // BOSS_BATTLE — col[9]=stage_group
            if (c9 && c9 !== "(None)" && c9 !== "") {
                questIds = collectBossBattleQuests(BOSS_BATTLE, c9);
            } else {
                // col[9] empty = ALL boss battles count
                questIds = collectAllBossBattleQuests(BOSS_BATTLE);
            }
            categories = [2];
            break;

        case "5": // ADVENT_EVENT — col[8]=stage_group
            if (c8 && c8 !== "(None)" && c8 !== "") {
                questIds = collectQuestsFromFlat(ADVENT_EVENT, c8);
            }
            categories = [7, 8];
            break;

        case "7": // CHALLENGE_DUNGEON — folder=1, all quests
            questIds = collectQuestsFromKeyed(CHALLENGE_DUNGEON, "1");
            categories = [13];
            break;

        case "8": // RANKING_EVENT (时间试炼) — col[8]=key
            if (c8 && c8 !== "(None)" && c8 !== "") {
                questIds = getSingleQuest(RANKING_EVENT, c8);
            }
            categories = [11];
            break;

        case "10": // WORLD_STORY_BOSS — col[8]=event_id
            if (c8 && c8 !== "(None)" && c8 !== "") {
                questIds = collectQuestsFromKeyed(WORLD_STORY_BOSS, c8);
            }
            categories = [19];
            break;

        case "15": // CARNIVAL — col[8]=folder_id
            if (c8 && c8 !== "(None)" && c8 !== "") {
                questIds = collectQuestsFromKeyed(CARNIVAL, c8);
            }
            categories = [22];
            break;

        case "16": // RAID — col[8]=stage_group
            if (c8 && c8 !== "(None)" && c8 !== "") {
                questIds = collectQuestsFromKeyed(RAID, c8);
            }
            categories = [23];
            break;

        case "17": // RUSH — col[8]=event_id
            if (c8 && c8 !== "(None)" && c8 !== "") {
                questIds = collectQuestsFromKeyed(RUSH, c8);
            }
            categories = [24];
            break;
    }

    // Determine count mode from pattern type (col[2])
    const patternType = r[2] || "";
    if (["16", "17", "20"].includes(patternType)) {
        countMode = "multi";  // multi_battle_clear / multi_host_count / attention
    } else if (patternType === "15") {
        countMode = "finish";  // single_battle_clear_time — use finished flag
    }

    if (questIds.length > 0) {
        result[pattern] = { questIds, categories, countMode };
        mapped++;
    } else {
        skipped++;
    }
}

fs.writeFileSync(OUT, JSON.stringify(result, null, 2));
console.log(`Generated ${OUT}`);
console.log(`  mapped: ${mapped} / skipped: ${skipped} / total: ${mapped + skipped}`);
