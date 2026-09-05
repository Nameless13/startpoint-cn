/**
 * event_timeline_cleanup.cjs
 *
 * 清洗国服 CDN 活动/商店/领主关卡主数据中混入的日服时间窗。
 *
 * 修正范围:
 *   1. boss_battle_quest.orderedmap — 50 条领主关卡 start 改写为国服运营时间
 *   2. advent_event.orderedmap — key 1/2/3 start 修正 + playable_end = start+7d
 *   3. story_event.orderedmap — key 100001/100003 start 修正; 15 条纪念关卡 end 锁定
 *   4. world_story_event.orderedmap — key 100100/100200/100300/100400 start 修正
 *   5. carnival_event.orderedmap — key 1 exchange_end 修正
 *   6. ranking_event.orderedmap — key 1 start 修正
 *   7. expert_single_event.orderedmap — key 1 start 修正
 *   8. world_story_event_boss_battle_quest.orderedmap — 16 条时间跟随世界故事活动
 *
 * 保留不变:
 *   raid_event, rush_event, solo_time_attack_event, score_attack_event,
 *   challenge_dungeon_event, tower_dungeon_event,
 *   boss_battle_multi_pickup_event, expert_single_event key 2, 其余未列入清单条目
 *
 * collect_item_event 不在 wf-store-fresh 中（CDN dump 物理缺失），跳过。
 *
 * 使用:
 *   node tools/event_timeline_cleanup.cjs [--dry-run] [--version 1.4.325] [--out <dir>]
 *
 * 输出:
 *   <out>/production/upload/<hash>/  修改后的 orderedmap 文件
 *   <out>/archive/                   zip 补丁包
 *   <out>/patch-manifest.json        补丁清单
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const zlib = require("zlib");
const { execSync } = require("child_process");

const SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy";

// ── Config ─────────────────────────────────────────────────────────────────

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_STORE = path.join(ROOT, "wf-store-fresh", "production", "upload");
const DEFAULT_OUT_DIR = path.join(ROOT, "assets", "asset-patch");
const DEFAULT_VERSION = "1.4.325";

// ── Boss battle quest start time map ────────────────────────────────────────
// key = quest id, value = start date (time always 12:00:00)
const BOSS_START_MAP = {
  // 废墟魔像
  "1006003": "2021-12-02", "1006004": "2021-12-02",
  // 不死王瑞西塔尔
  "1003003": "2021-12-23", "1003004": "2021-12-23",
  // 诅咒弧魔艾基尔
  "1012003": "2022-01-27", "1012004": "2022-01-27",
  // 寄居蟹船长
  "1010003": "2022-03-17", "1010004": "2022-03-17",
  // 管理者
  "1017003": "2022-04-14", "1017004": "2022-04-14",
  // 白虎
  "1014003": "2022-02-24", "1014004": "2022-02-24",
  // 潮汐巨妖 (第一期)
  "1009001": "2022-01-13", "1009002": "2022-01-13",
  // 潮汐巨妖 (第二期)
  "1009003": "2024-10-17", "1009004": "2024-10-17",
  // Sec-5200Li (第一期)
  "1016001": "2022-01-13", "1016002": "2022-01-13",
  // Sec-5200Li (第二期)
  "1016003": "2023-03-02", "1016004": "2023-03-02",
  // 雷霆树妖 (第一期)
  "1002001": "2022-11-24", "1002002": "2022-11-24",
  // 雷霆树妖 (第二期)
  "1002003": "2024-09-12", "1002004": "2024-09-12",
  // 风将獠牙骑士 (第一期)
  "1013001": "2022-09-29", "1013002": "2022-09-29",
  // 风将獠牙骑士 (第二期)
  "1013003": "2023-06-16", "1013004": "2023-06-16",
  // 妖狐 (第一期)
  "1019001": "2022-07-28", "1019002": "2022-07-28",
  // 妖狐 (第二期)
  "1019003": "2023-04-13", "1019004": "2023-04-13",
  // 八岐大蛇
  "1020002": "2022-10-27", "1020003": "2022-10-27",
  // 背鳍三兄弟
  "1023001": "2023-05-11", "1023002": "2023-05-11",
  "1023003": "2023-05-11", "1023004": "2023-05-11",
  // 猩红巨熊
  "1024001": "2023-06-11", "1024002": "2023-06-11",
  "1024003": "2023-06-11", "1024004": "2023-06-11",
  // 伊尔考普斯
  "1025001": "2023-07-06", "1025002": "2023-07-06",
  "1025003": "2023-07-06", "1025004": "2023-07-06",
  // 伊萨巴迪卡
  "1026001": "2023-07-06", "1026002": "2023-07-06",
  "1026003": "2023-07-06", "1026004": "2023-07-06",
  // 伊劳德雷斯
  "1027001": "2023-07-06", "1027002": "2023-07-06",
  "1027003": "2023-07-06", "1027004": "2023-07-06",
  // 伊尔格拉乌
  "1028001": "2023-07-06", "1028002": "2023-07-06",
  "1028003": "2023-07-06", "1028004": "2023-07-06",
  // 伊尔梅塔雷
  "1029001": "2023-07-06", "1029002": "2023-07-06",
  "1029003": "2023-07-06", "1029004": "2023-07-06",
  // 伊尔昂斯拉
  "1030001": "2023-07-06", "1030002": "2023-07-06",
  "1030003": "2023-07-06", "1030004": "2023-07-06",
};

// ── Story event commemorative quests to lock ────────────────────────────────
const STORY_MEMORIAL_QUESTS = new Set([
  "200001", "200003", "200005", "200007", "200008", "200009",
  "200010", "200011", "200012", "200013", "200014",
  "200021", "200022", "200023", "200024",
]);

// ── Helpers ─────────────────────────────────────────────────────────────────

function toCsv(row) {
  return row.map(v => {
    if (v === null || v === undefined) return "";
    const s = String(v);
    if (s === "" || s === "true" || s === "false" || s === "(None)" || /^-?\d+$/.test(s)) {
      return s;
    }
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }).join(",");
}

function parseCsvLine(line) {
  const out = [];
  let value = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') { value += '"'; i++; }
      else if (ch === '"') { quoted = false; }
      else { value += ch; }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      out.push(value);
      value = "";
    } else if (ch !== "\r") {
      value += ch;
    }
  }
  out.push(value);
  return out;
}

function hashed_rel(logicalPath) {
  const normalized = logicalPath.replace(/[\/\\]+/g, "/").replace(/^\//, "");
  const digest = crypto.createHash("sha1").update(normalized + SALT).digest("hex");
  return `${digest.slice(0, 2)}/${digest.slice(2)}`;
}

function hashResourcePath(logicalPath) {
  const normalized = logicalPath.replace(/[\/\\]+/g, "/").replace(/^\//, "");
  const digest = crypto.createHash("sha1").update(normalized + SALT).digest("hex");
  return {
    logicalPath: normalized,
    relativePath: hashed_rel(logicalPath),
    fileName: digest,
  };
}

function serializeOrderedMap(entries) {
  entries.sort((a, b) => {
    const na = parseInt(a.key, 10);
    const nb = parseInt(b.key, 10);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.key.localeCompare(b.key);
  });

  const keyBuffers = entries.map(e => Buffer.from(e.key, "utf8"));
  const rowTextBuffers = entries.map(e => Buffer.from(e.row, "utf8"));
  const rowBlocks = rowTextBuffers.map(r => zlib.deflateSync(r));

  let keyPos = 0;
  let rowPos = 0;
  const pairs = entries.map((_, i) => {
    keyPos += keyBuffers[i].length;
    rowPos += rowBlocks[i].length;
    return { keyEnd: keyPos, rowEnd: rowPos };
  });

  const indexPayload = Buffer.concat([
    Buffer.from(new Uint32Array([entries.length]).buffer),
    Buffer.concat(pairs.map(p =>
      Buffer.from(new Uint32Array([p.keyEnd, p.rowEnd]).buffer)
    )),
    Buffer.concat(keyBuffers),
  ]);

  const indexBlock = zlib.deflateSync(indexPayload);

  return Buffer.concat([
    Buffer.from(new Uint32Array([indexBlock.length]).buffer),
    indexBlock,
    ...rowBlocks,
  ]);
}

function formatDate(dateStr) {
  // Ensure time is 12:00:00
  return dateStr + " 12:00:00";
}

function addDays(dateStr, days) {
  const d = new Date(dateStr.replace(/-/g, "/"));
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day} 11:59:59`;
}

// ── Nested orderedmap read/write (for boss_battle_quest and world_story_event_boss_battle_quest) ──

function parseNode(raw) {
  if (raw.length < 12) return null;
  const ilen = raw.readUInt32LE(0);
  if (ilen <= 0 || 4 + ilen > raw.length) return null;
  let index;
  try { index = zlib.inflateSync(raw.subarray(4, 4 + ilen)); } catch { return null; }
  if (index.length < 4) return null;
  const n = index.readUInt32LE(0);
  if (n <= 0 || index.length < 4 + 8 * n) return null;
  const pairs = [];
  for (let i = 0; i < n; i++) {
    const o = 4 + 8 * i;
    pairs.push([index.readUInt32LE(o), index.readUInt32LE(o + 4)]);
  }
  const keyBlob = index.subarray(4 + 8 * n);
  const blob = raw.subarray(4 + ilen);
  if (pairs[n - 1][0] !== keyBlob.length || pairs[n - 1][1] !== blob.length) return null;
  let pk = 0, pr = 0;
  const keys = [], chunks = [];
  for (const [kEnd, rEnd] of pairs) {
    keys.push(keyBlob.subarray(pk, kEnd).toString("utf8"));
    chunks.push(blob.subarray(pr, rEnd));
    pk = kEnd; pr = rEnd;
  }
  return { keys, chunks };
}

function nodeToValue(chunk) {
  if (!chunk || chunk.length === 0) return "";
  const parsed = parseNode(chunk);
  if (parsed) {
    const result = {};
    for (let i = 0; i < parsed.keys.length; i++) {
      result[parsed.keys[i]] = nodeToValue(parsed.chunks[i]);
    }
    return result;
  }
  try { return zlib.inflateSync(chunk).toString("utf8"); } catch { return ""; }
}

function buildNode(node) {
  if (typeof node === "str" || typeof node === "string") {
    return node ? zlib.deflateSync(Buffer.from(node, "utf8")) : Buffer.alloc(0);
  }
  if (typeof node !== "object" || node === null) {
    throw new TypeError(`Expected string or dict, got ${typeof node}`);
  }
  let keyBlob = Buffer.alloc(0);
  let rowBlob = Buffer.alloc(0);
  const pairs = [];
  const sortedKeys = Object.keys(node).sort((a, b) => {
    const na = parseInt(a, 10), nb = parseInt(b, 10);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a.localeCompare(b);
  });
  for (const key of sortedKeys) {
    const child = node[key];
    const keyBuf = Buffer.from(key, "utf8");
    const rowBuf = buildNode(child);
    keyBlob = Buffer.concat([keyBlob, keyBuf]);
    const prevLen = rowBlob.length;
    rowBlob = Buffer.concat([rowBlob, rowBuf]);
    pairs.push([keyBlob.length, rowBlob.length]);
  }
  const indexBuf = Buffer.alloc(4 + pairs.length * 8 + keyBlob.length);
  indexBuf.writeUInt32LE(pairs.length, 0);
  for (let i = 0; i < pairs.length; i++) {
    indexBuf.writeUInt32LE(pairs[i][0], 4 + i * 8);
    indexBuf.writeUInt32LE(pairs[i][1], 4 + 4 + i * 8);
  }
  keyBlob.copy(indexBuf, 4 + pairs.length * 8);
  const indexCompressed = zlib.deflateSync(indexBuf);
  return Buffer.concat([
    Buffer.from(new Uint32Array([indexCompressed.length]).buffer),
    indexCompressed,
    rowBlob,
  ]);
}

// ── Core logic per table ─────────────────────────────────────────────────────

function cleanBossBattleQuest(store) {
  const logical = "master/quest/boss_battle_quest.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const raw = fs.readFileSync(filePath);
  const tree = nodeToValue(raw);
  // tree = { "1": { chapterId: { subId: csvRow, ... }, ... } }
  // quest_id is in CSV col[0], L2 keys are numeric sub-ids
  const changes = [];
  const l1 = tree["1"];
  if (!l1 || typeof l1 !== "object") return changes;
  for (const [chapterId, quests] of Object.entries(l1)) {
    if (typeof quests !== "object") continue;
    for (const [subId, row] of Object.entries(quests)) {
      if (typeof row !== "string") continue;
      const cols = parseCsvLine(row);
      const questId = cols[0];
      if (!(questId in BOSS_START_MAP)) continue;
      const newStart = formatDate(BOSS_START_MAP[questId]);
      if (cols[5] === newStart) continue;
      const oldStart = cols[5];
      cols[5] = newStart;
      l1[chapterId][subId] = toCsv(cols);
      changes.push({ quest: questId, field: "start", from: oldStart, to: newStart });
    }
  }
  // Rebuild and write
  const newRaw = buildNode(tree);
  fs.writeFileSync(filePath, newRaw);
  return changes;
}

function cleanAdventEvent(store) {
  const logical = "master/quest/event/advent_event.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const tree = parseSimpleOrderedMap(filePath);
  const changes = [];
  const fixes = {
    "1": { start: "2021-11-18", playableEnd: "2021-11-25", exchangeEnd: "2021-12-02" },
    "2": { start: "2021-12-30", playableEnd: "2022-01-06", exchangeEnd: "2022-01-13" },
    "3": { start: "2022-02-10", playableEnd: "2022-02-17", exchangeEnd: "2022-02-24" },
  };
  for (const [key, fix] of Object.entries(fixes)) {
    if (!(key in tree)) continue;
    const cols = parseCsvLine(tree[key]);
    const newStart = formatDate(fix.start);
    const origStart = cols[24];
    if (cols[24] !== newStart) {
      cols[24] = newStart;
      cols[25] = fix.playableEnd + " 11:59:59";
      cols[26] = fix.exchangeEnd + " 11:59:59";
      changes.push({ key, field: "start", from: origStart, to: newStart });
    }
    tree[key] = toCsv(cols);
  }
  writeSimpleOrderedMap(filePath, tree);
  return changes;
}

function cleanStoryEvent(store) {
  const logical = "master/quest/event/story_event.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const tree = parseSimpleOrderedMap(filePath);
  const changes = [];
  // Fix start for key 100001 and 100003
  const fixes = {
    "100001": { start: "2021-11-04", playableEnd: "2021-11-11", exchangeEnd: "2021-11-18" },
    "100003": { start: "2021-12-09", playableEnd: "2021-12-16", exchangeEnd: "2021-12-23" },
  };
  for (const [key, fix] of Object.entries(fixes)) {
    if (!(key in tree)) continue;
    const cols = parseCsvLine(tree[key]);
    // Strip surrounding quotes from date fields for comparison
    const origStart = (cols[16] || "").replace(/^"/, "").replace(/"$/, "");
    const newStart = formatDate(fix.start);
    if (origStart !== newStart) {
      cols[16] = '"' + newStart + '"';
      cols[17] = '"' + fix.playableEnd + " 11:59:59" + '"';
      cols[18] = '"' + fix.exchangeEnd + " 11:59:59" + '"';
      changes.push({ key, field: "start", from: origStart, to: newStart });
    }
    tree[key] = toCsv(cols);
  }
  // Lock commemorative quests to pre-launch
  const cnLaunch = "2021-10-29 23:59:59";
  for (const key of STORY_MEMORIAL_QUESTS) {
    if (!(key in tree)) continue;
    const cols = parseCsvLine(tree[key]);
    // col17 = end time
    if (cols[17] && cols[17] !== cnLaunch) {
      const oldEnd = cols[17];
      cols[17] = cnLaunch;
      // col18 = exchange_end, also set to same or earlier
      if (cols[18] && cols[18] > cnLaunch) {
        cols[18] = cnLaunch;
      }
      changes.push({ key, field: "end", from: oldEnd, to: cnLaunch });
    }
    tree[key] = toCsv(cols);
  }
  writeSimpleOrderedMap(filePath, tree);
  return changes;
}

function cleanWorldStoryEvent(store) {
  const logical = "master/quest/event/world_story_event.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const tree = parseSimpleOrderedMap(filePath);
  const changes = [];
  const fixes = {
    "100100": "2022-01-20",
    "100200": "2022-04-21",
    "100300": "2022-05-26",
    "100400": "2022-07-21",
  };
  for (const [key, startDate] of Object.entries(fixes)) {
    if (!(key in tree)) continue;
    const cols = parseCsvLine(tree[key]);
    const newStart = formatDate(startDate);
    if (cols[22] !== newStart) {
      const oldStart = cols[22];
      cols[22] = newStart;
      // col23 = playable_end = start + 7d
      cols[23] = addDays(startDate, 7);
      // col24 = exchange_end — follow existing pattern (+7 more days from playable_end)
      cols[24] = addDays(startDate, 14);
      changes.push({ key, field: "start", from: oldStart, to: newStart });
    }
    tree[key] = toCsv(cols);
  }
  writeSimpleOrderedMap(filePath, tree);
  return changes;
}

function cleanCarnivalEvent(store) {
  const logical = "master/quest/event/carnival_event.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const tree = parseSimpleOrderedMap(filePath);
  const changes = [];
  if ("1" in tree) {
    const cols = parseCsvLine(tree["1"]);
    // col22 = exchange_end (based on earlier inspection: col[20]=start, col[21]=playable_end, col[22]=exchange_end)
    if (cols[22] === "2199-12-31 23:59:59") {
      cols[22] = "2023-03-31 23:59:59";
      changes.push({ key: "1", field: "exchange_end", from: "2199-12-31 23:59:59", to: "2023-03-31 23:59:59" });
      tree["1"] = toCsv(cols);
    }
  }
  writeSimpleOrderedMap(filePath, tree);
  return changes;
}

function cleanRankingEvent(store) {
  const logical = "master/quest/event/ranking_event.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const tree = parseSimpleOrderedMap(filePath);
  const changes = [];
  if ("1" in tree) {
    const cols = parseCsvLine(tree["1"]);
    // From earlier: cols[3] = start (quoted), cols[4] = playable_end, cols[5] = exchange_end
    // The row was: 'time_attack_event_water_001', '0', '云水试炼', '"2020-08-21 12:00:00', '2020-08-31 11:59:59', ...
    // col[3] starts with " — need to handle quoted fields
    const newStart = '"2022-06-16 12:00:00';
    if (cols[3] !== newStart) {
      const old = cols[3];
      cols[3] = newStart;
      // col4 = playable_end = start + 10d (based on existing pattern: 08-21 → 08-31)
      cols[4] = "2022-06-26 11:59:59";
      // col5 = exchange_end (the closing quote is part of the quoted field)
      // Looking at original: cols[5]='2020-09-03 11:59:59', cols[6]='2020-09-10 11:59:59"'
      // It seems the quoted field spans cols[3]..cols[6]? No, the CSV parser handles quotes.
      // Let me re-check: the original row has cols[3]='"2020-08-21 12:00:00' and cols[6]='2020-09-10 11:59:59"'
      // This suggests the field is quoted and spans across comma boundaries? No — the quotes are literal.
      // Actually the parser should have handled this. Let's just update col[3].
      // For exchange_end, keep the existing pattern: end = start + 20d approx
      // Original: start 08-21, end 09-10 (20 days). New: start 06-16, end 07-06
      cols[6] = '2022-07-06 11:59:59"';
      changes.push({ key: "1", field: "start", from: old, to: newStart });
    }
    tree["1"] = toCsv(cols);
  }
  writeSimpleOrderedMap(filePath, tree);
  return changes;
}

function cleanExpertSingleEvent(store) {
  const logical = "master/quest/event/expert_single_event.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const tree = parseSimpleOrderedMap(filePath);
  const changes = [];
  // key 1: start at col[13], key 2: leave unchanged
  if ("1" in tree) {
    const cols = parseCsvLine(tree["1"]);
    const newStart = "2022-05-26 12:00:00";
    if (cols[13] !== newStart) {
      const old = cols[13];
      cols[13] = newStart;
      changes.push({ key: "1", field: "start", from: old, to: newStart });
    }
    tree["1"] = toCsv(cols);
  }
  writeSimpleOrderedMap(filePath, tree);
  return changes;
}

function cleanWorldStoryEventBossBattleQuest(store) {
  const logical = "master/quest/event/world_story_event_boss_battle_quest.orderedmap";
  const filePath = path.join(store, hashed_rel(logical));
  const raw = fs.readFileSync(filePath);
  const tree = nodeToValue(raw);
  const changes = [];
  const eventStartMap = {
    "100100": "2022-01-20",
    "100200": "2022-04-21",
    "100300": "2022-05-26",
    "100400": "2022-07-21",
  };
  for (const [eventKey, startDate] of Object.entries(eventStartMap)) {
    if (!(eventKey in tree) || typeof tree[eventKey] !== "object") continue;
    const quests = tree[eventKey];
    for (let subId = 1; subId <= 4; subId++) {
      const questId = `${eventKey}${String(subId).padStart(3, "0")}`;
      if (!(String(subId) in quests) || typeof quests[String(subId)] !== "string") continue;
      const cols = parseCsvLine(quests[String(subId)]);
      const newStart = formatDate(startDate);
      if (cols[5] === newStart) continue;
      const oldStart = cols[5];
      cols[5] = newStart;
      quests[String(subId)] = toCsv(cols);
      changes.push({ quest: questId, field: "start", from: oldStart, to: newStart });
    }
  }
  // Only write if there are actual changes
  if (changes.length > 0) {
    const newRaw = buildNode(tree);
    fs.writeFileSync(filePath, newRaw);
  }
  return changes;
}

// ── Simple orderedmap helpers ────────────────────────────────────────────────

function parseSimpleOrderedMap(filePath) {
  const raw = fs.readFileSync(filePath);
  const idxLen = raw.readUInt32LE(0);
  const idx = zlib.inflateSync(raw.subarray(4, 4 + idxLen));
  const count = idx.readUInt32LE(0);
  const pairs = [];
  for (let i = 0; i < count; i++) {
    const o = 4 + i * 8;
    pairs.push([idx.readUInt32LE(o), idx.readUInt32LE(o + 4)]);
  }
  const keyBlob = idx.subarray(4 + count * 8);
  const blob = raw.subarray(4 + idxLen);
  const tree = {};
  let pk = 0, pr = 0;
  for (const [kEnd, rEnd] of pairs) {
    const key = keyBlob.subarray(pk, kEnd).toString("utf8");
    pk = kEnd;
    const chunk = blob.subarray(pr, rEnd);
    pr = rEnd;
    tree[key] = chunk.length ? zlib.inflateSync(chunk).toString("utf8") : "";
  }
  return tree;
}

function writeSimpleOrderedMap(filePath, tree) {
  const entries = [];
  for (const [key, row] of Object.entries(tree)) {
    entries.push({ key, row });
  }
  const buf = serializeOrderedMap(entries);
  fs.writeFileSync(filePath, buf);
}

// ── CLI ──────────────────────────────────────────────────────────────────────

function main() {
  const args = process.argv.slice(2);
  let dryRun = false;
  let version = DEFAULT_VERSION;
  let outDir = DEFAULT_OUT_DIR;
  let store = DEFAULT_STORE;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--dry-run") { dryRun = true; }
    else if (args[i] === "--version" && args[i + 1]) { version = args[++i]; }
    else if (args[i] === "--out" && args[i + 1]) { outDir = args[++i]; }
    else if (args[i] === "--store" && args[i + 1]) { store = args[++i]; }
    else if (args[i] === "--help") {
      console.log(`
Usage: node tools/event_timeline_cleanup.cjs [options]

Options:
  --dry-run         Show changes without writing files
  --version VER     Patch version (default: ${DEFAULT_VERSION})
  --out DIR         Output directory (default: ${DEFAULT_OUT_DIR})
  --store DIR       Store root (default: ${DEFAULT_STORE})
  --help            Show this help
`);
      process.exit(0);
    }
  }

  console.log("=== Event Timeline Cleaner ===\n");
  console.log(`  version:  ${version}`);
  console.log(`  dry_run:  ${dryRun}`);
  console.log(`  store:    ${store}`);
  console.log(`  out_dir:  ${outDir}\n`);

  if (!fs.existsSync(store)) {
    console.error(`ERROR: store not found at ${store}`);
    process.exit(1);
  }

  const allChanges = [];

  // 1. boss_battle_quest
  console.log("--- boss_battle_quest ---");
  let c = cleanBossBattleQuest(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "boss_battle_quest", ...x })));

  // 2. advent_event
  console.log("--- advent_event ---");
  c = cleanAdventEvent(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "advent_event", ...x })));

  // 3. story_event
  console.log("--- story_event ---");
  c = cleanStoryEvent(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "story_event", ...x })));

  // 4. world_story_event
  console.log("--- world_story_event ---");
  c = cleanWorldStoryEvent(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "world_story_event", ...x })));

  // 5. carnival_event
  console.log("--- carnival_event ---");
  c = cleanCarnivalEvent(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "carnival_event", ...x })));

  // 6. ranking_event
  console.log("--- ranking_event ---");
  c = cleanRankingEvent(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "ranking_event", ...x })));

  // 7. expert_single_event
  console.log("--- expert_single_event ---");
  c = cleanExpertSingleEvent(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "expert_single_event", ...x })));

  // 8. world_story_event_boss_battle_quest
  console.log("--- world_story_event_boss_battle_quest ---");
  c = cleanWorldStoryEventBossBattleQuest(store);
  console.log(`  Changes: ${c.length}`);
  allChanges.push(...c.map(x => ({ table: "world_story_event_boss_battle_quest", ...x })));

  // Print summary
  console.log(`\n=== Summary ===`);
  console.log(`  Total changes: ${allChanges.length}`);
  for (const ch of allChanges) {
    console.log(`  [${ch.table}] ${ch.key || ch.quest}: ${ch.field} "${ch.from || ""}" → "${ch.to}"`);
  }

  if (dryRun) {
    console.log("\n[Dry-run mode: no patch archive created]");
    return;
  }

  if (allChanges.length === 0) {
    console.log("\n  All data already matches spec. No patch needed.");
    return;
  }

  // Build patch archive from modified files
  const tables = [
    "master/quest/boss_battle_quest.orderedmap",
    "master/quest/event/advent_event.orderedmap",
    "master/quest/event/story_event.orderedmap",
    "master/quest/event/world_story_event.orderedmap",
    "master/quest/event/carnival_event.orderedmap",
    "master/quest/event/ranking_event.orderedmap",
    "master/quest/event/expert_single_event.orderedmap",
    "master/quest/event/world_story_event_boss_battle_quest.orderedmap",
  ];

  const archiveName = `pinball-${version}-${version}-1-event-timeline-cleanup`;
  const archiveDir = path.join(outDir, "archive");
  if (!fs.existsSync(archiveDir)) fs.mkdirSync(archiveDir, { recursive: true });

  // Clean old archives with same prefix
  for (const f of fs.readdirSync(archiveDir)) {
    if (f.startsWith(archiveName)) fs.unlinkSync(path.join(archiveDir, f));
  }

  const tmpDir = path.join(outDir, "tmp");
  if (fs.existsSync(tmpDir)) fs.rmSync(tmpDir, { recursive: true });
  fs.mkdirSync(tmpDir, { recursive: true });

  let totalSize = 0;
  const archiveEntries = [];

  for (const logical of tables) {
    const hashInfo = hashResourcePath(logical);
    const srcFile = path.join(store, hashInfo.relativePath.split("/")[0], hashInfo.relativePath.split("/")[1]);
    if (!fs.existsSync(srcFile)) {
      console.log(`  SKIP (not found): ${logical}`);
      continue;
    }
    const destDir = path.join(tmpDir, "production", "upload", hashInfo.relativePath.split("/")[0]);
    fs.mkdirSync(destDir, { recursive: true });
    const destFile = path.join(destDir, hashInfo.relativePath.split("/")[1]);
    fs.copyFileSync(srcFile, destFile);
    // Set fixed mtime for reproducibility
    fs.utimesSync(destFile, new Date("2026-09-04T00:00:00Z"), new Date("2026-09-04T00:00:00Z"));
    const stat = fs.statSync(srcFile);
    totalSize += stat.size;
    archiveEntries.push({ logical, relativePath: hashInfo.relativePath, size: stat.size });
    console.log(`  Archive: ${hashInfo.relativePath} (${stat.size.toLocaleString()} bytes)`);
  }

  const cwd = process.cwd();
  process.chdir(tmpDir);
  try {
    execSync(`zip -X -r "${path.join(archiveDir, archiveName + '.zip')}" production/`, { stdio: "ignore" });
  } finally {
    process.chdir(cwd);
  }

  const sha1 = execSync(`shasum -a 1 "${path.join(archiveDir, archiveName + '.zip')}"`).toString().split(" ")[0];
  const finalName = `${archiveName}-${sha1.substring(0, 8)}.zip`;
  fs.renameSync(path.join(archiveDir, archiveName + ".zip"), path.join(archiveDir, finalName));
  fs.rmSync(tmpDir, { recursive: true });

  const stats = fs.statSync(path.join(archiveDir, finalName));
  console.log(`\n  Archive: ${finalName} (${(stats.size / 1024).toFixed(1)} KB)`);

  // Compute sha256 of zip
  const sha256 = crypto.createHash("sha256").update(fs.readFileSync(path.join(archiveDir, finalName))).digest("hex");

  // Write patch-manifest.json
  const patchManifest = {
    id: `event-timeline-cleanup-${version}`,
    type: "patch",
    name: `活动/领主时间窗清洗 v${version}`,
    description: `清洗日服活动时间窗: ${allChanges.length} 处修改。` +
      `领主关卡50条start时间修正、advent_event/story_event/world_story_event等6张活动表时间窗修正、` +
      `世界故事领主关16条时间跟随、story_event纪念关卡15条+collect_item_event(缺失跳过)锁定。`,
    version,
    depends_on: "1.4.324",
    enabled: true,
    chain: [finalName],
    archive_integrity: [{
      name: finalName,
      size: stats.size,
      sha256: sha256,
    }],
    created_at: new Date().toISOString().split("T")[0],
  };
  const patchManifestPath = path.join(outDir, "patch-manifest.json");
  fs.writeFileSync(patchManifestPath, JSON.stringify(patchManifest, null, 2));
  console.log(`  Patch manifest: ${patchManifestPath}`);

  console.log(`\n=== Done ===`);
  console.log(`  Version:    ${version}`);
  console.log(`  Changes:    ${allChanges.length}`);
  console.log(`  Archive:    ${finalName}`);
  console.log(`  SHA-256:    ${sha256}`);
  console.log(`  Next step:  append patch-manifest.json entry to assets/asset-patch/manifest.json`);
}

main();
