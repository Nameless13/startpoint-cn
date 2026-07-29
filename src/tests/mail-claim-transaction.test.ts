import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";


const databaseDir = mkdtempSync(path.join(tmpdir(), "wf-mail-claim-"));
process.env.WF_DATABASE_DIR = databaseDir;

const playerDomain = require("../data/domains/player") as typeof import("../data/domains/player");
const accountDomain = require("../data/domains/account") as typeof import("../data/domains/account");
const mailDomain = require("../data/domains/mail") as typeof import("../data/domains/mail");
const itemDomain = require("../data/domains/item") as typeof import("../data/domains/item");
const mailLib = require("../lib/mail") as typeof import("../lib/mail");
const { getDb } = require("../data/db") as typeof import("../data/db");

/** The page size the claim endpoints used to read before claiming. */
const LEGACY_CLAIM_WINDOW = 1000;
const REWARD_ITEM_ID = 1;

let playerId = 0;
/** Mail IDs in insertion order — the head of this list sits outside the legacy window. */
let mailIds: number[] = [];


function sendItemMail(count: number): number[] {
    const now = new Date().toISOString().replace("T", " ").substring(0, 19);
    return getDb().transaction((): number[] => {
        const ids: number[] = [];
        for (let index = 0; index < count; index += 1) {
            ids.push(mailDomain.insertMailSync(playerId, {
                reason_id: 0,
                subject: `mail ${index}`,
                description: null,
                type: mailDomain.MailType.ITEM,
                type_id: REWARD_ITEM_ID,
                number: 1,
                receive_time: "0000-00-00 00:00:00",
                create_time: now,
                reward_period_limited: 0,
                reward_limit_time: null,
            }));
        }
        return ids;
    })();
}


function itemCount(): number {
    return itemDomain.getPlayerItemSync(playerId, REWARD_ITEM_ID) ?? 0;
}


function isReceived(mailId: number): boolean {
    const mail = mailDomain.getPlayerMailByIdSync(playerId, mailId);
    assert.ok(mail);
    return mail.receive_time !== "0000-00-00 00:00:00";
}


before(() => {
    const account = accountDomain.insertAccountSync({
        appId: "mail-claim-test",
        idpAlias: "test",
        idpCode: "test",
        idpId: "mail-claim-test",
        status: "active",
    });
    playerId = playerDomain.insertDefaultPlayerSync(account.id).id;
    mailIds = sendItemMail(LEGACY_CLAIM_WINDOW + 5);
});


after(() => {
    getDb().close();
    delete process.env.WF_DATABASE_DIR;
    const resolved = path.resolve(databaseDir);
    const safeBase = path.resolve(tmpdir());
    assert.ok(resolved.startsWith(`${safeBase}${path.sep}`));
    assert.ok(path.basename(resolved).startsWith("wf-mail-claim-"));
    rmSync(resolved, { recursive: true, force: true });
});


test("mail past the legacy claim window is still claimable", () => {
    const oldest = mailIds[0];
    const window = mailDomain.getPlayerMailsSync(playerId, 1, LEGACY_CLAIM_WINDOW, true);
    assert.equal(window.some(mail => mail.id === oldest), false, "test needs a mail outside the window");

    const before = itemCount();
    const claim = mailLib.claimMailSync(playerId, oldest);

    assert.equal(claim.status, "claimed");
    assert.equal(claim.rewards.itemList[String(REWARD_ITEM_ID)], before + 1);
    assert.equal(itemCount(), before + 1);
    assert.ok(isReceived(oldest));
});


test("re-claiming a received mail replays empty instead of paying twice", () => {
    const target = mailIds[1];
    assert.equal(mailLib.claimMailSync(playerId, target).status, "claimed");

    const before = itemCount();
    const replay = mailLib.claimMailSync(playerId, target);

    assert.equal(replay.status, "already_received");
    assert.deepEqual(replay.rewards, mailLib.emptyMailRewards());
    assert.equal(itemCount(), before);
});


test("unknown mail is reported as not found", () => {
    const claim = mailLib.claimMailSync(playerId, Math.max(...mailIds) + 1000);
    assert.equal(claim.status, "not_found");
    assert.deepEqual(claim.rewards, mailLib.emptyMailRewards());
});


test("batch claim pays a duplicated id once", () => {
    const target = mailIds[2];
    const before = itemCount();

    const result = mailLib.claimMailsSync(playerId, [target, target, target]);

    assert.deepEqual(result.claimed, [target]);
    assert.equal(result.alreadyCount, 0);
    assert.equal(itemCount(), before + 1);
});


test("batch claim reaches past the legacy window and counts unclaimable ids", () => {
    const fresh = [mailIds[3], mailIds[4]];
    const alreadyReceived = mailIds[0];
    const unknown = Math.max(...mailIds) + 1000;
    const before = itemCount();

    const result = mailLib.claimMailsSync(playerId, [...fresh, alreadyReceived, unknown]);

    assert.deepEqual(result.claimed.sort((a, b) => a - b), [...fresh].sort((a, b) => a - b));
    assert.equal(result.alreadyCount, 2);
    assert.equal(result.rewards.itemList[String(REWARD_ITEM_ID)], before + fresh.length);
    assert.equal(itemCount(), before + fresh.length);
    for (const mailId of fresh) assert.ok(isReceived(mailId));
});
