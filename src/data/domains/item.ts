import { getDb } from "../db";
import { RawPlayerItem } from "../types";

/**
 * Gets the amount of a singular item that a player owns.
 * 
 * @param playerId The ID of the player.
 * @param itemId The ID of the item.
 * @returns The amount of the item that the player owns, or null, indicating no ownership.
 */
export function getPlayerItemSync(
    playerId: number,
    itemId: number | string
): number | null {
    const db = getDb();
    const rawItem = db.prepare(`
    SELECT id, amount
    FROM players_items
    WHERE player_id = ? AND id = ?
    `).get(playerId, Number(itemId)) as RawPlayerItem | undefined

    return rawItem === undefined ? null : rawItem.amount
}

/**
 * Gets the items that a player owns.
 * 
 * @param playerId The ID of the player.
 * @returns A record where the index is the item's ID and the value is the item's amount.
 */
export function getPlayerItemsSync(
    playerId: number
): Record<string, number> {
    const db = getDb();
    const rawItems = db.prepare(`
    SELECT id, amount
    FROM players_items
    WHERE player_id = ?
    `).all(playerId) as RawPlayerItem[]

    const output: Record<string, number> = {}
    for (const rawItem of rawItems) {
        output[rawItem.id.toString()] = rawItem.amount
    }

    return output
}

/**
 * Inserts a singular item into the player's inventory.
 * 
 * @param playerId The ID of the player.
 * @param itemId The ID of the item to insert.
 * @param amount The amount of the item to insert.
 */
function insertPlayerItemSync(
    playerId: number,
    itemId: number | string,
    amount: number
) {
    const db = getDb();
    db.prepare(`
    INSERT INTO players_items (id, amount, player_id)
    VALUES (?, ?, ?)
    `).run(Number(itemId), amount, playerId)
}

/**
 * Batch inserts a record of player items into a player's inventory.
 * 
 * @param playerId The ID of the player.
 * @param items The record of items.
 */
export function insertPlayerItemsSync(
    playerId: number,
    items: Record<string, number>
) {
    const db = getDb();
    db.transaction(() => {
        for (const [itemId, amount] of Object.entries(items)) {
            insertPlayerItemSync(playerId, itemId, amount)
        }
    })()
}

/**
 * Updates a player's item's amount.
 * 
 * @param playerId The ID of the player.
 * @param itemId The item's ID.
 * @param amount The new amount the item should have.
 */
export function updatePlayerItemSync(
    playerId: number,
    itemId: string | number,
    amount: number
) {
    const db = getDb();
    db.prepare(`
    UPDATE players_items
    SET amount = ?
    WHERE player_id = ? AND id = ?
    `).run(amount, playerId, Number(itemId))
}

/**
 * Gives a player giveAmount of an item.
 * 
 * @param playerId The ID of the player.
 * @param itemId The ID of the item.
 * @param giveAmount The amount of the item to give.
 * @returns The new total amount of the item that the player owns.
 */
export function givePlayerItemSync(
    playerId: number,
    itemId: string | number,
    giveAmount: number
): number {
    // check if the player owns the item
    const ownedAmount = getPlayerItemSync(playerId, itemId)
    if (ownedAmount === null) {
        insertPlayerItemSync(playerId, itemId, giveAmount)
        return giveAmount
    } else {
        const newAmount = ownedAmount + giveAmount
        updatePlayerItemSync(playerId, itemId, newAmount)
        return newAmount
    }
}
