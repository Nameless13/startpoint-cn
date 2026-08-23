/**
 * Extract CDN master data → assets/ for server use.
 *
 * Source: wf-assets-cn/orderedmap/item/equipment.json
 *         wf-assets-cn/orderedmap/item/item.json
 *
 * Field indices verified against:
 *   wf-2.1.125-cn-decompiled/.../EquipmentValues.as
 *   wf-2.1.125-cn-decompiled/.../ItemValues.as
 *
 * Run: npx ts-node scripts/gen_cdn_data.ts
 */

import * as fs from "fs";
import * as path from "path";

const ASSETS_CN = path.resolve(__dirname, "../../wf-assets-cn/orderedmap/item");
const ASSETS_OUT = path.resolve(__dirname, "../assets");

// ─── Equipment dissolve data ────────────────────────────────────────────

interface EquipmentDissolveEntry {
  ability_soul_id: number;
  obtain_source: number;
  generate_ability_soul: boolean;
}

function extractEquipmentDissolve() {
  const raw = JSON.parse(
    fs.readFileSync(path.join(ASSETS_CN, "equipment.json"), "utf8")
  ) as Record<string, any[][]>;

  const out: Record<string, EquipmentDissolveEntry> = {};

  for (const [id, rows] of Object.entries(raw)) {
    if (!rows || rows.length === 0) continue;
    const r = rows[0];

    // Verified EquipmentValues field indices:
    // [9] = generate_ability_soul, [10] = ability_soul_id, [15] = obtain_source
    const generateStr = String(r[9] ?? "false");
    const generateAbilitySoul =
      generateStr === "true" || generateStr === "True" || generateStr === "TRUE";

    out[id] = {
      ability_soul_id: parseInt(String(r[10] ?? id), 10),
      obtain_source: parseInt(String(r[15] ?? "0"), 10),
      generate_ability_soul: generateAbilitySoul,
      max_level: parseInt(String(r[8] ?? "5"), 10),
    };
  }

  fs.writeFileSync(
    path.join(ASSETS_OUT, "equipment_dissolve.json"),
    JSON.stringify(out, null, 2)
  );
  console.log(
    `[gen_cdn_data] equipment_dissolve.json: ${Object.keys(out).length} entries`
  );

  // Stats for verification
  const noGenSoul = Object.entries(out).filter(
    ([, v]) => !v.generate_ability_soul
  ).length;
  const noStarGrain = Object.entries(out).filter(
    ([, v]) => v.obtain_source !== 0
  ).length;
  console.log(`  generate_ability_soul=false: ${noGenSoul}`);
  console.log(`  obtain_source != 0: ${noStarGrain}`);
}

// ─── Item sale data ─────────────────────────────────────────────────────

interface ItemSaleEntry {
  sale_price: number;
  sellable: boolean;
  category: number;
}

function extractItemSale() {
  const raw = JSON.parse(
    fs.readFileSync(path.join(ASSETS_CN, "item.json"), "utf8")
  ) as Record<string, any[][]>;

  const out: Record<string, ItemSaleEntry> = {};

  for (const [id, rows] of Object.entries(raw)) {
    if (!rows || rows.length === 0) continue;
    const r = rows[0];

    // Item field indices (empirically verified against CDN orderedmap JSON).
    // Client ItemValues.as uses [12]=category, [14]=sale_price, [20]=sellable
    // but CDN JSON has different ordering: [14]=category, [16]=sale_price, [21]=sellable
    const sellableStr = String(r[21] ?? "false");
    const sellable =
      sellableStr === "true" || sellableStr === "True" || sellableStr === "TRUE";

    out[id] = {
      category: parseInt(String(r[14] ?? "0"), 10),
      sale_price: parseInt(String(r[16] ?? "0"), 10),
      sellable,
    };
  }

  fs.writeFileSync(
    path.join(ASSETS_OUT, "item_sale.json"),
    JSON.stringify(out, null, 2)
  );
  console.log(
    `[gen_cdn_data] item_sale.json: ${Object.keys(out).length} entries`
  );

  // Stats
  const abilitySouls = Object.entries(out).filter(
    ([, v]) => v.category === 5
  ).length;
  const sellableItems = Object.entries(out).filter(
    ([, v]) => v.sellable
  ).length;
  console.log(`  category=5 (ability souls): ${abilitySouls}`);
  console.log(`  sellable=true: ${sellableItems}`);
}

// ─── Equipment craft cost / dissolve rate ──────────────────────────────

interface CraftEntry {
    dissolve_craft: number;
    awakening_craft: number;
    dissolve_star: number;
}

function extractEquipmentCraft() {
    const craftRaw = JSON.parse(
        fs.readFileSync(path.join(ASSETS_CN, "equipment_craft_point_exchange.json"), "utf8")
    ) as Record<string, string[][]>;
    const starRaw = JSON.parse(
        fs.readFileSync(path.join(ASSETS_CN, "equipment_dissolve_rate.json"), "utf8")
    ) as Record<string, string[][]>;

    const out: Record<string, CraftEntry> = {};
    for (const rarity of ["1", "2", "3", "4", "5"]) {
        const craft = craftRaw[rarity]?.[0] ?? ["0", "0"];
        const star = starRaw[rarity]?.[0] ?? ["0"];
        out[rarity] = {
            dissolve_craft: parseInt(craft[0], 10),
            awakening_craft: parseInt(craft[1], 10),
            dissolve_star: parseInt(star[0], 10),
        };
    }

    fs.writeFileSync(
        path.join(ASSETS_OUT, "equipment_craft.json"),
        JSON.stringify(out, null, 2)
    );
    console.log(`[gen_cdn_data] equipment_craft.json: ${Object.keys(out).length} entries`);
    console.log(`  ${JSON.stringify(out)}`);
}

// ─── Run ─────────────────────────────────────────────────────────────────

console.log("[gen_cdn_data] Extracting CDN data...\n");
extractEquipmentDissolve();
console.log("");
extractItemSale();
console.log("");
extractEquipmentCraft();
console.log("\n[gen_cdn_data] Done.");
