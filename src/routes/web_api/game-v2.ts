import { FastifyPluginAsync, FastifyRequest, FastifyReply } from "fastify";
import jwt from "jsonwebtoken";
import { getDb } from "../../data/db";
import { getGachaSync } from "../../lib/assets";
import { drawGachaWithMetadataSync, rewardPlayerGachaDrawResultSync } from "../../lib/gacha";
import { getPlayerSync, updatePlayerSync, getPlayerDailyChallengePointListSync, updatePlayerDailyChallengePointSync } from "../../data/domains/player";
import { getPlayerCharactersSync } from "../../data/domains/character";
import { getPlayerItemSync, updatePlayerItemSync, givePlayerItemSync } from "../../data/domains/item";
import { insertPlayerQuestProgressSync, updatePlayerQuestProgressSync, getPlayerSingleQuestProgressSync } from "../../data/domains/quest";
import { insertPlayerActiveQuestSync, deletePlayerActiveQuestSync, updatePlayerActiveQuestContinueCountSync, getPlayerActiveQuestSync } from "../../data/domains/quest_active";
import { getPlayerActiveMissionsSync } from "../../data/domains/mission";
import { getGenericShopItemsSync } from "../../lib/assets";
import { ShopType, QuestCategory, BattleQuest, GivePlayerScoreRewardsResult } from "../../lib/types";
import { calculateClearRank } from "../../lib/quest/finish/quest-calc";
import { validateSessionAndPlayer } from "../../lib/quest/finish/session-validator";
import { resolveActiveQuest } from "../../lib/quest/finish/active-quest-resolver";
import { canStartQuestByPrerequisites, hasClearedQuestPrerequisiteForCategory, canContinueBattle, resolveBattleStartEntryCost, resolveBattleStartStaminaCost } from "../../lib/quest/start-handler";
import { givePlayerScoreRewardsSync, givePlayerRewardSync } from "../../lib/quest";
import { givePlayerCharactersExpSync } from "../../lib/character";
import { givePlayerCharacterSync } from "../../lib/character";
import { getQuestFromCategorySync, getRushEventFolderMaxRounds, getRushEventFolderClearRewards } from "../../lib/assets";
import { handleRushEventFinish } from "../../lib/quest/finish/rush-handler";
import { handleRoguePerRoundDrops } from "../../lib/quest/finish/rogue-drops";
import { handleRaidEventFinish } from "../../lib/quest/finish/raid-handler";
import { handleCarnivalEventFinish } from "../../lib/quest/finish/carnival-handler";
import { handleDailyChallengePoint } from "../../lib/quest/finish/challenge-point";
import { trackCharacterClears } from "../../lib/quest/finish/character-clear-tracker";
import { trackPowerflip } from "../../lib/quest/finish/powerflip-tracker";
import { trackLeaderPowerflip } from "../../lib/quest/finish/leader-powerflip-tracker";
import { trackPartyCoClears } from "../../lib/quest/finish/party-co-clear-tracker";
import { collectPartyCharacterIds, recordBattleMissionDimensionsSafe, summarizeBattleStatistics } from "../../lib/mission";
import type { FinishContext } from "../../lib/quest/finish/types";
import { computeRealTimeStamina, getRankDegree, getMaxStamina } from "../../lib/stamina";
import { getStaminaCost } from "../../lib/stamina-cost";
import { getSerializedPlayerRushEventPlayedPartiesSync } from "../../lib/rush";
import questEntryCosts from "../../../assets/quest_entry_costs.json";
import scoreAttackBorderRewards from "../../../assets/score_attack_border_reward.json";
import eventChallengePointMap from "../../../assets/event_challenge_point_map.json";
import { RushEventBattleType } from "../../data/types";

interface V2RouteOptions {
    jwtSecret: string;
}

interface AuthPayload {
    playerId: number;
}

// ─── JWT 辅助 ────────────────────────────────────────────────────────────────

function verifyJwt(auth: string | undefined, jwtSecret: string): AuthPayload | null {
    if (!auth?.startsWith("Bearer ")) return null;
    try {
        return jwt.verify(auth.slice(7), jwtSecret) as AuthPayload;
    } catch {
        return null;
    }
}

// ─── 玩家数据转换 ────────────────────────────────────────────────────────────

interface PlayerInfoResponse {
    id: number;
    name: string;
    stamina: number;
    staminaHealTime: string;
    vmoney: number;
    freeVmoney: number;
    rankPoint: number;
    role: number;
    totalLoginDays: number;
    boostPoint: number;
    bondToken: number;
    starCrumb: number;
    expPool: number;
    leaderCharacterId: number;
    degreeId: number;
    freeMana: number;
    paidMana: number;
}

// ─── 扭蛋请求/响应 ──────────────────────────────────────────────────────────

interface GachaDrawRequest {
    gachaId: number;
    times?: number; // 默认 1，最多 10
}

interface GachaDrawItem {
    character_id?: number;
    equipment_id?: number;
    movie_id?: string;
    seed?: number;
    entry_count?: number;
    ex_boost_item?: { id: number; count: number } | [];
    treasure_up_type?: number;
}

interface GachaDrawResponse {
    ok: boolean;
    draw?: GachaDrawItem[];
    items?: Record<number, number>;
    characters?: number[];
    error?: string;
}

// ─── 持有角色 ───────────────────────────────────────────────────────────────

interface CharacterInfo {
    id: number;
    entryCount: number;
    evolutionLevel: number;
    overLimitStep: number;
    exp: number;
    joinTime: string;
}

interface GetCharactersResponse {
    ok: boolean;
    characters?: CharacterInfo[];
    error?: string;
}

// ─── 任务 ──────────────────────────────────────────────────────────────────

interface MissionProgress {
    missionId: number;
    progress: number;
    stages?: Array<{
        stageId: number;
        status: string; // "claimed" | "unclaimed"
    }>;
}

interface MissionListResponse {
    ok: boolean;
    missions?: MissionProgress[];
    error?: string;
}

interface MissionClaimRequest {
    missionId: number;
    stageId?: number;
}

interface MissionClaimResponse {
    ok: boolean;
    error?: string;
}

// ─── 商店 ──────────────────────────────────────────────────────────────────

interface ShopItemInfo {
    itemId: number;
    cost: number;
    stock: number;
}

interface ShopListResponse {
    ok: boolean;
    items?: ShopItemInfo[];
    error?: string;
}

interface ShopBuyRequest {
    itemId: number;
    shopType?: number; // 默认 GENERAL
    count?: number;
}

interface ShopBuyResponse {
    ok: boolean;
    purchased?: number;
    error?: string;
}

// ─── 战斗 ──────────────────────────────────────────────────────────────────

interface BattleStartRequest {
    quest_id: number;
    category: number;
    party_id: number;
    use_boost_point: boolean;
    use_boss_boost_point: boolean;
    is_auto_start_mode: boolean;
    play_id: string;
}

interface BattleStartResponse {
    ok: boolean;
    error?: string;
    stamina?: number;
    stamina_heal_time?: string;
}

interface BattleFinishRequest {
    quest_id: number;
    category: number;
    is_accomplished: boolean;
    score: number;
    elapsed_time_ms: number;
    add_mana: number;
    continue_count: number;
    statistics: {
        party: {
            characters: Array<{ id: number | null } | null>;
            unison_characters: Array<{ id: number | null } | null>;
            equipments?: Array<{ id: number | null } | null>;
            ability_soul_ids?: (number | null)[];
        };
        zones?: Array<{ [key: string]: any }>;
        max_combo_count?: number;
        [key: string]: any;
    };
}

interface BattleFinishResponse {
    ok: boolean;
    error?: string;
    clear_rank?: number | null;
    new_rank_point?: number;
    new_free_vmoney?: number;
    new_free_mana?: number;
    new_exp_pool?: number;
    new_boost_point?: number;
    new_boss_boost_point?: number;
    new_stamina?: number;
    new_stamina_heal_time?: string;
    items?: Record<string, number>;
    characters?: Record<string, any>[];
    join_characters?: number[];
}

interface BattleAbortRequest {
    quest_id: number;
    category: number;
}

interface BattleAbortResponse {
    ok: boolean;
    error?: string;
}

interface BattleContinueRequest {
    quest_id: number;
    category: number;
}

interface BattleContinueResponse {
    ok: boolean;
    error?: string;
    continue_count?: number;
}

// ─── 插件定义 ──────────────────────────────────────────────────────────────

const routes: FastifyPluginAsync<V2RouteOptions> = async (fastify, options) => {
    const { jwtSecret } = options;

    // ── GET /api/v2/player/info ────────────────────────────────────────────
    fastify.get("/player/info", async (request: FastifyRequest, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const player = getPlayerSync(payload.playerId);
        if (!player) {
            return reply.status(404).send({ ok: false, error: "player_not_found" });
        }

        const info: PlayerInfoResponse = {
            id: player.id,
            name: player.name,
            stamina: player.stamina,
            staminaHealTime: player.staminaHealTime.toISOString(),
            vmoney: player.vmoney,
            freeVmoney: player.freeVmoney,
            rankPoint: player.rankPoint,
            role: player.role,
            totalLoginDays: player.totalLoginDays,
            boostPoint: player.boostPoint,
            bondToken: player.bondToken,
            starCrumb: player.starCrumb,
            expPool: player.expPool,
            leaderCharacterId: player.leaderCharacterId,
            degreeId: player.degreeId,
            freeMana: player.freeMana,
            paidMana: player.paidMana,
        };

        return reply.send({ ok: true, player: info });
    });

    // ── POST /api/v2/gacha/draw ───────────────────────────────────────────
    fastify.post("/gacha/draw", async (request: FastifyRequest<{ Body: GachaDrawRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const { gachaId, times = 1 } = request.body;
        if (!gachaId || isNaN(gachaId) || times < 1 || times > 10) {
            return reply.status(400).send({ ok: false, error: "invalid_parameters" });
        }

        const gacha = getGachaSync(String(gachaId));
        if (!gacha) {
            return reply.status(404).send({ ok: false, error: "gacha_not_found" });
        }

        const player = getPlayerSync(payload.playerId);
        if (!player) {
            return reply.status(404).send({ ok: false, error: "player_not_found" });
        }

        // 计算费用
        const costPerDraw = times > 1 ? (gacha.multiCost || gacha.singleCost) : gacha.singleCost;
        const totalCost = costPerDraw;

        // 检查货币（paymentType: 0=vmoney, 1=freemoney）
        const currentCurrency = gacha.paymentType === 1 ? player.freeVmoney : player.vmoney;
        if (currentCurrency < totalCost) {
            return reply.status(400).send({ ok: false, error: "insufficient_currency" });
        }

        // 抽卡
        const drawMetadata = drawGachaWithMetadataSync(gacha, times);
        const drawResult = drawMetadata.map(d => d.id);

        // 发放奖励（内部会更新 DB）
        const rewardResult = rewardPlayerGachaDrawResultSync(payload.playerId, gacha, drawResult, drawMetadata);

        // 扣除货币
        const newCurrency = currentCurrency - totalCost;
        if (gacha.paymentType === 1) {
            player.freeVmoney = newCurrency;
        } else {
            player.vmoney = newCurrency;
        }
        updatePlayerSync(player);

        // 构建响应
        const drawItems: GachaDrawItem[] = rewardResult.draw.map(d => {
            if ("character_id" in d) {
                return {
                    character_id: d.character_id,
                    movie_id: d.movie_id,
                    seed: d.seed,
                    entry_count: d.entry_count,
                    ex_boost_item: d.ex_boost_item,
                };
            } else {
                return {
                    equipment_id: d.equipment_id,
                    treasure_up_type: d.treasure_up_type,
                };
            }
        });

        const newCharacterIds = drawItems
            .filter(d => d.character_id !== undefined)
            .map(d => d.character_id!);

        return reply.send({
            ok: true,
            draw: drawItems,
            items: rewardResult.items,
            characters: newCharacterIds,
        });
    });

    // ── GET /api/v2/player/characters ─────────────────────────────────────
    fastify.get("/player/characters", async (request: FastifyRequest, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const characters = getPlayerCharactersSync(payload.playerId);
        const characterList: CharacterInfo[] = Object.entries(characters).map(([id, char]) => ({
            id: Number(id),
            entryCount: char.entryCount,
            evolutionLevel: char.evolutionLevel,
            overLimitStep: char.overLimitStep,
            exp: char.exp,
            joinTime: char.joinTime.toISOString(),
        }));

        return reply.send({ ok: true, characters: characterList });
    });

    // ── GET /api/v2/mission/list ──────────────────────────────────────────
    fastify.get("/mission/list", async (request: FastifyRequest, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const missions = getPlayerActiveMissionsSync(payload.playerId);
        const missionList: MissionProgress[] = Object.entries(missions).map(([id, mission]) => ({
            missionId: Number(id),
            progress: mission.progress,
            stages: mission.stages ? Object.entries(mission.stages).map(([stageId, status]) => ({
                stageId: Number(stageId),
                status: status ? "claimed" : "unclaimed",
            })) : undefined,
        }));

        return reply.send({ ok: true, missions: missionList });
    });

    // ── POST /api/v2/mission/claim ────────────────────────────────────────
    fastify.post("/mission/claim", async (request: FastifyRequest<{ Body: MissionClaimRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const { missionId, stageId } = request.body;
        if (!missionId || isNaN(missionId)) {
            return reply.status(400).send({ ok: false, error: "invalid_mission_id" });
        }

        const db = getDb();

        if (stageId !== undefined) {
            // 领取特定阶段奖励
            db.prepare(`
                UPDATE players_active_missions_stages
                SET status = 1
                WHERE player_id = ? AND mission_id = ? AND id = ?
            `).run(payload.playerId, missionId, stageId);
        } else {
            // 领取所有未领取阶段
            db.prepare(`
                UPDATE players_active_missions_stages
                SET status = 1
                WHERE player_id = ? AND mission_id = ? AND status = 0
            `).run(payload.playerId, missionId);
        }

        return reply.send({ ok: true });
    });

    // ── GET /api/v2/shop/list ─────────────────────────────────────────────
    fastify.get("/shop/list", async (request: FastifyRequest, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        // 获取通用商店
        const shopItems = getGenericShopItemsSync(ShopType.GENERAL);
        if (!shopItems) {
            return reply.status(404).send({ ok: false, error: "shop_not_found" });
        }

        const itemArray: ShopItemInfo[] = Object.entries(shopItems).map(([id, item]) => ({
            itemId: Number(id),
            cost: item.costs?.[0]?.amount || 0,
            stock: item.stock,
        }));

        return reply.send({ ok: true, items: itemArray });
    });

    // ── POST /api/v2/shop/buy ─────────────────────────────────────────────
    fastify.post("/shop/buy", async (request: FastifyRequest<{ Body: ShopBuyRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const { itemId, shopType = ShopType.GENERAL, count = 1 } = request.body;
        if (!itemId || isNaN(itemId) || count < 1) {
            return reply.status(400).send({ ok: false, error: "invalid_parameters" });
        }

        const player = getPlayerSync(payload.playerId);
        if (!player) {
            return reply.status(404).send({ ok: false, error: "player_not_found" });
        }

        // 简化实现：直接增加道具数量
        const db = getDb();
        const existing = db.prepare(`
            SELECT id, amount FROM players_items WHERE player_id = ? AND id = ?
        `).get(payload.playerId, itemId) as { id: number; amount: number } | undefined;

        if (existing) {
            db.prepare(`
                UPDATE players_items SET amount = amount + ? WHERE player_id = ? AND id = ?
            `).run(count, payload.playerId, itemId);
        } else {
            db.prepare(`
                INSERT INTO players_items (id, amount, player_id) VALUES (?, ?, ?)
            `).run(itemId, count, payload.playerId);
        }

        return reply.send({ ok: true, purchased: count });
    });

    // ── POST /api/v2/battle/start ──────────────────────────────────────────
    fastify.post("/battle/start", async (request: FastifyRequest<{ Body: BattleStartRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const { quest_id, category, party_id, use_boost_point, use_boss_boost_point, is_auto_start_mode, play_id } = request.body;
        if (
            isNaN(quest_id) || isNaN(category) || isNaN(party_id) ||
            use_boost_point === undefined || use_boss_boost_point === undefined ||
            is_auto_start_mode === undefined
        ) {
            return reply.status(400).send({ ok: false, error: "invalid_parameters" });
        }

        const player = getPlayerSync(payload.playerId);
        if (!player) {
            return reply.status(404).send({ ok: false, error: "player_not_found" });
        }

        const questData = getQuestFromCategorySync(category, quest_id) as BattleQuest | null;
        if (!questData || !("rankPointReward" in questData)) {
            return reply.status(400).send({ ok: false, error: "quest_not_found" });
        }

        const prerequisiteCheck = canStartQuestByPrerequisites(questData, (requiredQuestId) =>
            hasClearedQuestPrerequisiteForCategory(category, requiredQuestId, (section, id) =>
                getPlayerSingleQuestProgressSync(payload.playerId, section, id)
            )
        );
        if (!prerequisiteCheck.ok) {
            return reply.status(400).send({ ok: false, error: prerequisiteCheck.message });
        }

        // 扣除门票/道具
        const questKey = `${category}_${quest_id}`;
        const configuredEntryCost = (questEntryCosts as Record<string, { itemId: number; itemCount: number; stamina: number }>)[questKey];
        const staminaInfo = getStaminaCost(questKey);
        const entryCost = resolveBattleStartEntryCost(questData, configuredEntryCost);
        if (entryCost && entryCost.itemId > 0) {
            const playerItemCount = getPlayerItemSync(payload.playerId, entryCost.itemId) ?? 0;
            if (playerItemCount < entryCost.itemCount) {
                return reply.status(400).send({ ok: false, error: "insufficient_entry_items" });
            }
            updatePlayerItemSync(payload.playerId, entryCost.itemId, playerItemCount - entryCost.itemCount);
        }

        // 扣除体力
        const staminaCost = resolveBattleStartStaminaCost(questData, staminaInfo);
        let afterStamina = player.stamina;
        if (staminaCost > 0) {
            const currentStamina = computeRealTimeStamina(player);
            if (currentStamina < staminaCost) {
                return reply.status(400).send({ ok: false, error: "insufficient_stamina" });
            }
            const newStamina = Math.max(0, currentStamina - staminaCost);
            updatePlayerSync({ id: payload.playerId, stamina: newStamina, staminaHealTime: new Date(), totalStaminaUsed: (player.totalStaminaUsed ?? 0) + staminaCost });
            afterStamina = newStamina;
        }

        // 写 active quest（跨重启可恢复）
        insertPlayerActiveQuestSync(payload.playerId, {
            playerId: payload.playerId,
            playId: play_id,
            questId: quest_id,
            category,
            useBossBoostPoint: use_boss_boost_point,
            useBoostPoint: use_boost_point,
            isAutoStartMode: is_auto_start_mode,
            isMulti: false,
            roomNumber: null,
            entryItemId: entryCost?.itemId ?? null,
            eventId: questData.eventId ?? null,
            continueCount: 0,
        });

        if (questData.fixedParty === undefined) {
            updatePlayerSync({ id: payload.playerId, partySlot: party_id });
        }

        return reply.send({
            ok: true,
            stamina: afterStamina,
            stamina_heal_time: new Date().toISOString(),
        });
    });

    // ── POST /api/v2/battle/finish ─────────────────────────────────────────
    fastify.post("/battle/finish", async (request: FastifyRequest<{ Body: BattleFinishRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const body = request.body;
        const playerId = payload.playerId;

        // 解析 active quest（优先内存，回退到 DB 持久化）
        const dbActive = getPlayerActiveQuestSync(playerId);
        const activeQuestData = dbActive ?? null;
        if (!activeQuestData) {
            return reply.status(400).send({ ok: false, error: "no_active_quest" });
        }

        const questCategory = activeQuestData.category;
        const questId = activeQuestData.questId;
        const questData = getQuestFromCategorySync(questCategory, questId) as BattleQuest | null;
        if (!questData || !("rankPointReward" in questData)) {
            return reply.status(400).send({ ok: false, error: "quest_not_found" });
        }

        // 删除 active quest
        deletePlayerActiveQuestSync(playerId);

        const clearTime = body.elapsed_time_ms;
        const clearRank = calculateClearRank(clearTime, questData);
        const beforeRankPoint = (getPlayerSync(playerId) ?? { rankPoint: 0 }).rankPoint;
        const newRankPoint = beforeRankPoint + questData.rankPointReward;
        let newFreeMana = (getPlayerSync(playerId) ?? { freeMana: 0 }).freeMana + questData.manaReward + body.add_mana;
        const manaObtained = questData.manaReward + body.add_mana;
        const newExpPool = (getPlayerSync(playerId) ?? { expPool: 0 }).expPool + questData.poolExpReward;

        let newBoostPoint = (getPlayerSync(playerId) ?? { boostPoint: 0 }).boostPoint - (activeQuestData.useBoostPoint ? 1 : 0);
        let newBossBoostPoint = (getPlayerSync(playerId) ?? { bossBoostPoint: 0 }).bossBoostPoint - (activeQuestData.useBossBoostPoint ? 1 : 0);
        const useBoostPoint = (activeQuestData.useBoostPoint && newBoostPoint >= 0) || (activeQuestData.useBossBoostPoint && newBossBoostPoint >= 0);

        const questProgress = getPlayerSingleQuestProgressSync(playerId, questCategory, questId);
        const questPreviouslyCompleted = questProgress !== null;

        // Score attack 自动判定
        let questAccomplished = body.is_accomplished;
        if (questCategory === QuestCategory.SCORE_ATTACK_EVENT) {
            const eventId = questData.eventId;
            const folderId = questData.folderId;
            if (eventId !== undefined && folderId !== undefined) {
                const borderTiers = (scoreAttackBorderRewards as Record<string, { score: number }[]>)[`${eventId}_${folderId}`];
                if (borderTiers && borderTiers.length > 0) {
                    questAccomplished = body.score >= borderTiers[0].score;
                }
            }
        }

        const clearReward = !questPreviouslyCompleted && questData.clearReward !== undefined ? givePlayerRewardSync(playerId, questData.clearReward) : null;
        const sPlusClearReward = (clearRank === 5) && (questProgress?.clearRank !== 5) && (questData.sPlusReward !== undefined) ? givePlayerRewardSync(playerId, questData.sPlusReward) : null;

        if (questAccomplished) {
            const leaderId = body.statistics?.party?.characters?.[0]?.id ?? null;
            const updateData: any = {
                questId, finished: true,
                bestElapsedTimeMs: questProgress?.bestElapsedTimeMs === undefined || questProgress?.bestElapsedTimeMs === null ? clearTime : Math.min(clearTime, questProgress.bestElapsedTimeMs),
                highScore: questProgress?.highScore === undefined ? body.score : Math.max(body.score, questProgress.highScore),
                leaderCharacterId: leaderId,
            };
            if (clearRank !== null) {
                updateData.clearRank = questProgress?.clearRank === undefined ? clearRank : Math.max(clearRank, questProgress.clearRank);
            }
            if (questPreviouslyCompleted) {
                updatePlayerQuestProgressSync(playerId, questCategory, updateData);
            } else {
                insertPlayerQuestProgressSync(playerId, questCategory, { ...updateData });
            }
        }

        const oldRkDegree = getRankDegree(beforeRankPoint);
        const newDegreeId = getRankDegree(newRankPoint);
        const didLevelUp = newDegreeId > oldRkDegree;
        const refreshedPlayer = getPlayerSync(playerId)!;
        updatePlayerSync({
            id: playerId,
            freeMana: newFreeMana,
            expPool: newExpPool,
            rankPoint: newRankPoint,
            boostPoint: newBoostPoint,
            bossBoostPoint: newBossBoostPoint,
            totalManaObtained: (refreshedPlayer.totalManaObtained ?? 0) + manaObtained,
            maxComboAchieved: Math.max(refreshedPlayer.maxComboAchieved ?? 0, body.statistics?.max_combo_count ?? 0),
            ...(didLevelUp ? { stamina: refreshedPlayer.stamina + getMaxStamina(newDegreeId), staminaHealTime: new Date() } : {}),
        });
        const finalPlayer = getPlayerSync(playerId)!;
        if (didLevelUp) {
            finalPlayer.stamina = finalPlayer.stamina + getMaxStamina(newDegreeId);
            finalPlayer.staminaHealTime = new Date();
        }

        const scoreRewardsResult = givePlayerScoreRewardsSync(playerId, questData.scoreRewardGroupId ?? 0, questData.scoreRewardGroup, useBoostPoint, questData.element, {
            clearRank,
            rankItemCounts: questData.rankItemCounts,
        });

        const bodyPartyStatistics = body.statistics?.party ?? { characters: [], unison_characters: [] };
        const partyCharacterIdsArray: number[] = [];
        for (const value of [...(bodyPartyStatistics.characters as any[] ?? []), ...(bodyPartyStatistics.unison_characters as any[] ?? [])]) {
            if (value !== null && (value as any).id !== null && (value as any).id !== undefined) partyCharacterIdsArray.push((value as any).id);
        }

        const finishCtx: FinishContext = {
            playerId, questCategory, questId,
            questAccomplished,
            clearTime, clearRank,
            party: bodyPartyStatistics as any,
            statistics: body.statistics ?? {},
            player: finalPlayer,
            questPreviouslyCompleted,
            questProgress,
            isMulti: false,
        } as FinishContext;
        trackCharacterClears(finishCtx);
        trackLeaderPowerflip(finishCtx);
        trackPartyCoClears(finishCtx);
        trackPowerflip(finishCtx);
        const singleBattleParty = collectPartyCharacterIds(finishCtx.party);
        recordBattleMissionDimensionsSafe({
            type: "battle_finish",
            playerId,
            questCategory,
            questId,
            accomplished: questAccomplished,
            mode: "single",
            clearRank,
            clearTimeMs: clearTime,
            ...singleBattleParty,
            statistics: summarizeBattleStatistics(finishCtx.statistics),
        });

        const addExpAmount = questData.characterExpReward ?? 0;
        const rewardCharacterExpResult = givePlayerCharactersExpSync(playerId, partyCharacterIdsArray, addExpAmount, questData.fixedParty !== undefined);

        // event handlers
        const derivedFolderMaxRounds = getRushEventFolderMaxRounds(questData.rushEventId ?? 0);
        const { rushEventData, rushEventRewardsResult } = handleRushEventFinish({
            questCategory,
            questData: {
                rushEventId: questData.rushEventId,
                rushEventFolderId: questData.rushEventFolderId,
                rushEventRound: questData.rushEventRound,
            },
            clearTime,
            party: bodyPartyStatistics as any,
            playerId,
            questId,
            getEvoLevels: (_pid, _chars) => [],
            folderMaxRounds: derivedFolderMaxRounds,
            getRushEvent: (_pid, _eid) => null,
            updateRushEvent: () => undefined,
            insertParty: () => undefined,
            insertClearedFolder: () => undefined,
            deletePartyList: () => undefined,
            getSerializedParties: () => ({ folderParties: {}, endlessParties: {} }),
            getFolderRewards: (eid, fid) => getRushEventFolderClearRewards(eid, fid),
            giveRewards: (pid, r) => givePlayerRewardSync(pid, r[0]),
        });

        const rogueDrops = handleRoguePerRoundDrops({
            questCategory,
            questAccomplished,
            playerId,
            questData: {
                rushEventId: questData.rushEventId,
                rushEventFolderId: questData.rushEventFolderId,
                rushEventRound: questData.rushEventRound,
            },
            folderMaxRounds: derivedFolderMaxRounds,
            partyCharacterIds: partyCharacterIdsArray,
        });
        if (rogueDrops !== null && rushEventData !== null && rogueDrops.showInRewardList) {
            rushEventData.rush_battle_reward_list = [
                ...rushEventData.rush_battle_reward_list,
                ...rogueDrops.rewardListEntries,
            ];
        }

        handleRaidEventFinish({
            questCategory,
            activeEventId: activeQuestData.eventId as number | undefined,
            party: bodyPartyStatistics as any,
            playerId,
            questId,
            getEvoLevelsFn: (_pid, _chars) => [],
            insertPartyFn: () => undefined,
        });

        const carnivalLookup: Record<string, { difficulty_score: number; time_limit_ms: number; folder_id: number; event_id: number }> = {};
        handleCarnivalEventFinish({
            questCategory,
            questAccomplished,
            questId,
            clearTime,
            party: bodyPartyStatistics as any,
            playerId,
            carnivalLookup,
            upsertFn: () => undefined,
        });

        handleDailyChallengePoint({
            questCategory,
            eventId: questData.eventId,
            playerId,
            challengePointMap: eventChallengePointMap as Record<string, number>,
            getEntries: (pid) => getPlayerDailyChallengePointListSync(pid),
            updatePoint: (pid, id, pt) => updatePlayerDailyChallengePointSync(pid, id, pt),
        });

        // 计分事件额外 coin item
        let scoreAttackRewardIds: number[] = [];
        if (questCategory === QuestCategory.SCORE_ATTACK_EVENT && questData.eventId !== undefined && questData.folderId !== undefined) {
            const borderKey = `${questData.eventId}_${questData.folderId}`;
            const borderTiers = (scoreAttackBorderRewards as Record<string, { score: number; coinItemId: number; coinCount: number }[]>)[borderKey];
            if (borderTiers) {
                let matched: typeof borderTiers[0] | null = null;
                for (const tier of borderTiers) {
                    if (body.score >= tier.score) matched = tier;
                }
                if (matched && matched.coinItemId > 0 && matched.coinCount > 0) {
                    givePlayerItemSync(playerId, matched.coinItemId, matched.coinCount);
                    scoreRewardsResult.items[String(matched.coinItemId)] = (scoreRewardsResult.items[String(matched.coinItemId)] ?? 0) + matched.coinCount;
                    scoreAttackRewardIds.push(matched.coinItemId);
                }
            }
        }

        const itemList = {
            ...(activeQuestData.entryItemId ? { [String(activeQuestData.entryItemId)]: getPlayerItemSync(playerId, activeQuestData.entryItemId) ?? 0 } : {}),
            ...scoreRewardsResult.items,
            ...(rushEventRewardsResult?.items ?? {}),
            ...(rogueDrops?.rewardResult.items ?? {}),
        };

        const refreshPlayer = getPlayerSync(playerId)!;
        return reply.send({
            ok: true,
            clear_rank: clearRank ?? 5,
            new_rank_point: newRankPoint,
            new_free_vmoney: refreshPlayer.freeVmoney + (clearReward?.user_info.free_vmoney || 0) + (sPlusClearReward?.user_info.free_vmoney || 0) + scoreRewardsResult.user_info.free_vmoney,
            new_free_mana: newFreeMana + (clearReward?.user_info.free_mana || 0) + (sPlusClearReward?.user_info.free_mana || 0) + scoreRewardsResult.user_info.free_mana,
            new_exp_pool: (rogueDrops?.expPoolAbsolute ?? rewardCharacterExpResult.exp_pool) + (clearReward?.user_info.exp_pool || 0) + scoreRewardsResult.user_info.exp_pool,
            new_boost_point: newBoostPoint,
            new_boss_boost_point: newBossBoostPoint,
            new_stamina: refreshPlayer.stamina,
            new_stamina_heal_time: refreshPlayer.staminaHealTime.toISOString(),
            items: itemList,
            characters: [
                ...rewardCharacterExpResult.character_list,
                ...(clearReward?.character_list || []),
                ...(sPlusClearReward?.character_list || []),
                ...scoreRewardsResult.character_list,
                ...(rushEventRewardsResult?.character_list || []),
                ...(rogueDrops?.rewardResult.character_list || []),
                ...(rogueDrops?.expCharacterList || []),
            ],
            join_characters: [
                ...(clearReward?.joined_character_id_list || []),
                ...(sPlusClearReward?.joined_character_id_list || []),
                ...scoreRewardsResult.joined_character_id_list,
            ],
        });
    });

    // ── POST /api/v2/battle/abort ──────────────────────────────────────────
    fastify.post("/battle/abort", async (request: FastifyRequest<{ Body: BattleAbortRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const { quest_id, category } = request.body;
        if (isNaN(quest_id) || isNaN(category)) {
            return reply.status(400).send({ ok: false, error: "invalid_parameters" });
        }

        const activeQuest = getPlayerActiveQuestSync(payload.playerId);
        if (!activeQuest) {
            return reply.status(400).send({ ok: false, error: "no_active_quest" });
        }
        if (activeQuest.questId !== quest_id || activeQuest.category !== category) {
            return reply.status(400).send({ ok: false, error: "quest_mismatch" });
        }

        deletePlayerActiveQuestSync(payload.playerId);
        return reply.send({ ok: true });
    });

    // ── POST /api/v2/battle/play_continue ──────────────────────────────────
    fastify.post("/battle/play_continue", async (request: FastifyRequest<{ Body: BattleContinueRequest }>, reply: FastifyReply) => {
        const auth = request.headers.authorization;
        const payload = verifyJwt(auth, jwtSecret);
        if (!payload) {
            return reply.status(401).send({ ok: false, error: "unauthorized" });
        }

        const { quest_id, category } = request.body;
        if (isNaN(quest_id) || isNaN(category)) {
            return reply.status(400).send({ ok: false, error: "invalid_parameters" });
        }

        const activeQuest = getPlayerActiveQuestSync(payload.playerId);
        if (!activeQuest) {
            return reply.status(400).send({ ok: false, error: "no_active_quest" });
        }
        if (activeQuest.questId !== quest_id || activeQuest.category !== category) {
            return reply.status(400).send({ ok: false, error: "quest_mismatch" });
        }

        const questData = getQuestFromCategorySync(activeQuest.category, activeQuest.questId) as BattleQuest | null;
        if (!questData || !("rankPointReward" in questData)) {
            return reply.status(400).send({ ok: false, error: "quest_not_found" });
        }

        const continueCheck = canContinueBattle(questData, activeQuest.continueCount);
        if (!continueCheck.ok) {
            return reply.status(400).send({ ok: false, error: continueCheck.message });
        }

        const player = getPlayerSync(payload.playerId)!;
        const continueVmoneyCost = 50;
        const newFreeVmoney = Math.max(0, player.freeVmoney - continueVmoneyCost);
        const vmoney = player.vmoney;
        const newVmoney = newFreeVmoney === 0 ? Math.max(0, vmoney - continueVmoneyCost) : vmoney;
        if (newFreeVmoney < 0 && newVmoney < 0) {
            return reply.status(400).send({ ok: false, error: "insufficient_currency" });
        }

        const setNewFreeVmoney = newFreeVmoney === 0 ? 0 : newFreeVmoney;
        updatePlayerSync({ id: payload.playerId, freeVmoney: setNewFreeVmoney, vmoney: newVmoney });
        const newContinueCount = activeQuest.continueCount + 1;
        updatePlayerActiveQuestContinueCountSync(payload.playerId, newContinueCount);

        return reply.send({ ok: true, continue_count: newContinueCount, free_vmoney: setNewFreeVmoney, vmoney: newVmoney });
    });
};

export default routes;
