import { FastifyPluginAsync, FastifyRequest, FastifyReply } from "fastify";
import jwt from "jsonwebtoken";
import { getDb } from "../../data/db";
import { getGachaSync } from "../../lib/assets";
import { drawGachaWithMetadataSync, rewardPlayerGachaDrawResultSync } from "../../lib/gacha";
import { getPlayerSync, updatePlayerSync } from "../../data/domains/player";
import { getPlayerCharactersSync } from "../../data/domains/character";
import { getPlayerActiveMissionsSync } from "../../data/domains/mission";
import { getGenericShopItemsSync } from "../../lib/assets";
import { ShopType } from "../../lib/types";

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
};

export default routes;
