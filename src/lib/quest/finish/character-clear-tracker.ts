// Tracks character quest clears for awakening missions
// Leader (position 0) tracked separately for "以X为队长" tasks
// Other party members for "队伍中编有X" tasks

import { incrementPlayerCharacterClearSync } from "../../../data/domains/character_clear"
import type { FinishContext } from "./types"

export function trackCharacterClears(ctx: FinishContext): void {
    const party = ctx.party
    const leaderId = party.characters[0]?.id
    const isMulti = ctx.isMulti ?? false

    if (leaderId) {
        incrementPlayerCharacterClearSync(ctx.playerId, leaderId, isMulti, true)
    }

    const seen = new Set<number>([leaderId].filter(Boolean) as number[])
    for (let i = 1; i < party.characters.length; i++) {
        const c = party.characters[i]
        if (c?.id && !seen.has(c.id)) {
            incrementPlayerCharacterClearSync(ctx.playerId, c.id, isMulti, false)
            seen.add(c.id)
        }
    }
    for (const c of party.unison_characters) {
        if (c?.id && !seen.has(c.id)) {
            incrementPlayerCharacterClearSync(ctx.playerId, c.id, isMulti, false)
            seen.add(c.id)
        }
    }
}
