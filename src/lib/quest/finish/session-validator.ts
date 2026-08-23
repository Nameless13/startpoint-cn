import { getPlayerSync } from "../../../data/domains/player"
import { getSession } from "../../../data/domains/session"
import { resolvePlayerIdSync } from "../../../data/activeAccount"
import type { Player } from "../../../data/types"

export async function validateSessionAndPlayer(viewerId: number): Promise<{
    playerId: number
    playerData: Player
} | null> {
    if (!viewerId || isNaN(viewerId)) return null
    const session = await getSession(String(viewerId))
    if (!session) return null
    const playerId = resolvePlayerIdSync(session.accountId)
    if (!playerId) return null
    const playerData = getPlayerSync(playerId)
    if (!playerData) return null
    return { playerId, playerData }
}
