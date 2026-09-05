/**
 * clean_gacha_timeline.cjs
 *
 * 清洗 assets/cdndata/gacha.json 中混入的日服卡池时间窗，生成 CDN orderedmap 补丁包。
 *
 * 规则:
 *   1. 日服卡池（id ∈ [1,60]∪[87,99]∪[100,216]∪{2,4,9,101,1600,700000-700004,900003}）
 *      的 endDate 改写为 "2021-10-29 23:59:59"（早于国服开服 2021-10-30），使其在客户端
 *      TimeRange.isWithin(now) 判定为过期不可抽。
 *
 *   2. id 61 startDate 从 "2011-12-24" 改为 "2021-10-30 12:00:00"
 *      id 67 startDate 从 "2021-09-13" 改为 "2021-11-15 12:00:00"（与 66 不冲突）
 *
 *   3. 装备扭蛋（5000-5044）和复刻活动（2000-2099、10000-10999、15000-15999、25000-25999）
 *      时间窗保持原值不动。
 *
 *   4. 其余时间窗年份 ≥ 2099 的国服常驻池（80000、1541、1561、1586、1612-1613、1622、
 *      1649、1675、1699 等）保持原值不动。
 *
 * 使用:
 *   node tools/clean_gacha_timeline.cjs [--dry-run] [--version 1.4.324] [--out <dir>]
 *
 * 输出:
 *   <out>/production/upload/<hash>/     修改后的 orderedmap 文件
 *   <out>/archive/                       zip 补丁包
 *   <out>/patch-manifest.json            补丁清单（供 manifest.json 追加使用）
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const zlib = require("zlib");
const { execSync } = require("child_process");

// ── Config ─────────────────────────────────────────────────────────────────

const JP_LAUNCH = "2021-10-30";
const CN_OPEN_DATE = "2021-10-29 23:59:59";

const ROOT = path.resolve(__dirname, "..");
const DEFAULT_GACHA_PATH = path.join(ROOT, "assets", "cdndata", "gacha.json");
const DEFAULT_OUT_DIR = path.join(ROOT, "assets", "asset-patch");
const DEFAULT_VERSION = "1.4.324";
const DEFAULT_NEXT_VERSION = "1.4.325";

const SALT = "K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy";

// ── JP banner classification ────────────────────────────────────────────────

const JP_EXPLICIT_SET = new Set([
  "2", "4", "9", "101", "1600",
  "700000", "700001", "700002", "700003", "700004",
  "900003",
]);

function isJpBanner(id) {
  const n = Number(id);
  if (isNaN(n)) return false;
  if (JP_EXPLICIT_SET.has(String(n))) return true;
  if (n >= 1 && n <= 60) return true;
  if (n >= 87 && n <= 99) return true;
  if (n >= 100 && n <= 216) return true;
  return false;
}

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

function parseCsv(text) {
  const fields = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"' && text[i + 1] === '"') { current += '"'; i++; }
      else if (c === '"') { inQuotes = false; }
      else { current += c; }
    } else {
      if (c === '"') { inQuotes = true; }
      else if (c === ",") { fields.push(current); current = ""; }
      else { current += c; }
    }
  }
  fields.push(current);
  return fields;
}

function hashResourcePath(logicalPath) {
  const normalized = logicalPath.replace(/[\/\\]+/g, "/").replace(/^\//, "");
  const digest = crypto.createHash("sha1").update(normalized + SALT).digest("hex");
  return {
    logicalPath: normalized,
    relativePath: `${digest.slice(0, 2)}/${digest.slice(2)}`,
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

  // Build index payload
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

function readUInt32LE(buf, offset) {
  return buf.readUInt32LE(offset);
}

function parseOrderedMap(raw) {
  if (raw.length < 8) throw new Error("orderedmap is too small");
  const indexLength = readUInt32LE(raw, 0);
  if (indexLength <= 0 || 4 + indexLength > raw.length) {
    throw new Error(`invalid orderedmap index length: ${indexLength}`);
  }
  const index = zlib.inflateSync(raw.subarray(4, 4 + indexLength));
  const count = readUInt32LE(index, 0);
  const pairs = [];
  for (let i = 0; i < count; i++) {
    const off = 4 + i * 8;
    pairs.push({
      keyEnd: readUInt32LE(index, off),
      rowEnd: readUInt32LE(index, off + 4),
    });
  }
  const keyBlob = index.subarray(4 + count * 8);
  const keys = [];
  let prevKeyEnd = 0;
  for (const pair of pairs) {
    keys.push(keyBlob.subarray(prevKeyEnd, pair.keyEnd).toString("utf8"));
    prevKeyEnd = pair.keyEnd;
  }
  const blob = raw.subarray(4 + indexLength);
  const rows = [];
  let prevRowEnd = 0;
  for (const pair of pairs) {
    rows.push(blob.subarray(prevRowEnd, pair.rowEnd));
    prevRowEnd = pair.rowEnd;
  }
  return { keys, rows };
}

function readOrderedMap(filePath) {
  const raw = fs.readFileSync(filePath);
  const { keys, rows } = parseOrderedMap(raw);
  return keys.map((key, i) => ({
    key,
    text: rows[i].length ? zlib.inflateSync(rows[i]).toString("utf8") : "",
  }));
}

// ── Core logic ───────────────────────────────────────────────────────────────

function cleanGachaJson(gacha) {
  const changes = [];

  for (const [id, rows] of Object.entries(gacha)) {
    if (!rows || !Array.isArray(rows) || !rows[0]) continue;
    const row = rows[0];
    const origStart = row[29] || "";
    const origEnd = row[30] || "";

    let modified = false;

    // Special fix for id 61 and 67
    if (id === "61") {
      const newStart = "2021-10-30 12:00:00";
      if (row[29] !== newStart) {
        row[29] = newStart;
        modified = true;
        changes.push({ id, field: "startDate", from: origStart, to: newStart });
      }
    }
    if (id === "67") {
      const newStart = "2021-11-15 12:00:00";
      if (row[29] !== newStart) {
        row[29] = newStart;
        modified = true;
        changes.push({ id, field: "startDate", from: origStart, to: newStart });
      }
    }

    // Lock JP banners to pre-launch end date
    if (isJpBanner(id)) {
      const newEnd = CN_OPEN_DATE;
      if (origEnd !== newEnd) {
        row[30] = newEnd;
        modified = true;
        changes.push({ id, field: "endDate", from: origEnd, to: newEnd });
      }
    }

    if (modified) {
      gacha[id] = [row];
    }
  }

  return changes;
}

function buildOrderedMapEntries(gacha) {
  const entries = [];
  for (const [gid, rows] of Object.entries(gacha)) {
    const row = rows[0];
    if (!row) continue;
    entries.push({ key: gid, row: toCsv(row) });
  }
  return entries;
}

function findOrderedMapSource(outDir) {
  // Try several possible locations
  const candidates = [
    path.join(ROOT, "WorldFlipper", "dummy", "download", "production", "upload"),
    path.join(ROOT, "弹国服", "WorldFlipper", "dummy", "download", "production", "upload"),
  ];
  for (const dir of candidates) {
    if (!fs.existsSync(dir)) continue;
    // Find gacha.orderedmap by hash
    const hashInfo = hashResourcePath("master/gacha/gacha.orderedmap");
    const expectedFile = path.join(dir, hashInfo.relativePath.split("/")[0], hashInfo.relativePath.split("/")[1]);
    if (fs.existsSync(expectedFile)) return expectedFile;
    // Fallback: scan
    for (const subdir of fs.readdirSync(dir)) {
      const subpath = path.join(dir, subdir);
      if (!fs.isDirectory(subpath)) continue;
      for (const file of fs.readdirSync(subpath)) {
        const fullPath = path.join(subpath, file);
        try {
          const data = readOrderedMap(fullPath);
          if (data.length > 100) return fullPath;
        } catch {}
      }
    }
  }
  return null;
}

// ── CLI ──────────────────────────────────────────────────────────────────────

function main() {
  const args = process.argv.slice(2);
  let dryRun = false;
  let version = DEFAULT_VERSION;
  let outDir = DEFAULT_OUT_DIR;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--dry-run") { dryRun = true; }
    else if (args[i] === "--version" && args[i + 1]) { version = args[++i]; }
    else if (args[i] === "--out" && args[i + 1]) { outDir = args[++i]; }
    else if (args[i] === "--help") {
      console.log(`
Usage: node tools/clean_gacha_timeline.cjs [options]

Options:
  --dry-run         Show changes without writing files
  --version VER     Patch version (default: ${DEFAULT_VERSION})
  --out DIR         Output directory (default: ${DEFAULT_OUT_DIR})
  --help            Show this help
`);
      process.exit(0);
    }
  }

  console.log("=== Gacha Timeline Cleaner ===\n");
  console.log(`  version:    ${version}`);
  console.log(`  dry_run:    ${dryRun}`);
  console.log(`  out_dir:    ${outDir}\n`);

  // Load gacha.json
  const gachaPath = DEFAULT_GACHA_PATH;
  if (!fs.existsSync(gachaPath)) {
    console.error(`ERROR: gacha.json not found at ${gachaPath}`);
    process.exit(1);
  }
  const gacha = JSON.parse(fs.readFileSync(gachaPath, "utf8"));
  console.log(`  Loaded ${Object.keys(gacha).length} banners from ${gachaPath}`);

  // Clean
  const changes = cleanGachaJson(gacha);
  console.log(`  Changes detected: ${changes.length}`);
  for (const c of changes) {
    console.log(`    ${c.id}: ${c.field} "${c.from}" → "${c.to}"`);
  }

  // Also show unmodified JP banners (end_date already set)
  const alreadyClean = Object.entries(gacha).filter(([id, rows]) => {
    if (!rows || !rows[0]) return false;
    const row = rows[0];
    return isJpBanner(id) && row[30] === CN_OPEN_DATE;
  }).length;
  console.log(`  Already clean JP banners: ${alreadyClean}`);

  // Build orderedmap
  const entries = buildOrderedMapEntries(gacha);
  const buf = serializeOrderedMap(entries);
  const hashInfo = hashResourcePath("master/gacha/gacha.orderedmap");

  console.log(`\n  Orderedmap: ${hashInfo.relativePath} (${buf.length.toLocaleString()} bytes, ${entries.length} entries)`);

  if (dryRun) {
    console.log("\n[Dry-run mode: no files written]");
    return;
  }

  // Write orderedmap file
  const outDirUpload = path.join(outDir, "production", "upload", hashInfo.relativePath.split("/")[0]);
  const outFile = path.join(outDirUpload, hashInfo.relativePath.split("/")[1]);
  if (!fs.existsSync(outDirUpload)) fs.mkdirSync(outDirUpload, { recursive: true });
  fs.writeFileSync(outFile, buf);
  console.log(`  Written: ${outFile}`);

  // Compute sha256
  const sha256 = crypto.createHash("sha256").update(buf).digest("hex");
  console.log(`  SHA-256: ${sha256}`);

  // Create patch archive
  const archiveName = `pinball-${version}-${version}-1-clean-gacha-timeline`;
  const archiveDir = path.join(outDir, "archive");
  if (!fs.existsSync(archiveDir)) fs.mkdirSync(archiveDir, { recursive: true });

  // Clean old archives with same prefix
  for (const f of fs.readdirSync(archiveDir)) {
    if (f.startsWith(archiveName)) fs.unlinkSync(path.join(archiveDir, f));
  }

  const tmpDir = path.join(outDir, "tmp");
  if (fs.existsSync(tmpDir)) fs.rmSync(tmpDir, { recursive: true });
  fs.mkdirSync(tmpDir, { recursive: true });

  const srcDir = path.join(outDir, "production", "upload", hashInfo.relativePath.split("/")[0]);
  const dstDir = path.join(tmpDir, "production", "upload", hashInfo.relativePath.split("/")[0]);
  fs.mkdirSync(dstDir, { recursive: true });
  fs.copyFileSync(outFile, path.join(dstDir, hashInfo.relativePath.split("/")[1]));
  console.log(`  Archive entry: production/upload/${hashInfo.relativePath}`);

  const cwd = process.cwd();
  process.chdir(tmpDir);
  try {
    // Use -X to preserve extra file attributes and -0 for no compression of directory entries
    // Use -j to junk paths (store just filenames) for reproducibility
    execSync(`zip -X -r "${path.join(archiveDir, archiveName + '.zip')}" production/`, { stdio: "ignore" });
  } finally {
    process.chdir(cwd);
  }

  // Add SHA1 hash to filename (matching rebuild_asset_patch.cjs style)
  const sha1 = execSync(`shasum -a 1 "${path.join(archiveDir, archiveName + '.zip')}"`).toString().split(" ")[0];
  const finalName = `${archiveName}-${sha1.substring(0, 8)}.zip`;
  fs.renameSync(path.join(archiveDir, archiveName + ".zip"), path.join(archiveDir, finalName));

  fs.rmSync(tmpDir, { recursive: true });
  const stats = fs.statSync(path.join(archiveDir, finalName));
  console.log(`\n  Archive: ${finalName} (${(stats.size / 1024).toFixed(1)} KB)`);

  // Write patch-manifest.json
  const patchManifest = {
    id: `clean-gacha-timeline-${version}`,
    type: "patch",
    name: `Gacha 时间窗清洗 v${version}`,
    description: `清洗日服卡池时间窗: ${changes.length} 个卡池 endDate/startDate 修改。` +
      `规则: 日服卡池(endDate→${CN_OPEN_DATE})、id 61/67 时间窗修复、装备/复刻池保持原值。`,
    version,
    depends_on: "1.4.323",
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

  // Summary
  console.log(`\n=== Summary ===`);
  console.log(`  Version:           ${version}`);
  console.log(`  Changed banners:   ${changes.length}`);
  console.log(`  Already clean JP:  ${alreadyClean}`);
  console.log(`  Archive:           ${finalName}`);
  console.log(`  Next step: append patch-manifest.json entry to assets/asset-patch/manifest.json`);
}

main();
