/**
 * Test helper: send msgpack-encoded requests and decode responses.
 * Usage: node scripts/test_equipment.js
 */
const http = require('http');
const { pack, unpack } = require('msgpackr');

const HOST = '127.0.0.1';
const API = '/api/index.php/equipment';
const ITEM_API = '/api/index.php/item';
const VIEWER_ID = 1;

function post(path, body) {
  return new Promise((resolve, reject) => {
    const packed = pack(body);
    const encoded = Buffer.from(packed).toString('base64');
    const options = {
      hostname: HOST,
      port: 8001,
      path: path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(encoded),
      },
    };
    const req = http.request(options, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        try {
          const data = unpack(Buffer.from(Buffer.concat(chunks).toString(), 'base64'));
          resolve({ status: res.statusCode, data });
        } catch (e) {
          resolve({ status: res.statusCode, raw: Buffer.concat(chunks).toString() });
        }
      });
    });
    req.on('error', reject);
    req.write(encoded);
    req.end();
  });
}

function log(label, obj) {
  console.log(`\n=== ${label} ===`);
  console.log(JSON.stringify(obj, null, 2).substring(0, 800));
}

async function run() {
  // ─── Test 1: bulk_sell_stack — mixed source equipment ──────────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 1: bulk_sell_stack — CDN star grain check');
  console.log('═══════════════════════════════════════════');
  console.log('Equipment: 3010007 (source=0, gives star) + 4010003 (source≠0, no star)');

  const res1 = await post(`${API}/bulk_sell_stack`, {
    equipment_ids: [3010007, 4010003],
    viewer_id: VIEWER_ID,
    api_count: 1,
  });
  log('Response', res1);

  // ─── Test 2a: bulk_sell_stack — generate=false equipment ─────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 2a: bulk_sell_stack — generate_ability_soul=false');
  console.log('═══════════════════════════════════════════');
  console.log('Equipment: 5020043 (generate=false, no ability soul)');

  const res2a = await post(`${API}/bulk_sell_stack`, {
    equipment_ids: [5020043],
    viewer_id: VIEWER_ID,
    api_count: 2,
  });
  log('Response', res2a);

  // ─── Test 2b: bulk_sell_stack — generate=true equipment ──────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 2b: bulk_sell_stack — generate_ability_soul=true (control)');
  console.log('═══════════════════════════════════════════');
  console.log('Equipment: 3010007 again (generate=true)');

  const res2b = await post(`${API}/bulk_sell_stack`, {
    equipment_ids: [3010007],
    viewer_id: VIEWER_ID,
    api_count: 3,
  });
  log('Response', res2b);

  // ─── Test 3: sell_equipment ──────────────────────────────────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 3: sell_equipment');
  console.log('═══════════════════════════════════════════');
  console.log('Equipment: 4010003 (single sell, count=1 for souls)');

  const res3 = await post(`${API}/sell_equipment`, {
    equipment_list: [{ equipment_id: 4010003 }],
    viewer_id: VIEWER_ID,
    api_count: 4,
  });
  log('Response', res3);

  // ─── Test 4: sell_stack ──────────────────────────────────────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 4: sell_stack');
  console.log('═══════════════════════════════════════════');
  console.log('Equipment: 5020043 (partial stack, generate=false)');

  const res4 = await post(`${API}/sell_stack`, {
    equipment_list: [{ equipment_id: 5020043, number: 1 }],
    viewer_id: VIEWER_ID,
    api_count: 5,
  });
  log('Response', res4);

  // ─── Test 5: item/sell — basic sale ──────────────────────────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 5: /item/sell — basic sale');
  console.log('═══════════════════════════════════════════');
  console.log('Item: 3010007 ×5 (ability soul, sellable=true, price=100)');

  const res5 = await post(`${ITEM_API}/sell`, {
    item_id: 3010007,
    sell_number: 5,
    viewer_id: VIEWER_ID,
    api_count: 6,
  });
  log('Response', res5);

  // ─── Test 6: item/sell — party-locked soul ───────────────────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 6: /item/sell — party-locked ability soul');
  console.log('═══════════════════════════════════════════');
  console.log('Item: 5050039 (used in 1 party slot, owned 5 → sellable 4)');
  console.log('Selling 4 → should SUCCEED');

  const res6a = await post(`${ITEM_API}/sell`, {
    item_id: 5050039,
    sell_number: 4,
    viewer_id: VIEWER_ID,
    api_count: 7,
  });
  log('4 sell result', res6a);

  console.log('\nSelling 9 (all 5 owned) → should FAIL');

  const res6b = await post(`${ITEM_API}/sell`, {
    item_id: 5050039,
    sell_number: 5,
    viewer_id: VIEWER_ID,
    api_count: 8,
  });
  log('5 sell result', res6b);

  // ─── Test 7: item/sell — non-sellable item ───────────────────────────
  console.log('\n═══════════════════════════════════════════');
  console.log('TEST 7: /item/sell — non-sellable item');
  console.log('═══════════════════════════════════════════');
  console.log('Item: 100000 (craft points, sellable=false)');

  const res7 = await post(`${ITEM_API}/sell`, {
    item_id: 100000,
    sell_number: 1,
    viewer_id: VIEWER_ID,
    api_count: 9,
  });
  log('Response', res7);

  console.log('\n═══════════════════════════════════════════');
  console.log('ALL TESTS COMPLETE');
  console.log('═══════════════════════════════════════════');
}

run().catch((e) => {
  console.error('TEST ERROR:', e.message);
  process.exit(1);
});
