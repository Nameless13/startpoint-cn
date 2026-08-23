import type { BattleQuest } from "../../types"

export function calculateClearRank(clearTime: number, questData: BattleQuest): number | null {
    const hasRankThresholds = questData.bRankTime > 0
    if (!hasRankThresholds) return null
    if (questData.sPlusRankTime >= clearTime) return 5
    if (questData.sRankTime >= clearTime) return 4
    if (questData.aRankTime >= clearTime) return 3
    if (questData.bRankTime >= clearTime) return 2
    return 1
}
