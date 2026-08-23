// Accumulates zone-level powerflip and dash counters for mission progress

import { updatePlayerSync } from "../../../data/domains/player"
import type { FinishContext } from "./types"

export function trackPowerflip(ctx: FinishContext): void {
    const zones = ctx.statistics.zones || []
    let powerFlipCount = 0
    let dashCount = 0
    for (const zone of zones) {
        powerFlipCount += zone.use_power_flip_count ?? 0
        dashCount += zone.use_dash_count ?? 0
    }
    if (powerFlipCount > 0 || dashCount > 0) {
        updatePlayerSync({
            id: ctx.playerId,
            totalPowerflips: (ctx.player.totalPowerflips ?? 0) + powerFlipCount,
            totalDashes: (ctx.player.totalDashes ?? 0) + dashCount,
        })
    }
}
