import { FastifyPluginAsync } from "fastify";

import { AdminAuthConfig } from "../../lib/admin-auth";
import adminAuthApiPlugin from "./admin-auth";
import playerApiPlugin from "./player";
import serverApiPlugin from "./server";
import mailApiPlugin from "./mail";
import lookupApiPlugin from "./lookup";
import gameAuthApiPlugin from "./game-auth";
import gameV2ApiPlugin from "./game-v2";


interface WebApiRouteOptions {
    adminAuthConfig: AdminAuthConfig;
    gameAuthJwtSecret: string;
}

const routes: FastifyPluginAsync<WebApiRouteOptions> = async (fastify, options) => {
    fastify.register(adminAuthApiPlugin, {
        prefix: "/admin-auth",
        config: options.adminAuthConfig,
    });
    fastify.register(require('@fastify/multipart'), {
        limits: {
            fieldNameSize: 100, // Max field name size in bytes
            fieldSize: 100,     // Max field value size in bytes
            fields: 10,         // Max number of non-file fields
            fileSize: 5000000,  // For multipart forms, the max file size in bytes
            files: 1,           // Max number of file fields
            headerPairs: 2000,  // Max number of header key=>value pairs
            parts: 1000         // For multipart forms, the max number of parts (fields + files)
        }
    });

    fastify.register(playerApiPlugin, { prefix: "/player" });
    fastify.register(serverApiPlugin, { prefix: "/server" });
    fastify.register(mailApiPlugin, { prefix: "/mail" });
    fastify.register(lookupApiPlugin, { prefix: "/lookup" });
    fastify.register(gameAuthApiPlugin, {
        prefix: "/v2/game",
        jwtSecret: options.gameAuthJwtSecret,
    });
    fastify.register(gameV2ApiPlugin, {
        prefix: "/v2",
        jwtSecret: options.gameAuthJwtSecret,
    });
};

export default routes;
