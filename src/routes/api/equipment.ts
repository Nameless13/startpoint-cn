// Handles the insertion of mana into characters.

import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { deletePlayerEquipmentSync, getAccountPlayers, getPlayerEquipmentListSync, getPlayerEquipmentSync, getPlayerItemSync, getPlayerSync, getSession, givePlayerItemSync, playerOwnsEquipmentSync, updatePlayerEquipmentSync, updatePlayerItemSync, updatePlayerPartyGroupSync } from "../../data/wdfpData";
import { generateDataHeaders } from "../../utils";
import { clientSerializeEquipment } from "../../lib/equipment";
import { UserEquipment } from "../../data/types";
import { resolvePlayerIdSync } from "../../data/activeAccount";

interface SetProtectionBody {
    protection: boolean
    equipment_ids: number[]
    viewer_id: number
    api_count: number
}

interface UpgradeBody {
    use_stack: boolean,
    upgrade_count: number,
    item_id?: number,
    viewer_id: number,
    api_count: number,
    equipment_id: number
}

interface SellEquipmentListItem {
    equipment_id: number
}

interface SellStackEquipmentListItem extends SellEquipmentListItem {
    number: number
}

interface SellBody {
    equipment_list: SellEquipmentListItem[],
    viewer_id: number,
    api_count: number
}

interface BulkUpgradeBody {
    viewer_id: number
    api_count: number
    equipment_ids: number[]
}

interface BulkSellStackBody {
    viewer_id: number
    api_count: number
    equipment_ids: number[]
}

const wrightpieceItemId = 100000
const starGrainItemId = 990008

// wrightpiece cost for each rank of weapon (awakening)
const equipmentUpgradeCost = [
    5,
    10,
    15,
    20,
    25
]

// wrightpiece reward for dissolving each rank of weapon
const dissolvingCraftPoints = [
    1,
    2,
    3,
    4,
    5
]

// star grain reward for dissolving each rank of weapon
const dissolvingStarGrains = [
    0,
    0,
    1,
    5,
    15
]

// wrightpiece reward for selling each rank of weapon
const equipmentSellReward = [
    0,
    0,
    1,
    5,
    15
]

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/sell_equipment", async(request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as SellBody

        const toSellEquipmentList = body.equipment_list
        const viewerId = body.viewer_id
        if (isNaN(viewerId) || toSellEquipmentList === undefined) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // get wrightpieces
        let newWrightPieces = 0;
        const returnItemList: Record<number, number> = {}

        // sell stacks
        for (const toSell of toSellEquipmentList) {
            const equipmentId = toSell.equipment_id
            const equipmentRarity = Math.floor(equipmentId / 1000000) - 1

            // get the data for the equipment
            const playerEquipmentData = getPlayerEquipmentSync(playerId, equipmentId)
            if (playerEquipmentData === null) return reply.status(400).send({
                "error": "Bad Request",
                "message": "Player does not own equipment."
            }) 

            // add wright pieces
            const stack = playerEquipmentData.stack
            newWrightPieces += (equipmentSellReward[equipmentRarity] ?? 0) * stack

            // delete equipment
            deletePlayerEquipmentSync(playerId, equipmentId)

            // give ability soul
            returnItemList[equipmentId] = givePlayerItemSync(playerId, equipmentId, stack)
        }

        // give wrightpieces
        returnItemList[wrightpieceItemId] = givePlayerItemSync(playerId, wrightpieceItemId, newWrightPieces)

        // respond to client
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "item_list": returnItemList,
                "mail_arrived": false
            }
        })
    })

    fastify.post("/sell_stack", async(request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as SellBody

        const toSellEquipmentList = body.equipment_list
        const viewerId = body.viewer_id
        if (isNaN(viewerId) || toSellEquipmentList === undefined) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // get wrightpieces
        let newWrightPieces = 0;
        const returnItemList: Record<number, number> = {}
        const returnEquipmentList: Object[] = []

        // sell stacks
        for (const toSell of toSellEquipmentList) {
            const equipmentId = toSell.equipment_id
            const sellCount = Math.max(1, (toSell as SellStackEquipmentListItem).number)
            const equipmentRarity = Math.floor(equipmentId / 1000000) - 1

            // get the data for the equipment
            const playerEquipmentData = getPlayerEquipmentSync(playerId, equipmentId)
            if (playerEquipmentData === null) return reply.status(400).send({
                "error": "Bad Request",
                "message": "Player does not own equipment."
            })

            // make sure that we have enough stacks
            const newStack = playerEquipmentData.stack - sellCount
            if (0 > newStack) return reply.status(400).send({
                "error": "Bad Request",
                "message": "Attempt to sell more stacks than owned."
            })

            newWrightPieces += (equipmentSellReward[equipmentRarity] ?? 0) * sellCount

            // update eqwuipment
            playerEquipmentData.stack = newStack
            updatePlayerEquipmentSync(playerId, equipmentId, {
                stack: newStack
            })
            returnEquipmentList.push(clientSerializeEquipment(equipmentId, playerEquipmentData))

            // give ability sould
            returnItemList[equipmentId] = givePlayerItemSync(playerId, equipmentId, sellCount)
        }

        // give wrightpieces
        returnItemList[wrightpieceItemId] = givePlayerItemSync(playerId, wrightpieceItemId, newWrightPieces)

        // respond to client
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "equipment_list": returnEquipmentList,
                "item_list": returnItemList,
                "mail_arrived": false
            }
        })
    })

    fastify.post("/upgrade", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as UpgradeBody

        const viewerId = body.viewer_id
        const upgradeCount = Math.max(1, body.upgrade_count ?? 1)
        const useStack = body.use_stack
        const itemId = body.item_id
        const equipmentId = body.equipment_id
        if (isNaN(viewerId) || isNaN(equipmentId) || useStack === undefined) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // get equipment
        const equipment = getPlayerEquipmentSync(playerId, equipmentId)
        if (equipment === null) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Player does not own equipment."
        })

        // validate that we won't overflow the equipment's level.
        const newLevel = equipment.level + upgradeCount
        if (newLevel > 5) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Cannot upgrade weapon more than 4 times."
        })

        // check if the equipment can be upgraded
        const newStack = useStack ? equipment.stack - upgradeCount : equipment.stack
        if (0 > newStack) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Not enough stack."
        })

        const equipmentRarity = Math.floor(equipmentId / 1000000) - 1
        const wrightPieces = getPlayerItemSync(playerId, wrightpieceItemId) ?? 0
        const upgradeCost = equipmentUpgradeCost[equipmentRarity] ?? 0
        const newWrightPieces = wrightPieces - (upgradeCost * upgradeCount)
        if (0 > newWrightPieces) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Not enough of wrightpieces."
        }) 
        
        const itemCount = itemId ? getPlayerItemSync(playerId, itemId) ?? 0 : 0
        const newItemCount = !useStack ? itemCount - upgradeCount : itemCount
        if (0 > newItemCount) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Not enough of item."
        })

        const returnItemList: Record<string, number> = {}

        // deduct item
        if (!useStack && itemId !== undefined) {
            returnItemList[itemId] = newItemCount
            updatePlayerItemSync(playerId, itemId, newItemCount)
        }

        // deduct wrightpiece
        returnItemList[wrightpieceItemId] = newWrightPieces
        updatePlayerItemSync(playerId, wrightpieceItemId, newWrightPieces)

        // upgrade weapon
        equipment.level = newLevel
        equipment.stack = newStack
        updatePlayerEquipmentSync(playerId, equipmentId, {
            "stack": newStack,
            "level": newLevel
        })

        // give ability cores
        returnItemList[equipmentId] = givePlayerItemSync(playerId, equipmentId, upgradeCount)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {
                "equipment_list": [
                    clientSerializeEquipment(equipmentId, equipment)
                ],
                "item_list": returnItemList,
                "mail_arrived": false
            }
        })
    })

    fastify.post("/bulk_upgrade", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as BulkUpgradeBody

        const viewerId = body.viewer_id
        const equipmentIds = body.equipment_ids
        if (isNaN(viewerId) || !equipmentIds || !Array.isArray(equipmentIds) || equipmentIds.length === 0) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            })
        }

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        const player = getPlayerSync(playerId)
        if (!player) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "Player not found."
        })

        // Phase 1: calculate upgrade counts and total cost
        const upgrades: Array<{ equipmentId: number, upgradeCount: number }> = []
        let totalCraftPointCost = 0
        const seen = new Set<number>()

        for (const equipmentId of equipmentIds) {
            if (seen.has(equipmentId)) continue
            seen.add(equipmentId)

            const equipment = getPlayerEquipmentSync(playerId, equipmentId)
            if (!equipment) continue

            const upgradeCount = Math.min(5 - equipment.level, equipment.stack)
            if (upgradeCount <= 0) continue

            const rarity = Math.floor(equipmentId / 1000000) - 1
            totalCraftPointCost += equipmentUpgradeCost[rarity] * upgradeCount
            upgrades.push({ equipmentId, upgradeCount })
        }

        if (upgrades.length === 0) {
            reply.header("content-type", "application/x-msgpack")
            return reply.status(200).send({
                "data_headers": generateDataHeaders({ viewer_id: viewerId }),
                "data": {
                    "equipment_list": [],
                    "item_list": {},
                    "mail_arrived": false
                }
            })
        }

        // Check craft point balance
        const currentCraftPoints = getPlayerItemSync(playerId, wrightpieceItemId) ?? 0
        if (totalCraftPointCost > currentCraftPoints) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Not enough craft points."
            })
        }

        // Phase 2: apply upgrades
        const returnEquipmentList: Object[] = []
        const returnItemList: Record<number, number> = {}

        for (const { equipmentId, upgradeCount } of upgrades) {
            const equipment = getPlayerEquipmentSync(playerId, equipmentId)!

            equipment.level += upgradeCount
            equipment.stack -= upgradeCount
            updatePlayerEquipmentSync(playerId, equipmentId, {
                level: equipment.level,
                stack: equipment.stack
            })

            returnEquipmentList.push(clientSerializeEquipment(equipmentId, equipment))
            returnItemList[equipmentId] = givePlayerItemSync(playerId, equipmentId, upgradeCount)
        }

        // Deduct craft points
        const newCraftPoints = currentCraftPoints - totalCraftPointCost
        updatePlayerItemSync(playerId, wrightpieceItemId, newCraftPoints)
        returnItemList[wrightpieceItemId] = newCraftPoints

        console.log(`[BULK_UPGRADE] player ${playerId}: ${upgrades.length} equipment upgraded, craft points ${currentCraftPoints} -> ${newCraftPoints}`)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({ viewer_id: viewerId }),
            "data": {
                "equipment_list": returnEquipmentList,
                "item_list": returnItemList,
                "mail_arrived": false
            }
        })
    })

    fastify.post("/bulk_sell_stack", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as BulkSellStackBody

        const viewerId = body.viewer_id
        const equipmentIds = body.equipment_ids
        if (isNaN(viewerId) || !equipmentIds || !Array.isArray(equipmentIds) || equipmentIds.length === 0) {
            return reply.status(400).send({
                "error": "Bad Request",
                "message": "Invalid request body."
            })
        }

        const session = await getSession(viewerId.toString())
        if (!session) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        const playerId = resolvePlayerIdSync(session.accountId)!
        if (playerId === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        const player = getPlayerSync(playerId)
        if (!player) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "Player not found."
        })

        // Phase 1: calculate rewards per equipment
        let totalCraftPoints = 0
        let totalStarGrains = 0
        const abilitySoulCounts: Record<number, number> = {}
        const toSell: Array<{ equipmentId: number, stack: number }> = []
        const seen = new Set<number>()

        for (const equipmentId of equipmentIds) {
            if (seen.has(equipmentId)) continue
            seen.add(equipmentId)

            const equipment = getPlayerEquipmentSync(playerId, equipmentId)
            if (!equipment) continue

            const stack = equipment.stack
            if (stack <= 0) continue

            const rarity = Math.floor(equipmentId / 1000000) - 1
            totalCraftPoints += dissolvingCraftPoints[rarity] * stack
            totalStarGrains += dissolvingStarGrains[rarity] * stack
            abilitySoulCounts[equipmentId] = (abilitySoulCounts[equipmentId] ?? 0) + stack
            toSell.push({ equipmentId, stack })
        }

        if (toSell.length === 0) {
            reply.header("content-type", "application/x-msgpack")
            return reply.status(200).send({
                "data_headers": generateDataHeaders({ viewer_id: viewerId }),
                "data": {
                    "equipment_list": [],
                    "item_list": {},
                    "mail_arrived": false
                }
            })
        }

        // Phase 2: delete equipment, give items
        for (const { equipmentId } of toSell) {
            deletePlayerEquipmentSync(playerId, equipmentId)
        }

        const returnItemList: Record<number, number> = {}

        if (totalCraftPoints > 0) {
            returnItemList[wrightpieceItemId] = givePlayerItemSync(playerId, wrightpieceItemId, totalCraftPoints)
        }
        if (totalStarGrains > 0) {
            returnItemList[starGrainItemId] = givePlayerItemSync(playerId, starGrainItemId, totalStarGrains)
        }
        for (const [equipmentId, count] of Object.entries(abilitySoulCounts)) {
            returnItemList[parseInt(equipmentId)] = givePlayerItemSync(playerId, parseInt(equipmentId), count)
        }

        // Get full remaining equipment list
        const allEquipment = getPlayerEquipmentListSync(playerId)
        const returnEquipmentList: Object[] = []
        for (const [equipId, equip] of Object.entries(allEquipment)) {
            returnEquipmentList.push(clientSerializeEquipment(parseInt(equipId), equip))
        }

        const craftPointLog = totalCraftPoints > 0 ? `craft +${totalCraftPoints} ` : ""
        const starGrainLog = totalStarGrains > 0 ? `star +${totalStarGrains} ` : ""
        console.log(`[BULK_SELL] player ${playerId}: ${toSell.length} equipment dissolved, ${craftPointLog}${starGrainLog}ability souls: ${Object.keys(abilitySoulCounts).length} types`)

        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({ viewer_id: viewerId }),
            "data": {
                "equipment_list": returnEquipmentList,
                "item_list": returnItemList,
                "mail_arrived": false
            }
        })
    })

    fastify.post("/set_protection", async (request: FastifyRequest, reply: FastifyReply) => {
        const body = request.body as SetProtectionBody

        const viewerId = body.viewer_id
        if (!viewerId || isNaN(viewerId)) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid request body."
        })

        const viewerIdSession = await getSession(viewerId.toString())
        if (!viewerIdSession) return reply.status(400).send({
            "error": "Bad Request",
            "message": "Invalid viewer id."
        })

        // get player
        const playerId = resolvePlayerIdSync(viewerIdSession.accountId)!
        const player = playerId !== null ? getPlayerSync(playerId) : null

        if (player === null) return reply.status(500).send({
            "error": "Internal Server Error",
            "message": "No players bound to account."
        })

        // update protection
        const newProtection = body.protection
        for (const equipmentId of body.equipment_ids) {
            if (playerOwnsEquipmentSync(playerId, equipmentId)) {
                updatePlayerEquipmentSync(playerId, equipmentId, {
                    protection: newProtection
                })
            }
        }
        
        reply.header("content-type", "application/x-msgpack")
        return reply.status(200).send({
            "data_headers": generateDataHeaders({
                viewer_id: viewerId
            }),
            "data": {}
        })
    })
}

export default routes;