/**
 * Add available_from field to permanent characters in character_table.json.
 * Logic:
 *   1. 91 JP launch characters (verified from CDN gacha_odds) → "2019-12-01"
 *   2. Other permanent characters → first UP banner's endDate + 1 day
 *   3. No UP record → "2019-12-01" (launch window character)
 *   4. Abnormal dates (before 2019) → fall back to startDate
 */
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..");

const CHAR_TABLE_PATH = path.join(ROOT, "data", "character_table.json");
const CDN_GACHA_PATH = path.join(ROOT, "assets", "cdndata", "gacha.json");
const CDN_FC_PATH = path.join(ROOT, "assets", "cdndata", "gacha_feature_content.json");

const JP_LAUNCH = "2019-12-01";

// 91 JP launch permanent characters (verified from commit 44931d4 banner 1)
const JP_LAUNCH_IDS = new Set([
    // ★5 (15)
    111001, 111002, 111003, 121001, 121002, 131001, 131002,
    141001, 141002, 141004, 151001, 151002, 151003, 161001, 161002,
    // ★4 (27)
    211001, 211002, 211003, 211004, 211005, 221001, 221002, 221003,
    221004, 221006, 231001, 231002, 231003, 231004, 231006, 241001,
    241002, 241003, 241004, 241005, 251002, 251003, 251004, 251005,
    261003, 261004, 261005,
    // ★3 (49)
    311001, 311002, 311004, 311005, 311006, 311008, 311009, 311010,
    321001, 321002, 321003, 321004, 321005, 321006, 321007, 321008,
    321009, 321010, 331001, 331002, 331003, 331004, 331005, 331006,
    331007, 331010, 331011, 341001, 341002, 341004, 341005, 341006,
    341007, 341008, 341009, 351001, 351002, 351003, 351004, 351005,
    351006, 351007, 361001, 361002, 361003, 361004, 361005, 361006,
    361007,
]);

interface CharEntry {
    name: string;
    code_number: string;
    code_name: string;
    rarity: number;
    source: string;
    available_from?: string;
}

function addDays(dateStr: string, days: number): string {
    const clean = dateStr.replace(" ", "T").substring(0, 10);
    const d = new Date(clean + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().substring(0, 10);
}

function isValidDate(dateStr: string): boolean {
    return dateStr >= "2019-01-01" && dateStr <= "2099-01-01";
}

function main() {
    // Load data
    const charTable: CharEntry[] = JSON.parse(fs.readFileSync(CHAR_TABLE_PATH, "utf-8"));
    const cdnGacha: Record<string, any> = JSON.parse(fs.readFileSync(CDN_GACHA_PATH, "utf-8"));
    const cdnFC: Record<string, any> = JSON.parse(fs.readFileSync(CDN_FC_PATH, "utf-8"));

    // Build {gachaId → {startDate, endDate}}
    const bannerDates: Record<string, { start: string; end: string | null }> = {};
    for (const [gid, rows] of Object.entries(cdnGacha)) {
        if (!Array.isArray(rows) || rows.length === 0) continue;
        const row = Array.isArray(rows[0]) ? rows[0] : rows;
        if (!Array.isArray(row)) continue;
        const start = String(row[29] || "");
        const endRaw = String(row[30] || "");
        const end = endRaw && endRaw !== "(None)" && endRaw !== "" && endRaw !== "2199-12-31 23:59:59" ? endRaw : null;
        if (start) {
            bannerDates[gid] = { start, end };
        }
    }

    // Find each character's first UP banner from feature_content
    const allCodes = new Set(charTable.map(c => String(c.code_number)));
    const charFirstUpBanner: Record<string, string> = {};

    for (const [gid, sections] of Object.entries(cdnFC)) {
        if (typeof sections !== "object" || !sections) continue;
        for (const rows of Object.values(sections as Record<string, any>)) {
            if (!Array.isArray(rows)) continue;
            for (const row of rows as any[]) {
                if (!Array.isArray(row)) continue;
                for (const cell of row) {
                    const s = String(cell);
                    if (s.length === 6 && /^\d+$/.test(s) && s[0] !== "0" && allCodes.has(s)) {
                        const existing = charFirstUpBanner[s];
                        if (!existing) {
                            charFirstUpBanner[s] = gid;
                        } else {
                            const existingDate = bannerDates[existing]?.start || "";
                            const thisDate = bannerDates[gid]?.start || "";
                            if (thisDate && (!existingDate || thisDate < existingDate)) {
                                charFirstUpBanner[s] = gid;
                            }
                        }
                    }
                }
            }
        }
    }

    // Assign available_from to each permanent character
    // Build code_number groups for guessing dates of no-UP characters
    const codeGroups: Record<string, CharEntry[]> = {};
    for (const char of charTable) {
        if (char.source !== "常驻卡池") continue;
        const code = String(char.code_number);
        const groupKey = code.substring(0, 2);
        if (!codeGroups[groupKey]) codeGroups[groupKey] = [];
        codeGroups[groupKey].push(char);
    }
    for (const key of Object.keys(codeGroups)) {
        codeGroups[key].sort((a, b) => parseInt(a.code_number) - parseInt(b.code_number));
    }

    // Helper: find the best date for a no-UP character
    function getGroupBestDate(char: CharEntry): string {
        const code = String(char.code_number);
        const groupKey = code.substring(0, 2);
        const group = codeGroups[groupKey];
        if (!group) return JP_LAUNCH;
        const targetSeq = parseInt(code.substring(2));
        
        // Find the FIRST character after this one that has a real date (from UP record)
        for (const g of group) {
            const gSeq = parseInt(String(g.code_number).substring(2));
            if (gSeq <= targetSeq) continue;
            if (g.available_from && g.available_from !== JP_LAUNCH) {
                return g.available_from;
            }
        }
        
        // Fallback: use latest predecessor's date
        let bestDate = JP_LAUNCH;
        for (const g of group) {
            const gSeq = parseInt(String(g.code_number).substring(2));
            if (gSeq >= targetSeq) break;
            if (g.available_from && g.available_from > bestDate) {
                bestDate = g.available_from;
            }
        }
        return bestDate;
    }

    let assigned = 0;
    let fromLaunchSet = 0;
    let fromUP = 0;
    let badDates = 0;

    // First pass: assign dates for launch set and UP-record characters
    for (const char of charTable) {
        if (char.source !== "常驻卡池") continue;
        const code = parseInt(String(char.code_number));

        if (JP_LAUNCH_IDS.has(code)) {
            char.available_from = JP_LAUNCH;
            fromLaunchSet++;
        } else {
            const upBanner = charFirstUpBanner[String(char.code_number)];
            if (upBanner && bannerDates[upBanner]) {
                const { start, end } = bannerDates[upBanner];
                let date: string;
                if (end && isValidDate(end.substring(0, 10))) {
                    date = addDays(end, 1);
                } else if (isValidDate(start.substring(0, 10))) {
                    date = start.substring(0, 10);
                    badDates++;
                } else {
                    date = JP_LAUNCH;
                    badDates++;
                }
                char.available_from = date;
                fromUP++;
            } else {
                // Clear stale date from previous run — will be filled in second pass
                delete (char as any).available_from;
            }
        }
        assigned++;
    }

    // Second pass: assign dates for no-UP characters using group predecessor
    let noUpCount = 0;
    let fromGroupPred = 0;
    for (const char of charTable) {
        if (char.source !== "常驻卡池") continue;
        const code = parseInt(String(char.code_number));
        if (JP_LAUNCH_IDS.has(code)) continue;
        if (char.available_from) continue;

        noUpCount++;
        const predDate = getGroupBestDate(char);
        char.available_from = predDate;
        fromGroupPred++;
        if (noUpCount <= 5) console.log(`  [groupPred] ${char.code_number} ${char.name} → ${predDate}`);
    }
    console.log(`  No-UP chars with group pred: ${fromGroupPred}/${noUpCount}`);

    // Stats
    console.log(`Permanent characters: ${assigned}`);
    console.log(`  From JP launch set (91): ${fromLaunchSet}`);
    console.log(`  From UP banner (endDate+1): ${fromUP}`);
    console.log(`  From group predecessor: ${fromGroupPred}`);
    console.log(`  Bad dates (fallback): ${badDates}`);
    console.log(`  Total UP banners referenced: ${Object.keys(charFirstUpBanner).length}`);

    // Show sample
    console.log("\nSample dates:");
    const sample = charTable.filter(c => c.source === "常驻卡池" && c.available_from).slice(0, 10);
    for (const c of sample) {
        const code = String(c.code_number);
        const isLaunch = JP_LAUNCH_IDS.has(parseInt(code));
        const up = charFirstUpBanner[code];
        const dateInfo = isLaunch ? 'JP launch' : (up ? `banner=${up}` : 'no UP record');
        console.log(`  ${code} ${c.name}: ${c.available_from} (${dateInfo})`);
    }

    // Write back
    fs.writeFileSync(CHAR_TABLE_PATH, JSON.stringify(charTable, null, 2) + "\n");
    console.log(`\nWritten: ${CHAR_TABLE_PATH}`);
}

main();
