import { FastifyPluginAsync, FastifyRequest, FastifyReply } from "fastify";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import crypto from "crypto";
import { getDb } from "../../data/db";
import { getPlayerSync } from "../../data/domains/player";
import { RawAccount } from "../../data/types";

interface GameAuthRouteOptions {
    jwtSecret: string;
}

interface LoginRequestBody {
    username: string;
    password: string;
}

interface PlayerResponse {
    id: number;
    name: string;
    stamina: number;
    staminaHealTime: string;
    vmoney: number;
    freeVmoney: number;
    rankPoint: number;
    role: number;
    totalLoginDays: number;
    accountId: number;
}

interface LoginResponseBody {
    ok: boolean;
    token?: string;
    player?: PlayerResponse;
    error?: string;
}

interface SessionResponseBody {
    authenticated: boolean;
    accountId?: number;
    playerId?: number;
}

const LOGIN_FAILURE_LIMIT = 5;
const LOGIN_WINDOW_MS = 10 * 60 * 1000; // 10 minutes
const JWT_EXPIRES_IN = "7d";

class LoginFailureLimiter {
    private buckets = new Map<string, { count: number; resetAt: number }>();

    isLimited(ip: string, now: number): boolean {
        const current = this.buckets.get(ip);
        if (current && current.resetAt > now) {
            return current.count >= LOGIN_FAILURE_LIMIT;
        }
        if (current) this.buckets.delete(ip);
        return false;
    }

    recordFailure(ip: string, now: number): void {
        const current = this.buckets.get(ip);
        if (current) {
            current.count += 1;
            return;
        }
        this.buckets.set(ip, { count: 1, resetAt: now + LOGIN_WINDOW_MS });
    }

    clear(ip: string): void {
        this.buckets.delete(ip);
    }
}

const routes: FastifyPluginAsync<GameAuthRouteOptions> = async (fastify, options) => {
    const { jwtSecret } = options;

    if (!jwtSecret || jwtSecret.length < 32) {
        throw new Error("GAME_AUTH_JWT_SECRET must be at least 32 characters");
    }

    const failures = new LoginFailureLimiter();

    fastify.post("/login", async (request: FastifyRequest<{ Body: LoginRequestBody }>, reply: FastifyReply) => {
        reply.header("cache-control", "no-store");

        const { username, password } = request.body;
        if (!username || !password) {
            return reply.status(400).send({ ok: false, error: "missing_credentials" });
        }

        const now = Date.now();
        if (failures.isLimited(request.ip, now)) {
            return reply.status(429).send({ ok: false, error: "too_many_attempts" });
        }

        // 1. Query account by username
        const db = getDb();
        const rawAccount = db.prepare(`
            SELECT id, username, password_hash, status
            FROM accounts
            WHERE username = ?
        `).get(username) as (RawAccount & { password_hash: string | null }) | undefined;

        if (!rawAccount) {
            failures.recordFailure(request.ip, now);
            return reply.status(401).send({ ok: false, error: "invalid_credentials" });
        }

        // 2. Verify password (bcrypt > SHA256 > plaintext)
        let passwordValid = false;
        const hash = rawAccount.password_hash;

        if (hash) {
            // Try bcrypt first
            try {
                passwordValid = await bcrypt.compare(password, hash);
            } catch {
                passwordValid = false;
            }

            // Fallback to SHA256 (legacy format)
            if (!passwordValid) {
                const sha256 = crypto.createHash("sha256").update(password).digest("hex");
                passwordValid = sha256 === hash;

                // Upgrade to bcrypt if SHA256 matched
                if (passwordValid) {
                    const newHash = await bcrypt.hash(password, 10);
                    db.prepare(`UPDATE accounts SET password_hash = ? WHERE id = ?`).run(newHash, rawAccount.id);
                }
            }
        } else {
            // password_hash is NULL, allow test password
            passwordValid = password === "test";
        }

        if (!passwordValid) {
            failures.recordFailure(request.ip, now);
            return reply.status(401).send({ ok: false, error: "invalid_credentials" });
        }

        // 3. Check account status
        if (rawAccount.status !== "active") {
            return reply.status(403).send({ ok: false, error: "account_disabled" });
        }

        // 4. Get primary player (first one)
        const playerIdRow = db.prepare(`
            SELECT id FROM players WHERE account_id = ? ORDER BY id ASC LIMIT 1
        `).get(rawAccount.id) as { id: number } | undefined;

        if (!playerIdRow) {
            return reply.status(404).send({ ok: false, error: "no_player_found" });
        }

        // 5. Update last_login_time
        const nowISO = new Date().toISOString();
        db.prepare(`UPDATE accounts SET last_login_time = ? WHERE id = ?`).run(nowISO, rawAccount.id);
        db.prepare(`UPDATE players SET last_login_time = ? WHERE id = ?`).run(nowISO, playerIdRow.id);

        // 6. Generate JWT
        const player = getPlayerSync(playerIdRow.id);
        const token = jwt.sign(
            {
                accountId: rawAccount.id,
                playerId: playerIdRow.id,
                username: rawAccount.username,
            },
            jwtSecret,
            { expiresIn: JWT_EXPIRES_IN }
        );

        // 7. Clear failure count and return success
        failures.clear(request.ip);
        return reply.send({
            ok: true,
            token,
            player: player ?? {
                id: playerIdRow.id,
                name: "Unknown",
                stamina: 0,
                vmoney: 0,
                freeVmoney: 0,
                rankPoint: 0,
                accountId: rawAccount.id,
            },
        });
    });

    fastify.get("/session", async (request: FastifyRequest, reply: FastifyReply) => {
        reply.header("cache-control", "no-store");
        const auth = request.headers.authorization;
        if (!auth?.startsWith("Bearer ")) {
            return reply.send({ authenticated: false });
        }
        try {
            const payload = jwt.verify(auth.slice(7), jwtSecret) as {
                accountId: number;
                playerId: number;
            };
            return reply.send({
                authenticated: true,
                accountId: payload.accountId,
                playerId: payload.playerId,
            });
        } catch {
            return reply.send({ authenticated: false });
        }
    });
};

export default routes;
