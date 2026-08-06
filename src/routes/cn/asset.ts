import { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { generateDataHeaders } from "../../utils";
import { existsSync, lstatSync, readdirSync, statSync } from "fs";
import path from "path";
import { resolveCnCdnDir } from "../../lib/cn-character-release";
import type { DiffGroup } from "../../lib/cn-character-release";
import {
    findReleasePath,
    getCnReleaseGraphSnapshot,
    MAX_ARCHIVE_SEQ,
} from "../../lib/cn-asset-graph";
import type { ReleaseGraphSnapshot, ReleasePathResult } from "../../lib/cn-asset-graph";
import { computeAssetTarget } from "../../lib/version";

const CN_PORT = process.env.CN_LISTEN_PORT || "8001";
const CDN_BASE = process.env.CDN_BASE_URL;

/** Get CDN base URL from request Host header, fall back to CDN_BASE_URL env or default. */
function getCdnBase(request: FastifyRequest): string {
    if (CDN_BASE) return CDN_BASE;
    const host = request.headers.host || `localhost:${CN_PORT}`;
    return `http://${host}/patch/cn`;
}

/** Detect CDN path-list dir name: `EntityLists` (cn_cdn) or `entities` (cn_cdn_new). */
function entityListsDirName(): string {
    if (existsSync(path.join(cdnDir, "EntityLists"))) return "EntityLists";
    if (existsSync(path.join(cdnDir, "entities"))) return "entities";
    return "EntityLists";
}

function getVersionInfo(baseUrl: string) {
    const el = entityListsDirName();
    return {
        base_url: `${baseUrl}/${el}/`,
        files_list: `${baseUrl}/${el}/10939-android_medium.csv`,
        total_size: TOTAL_SIZE,
        delayed_assets_size: 0
    };
}

const FULL_ARCHIVE_RE = /^pinball-1\.4\.0-([1-9]\d*)-(.+)\.zip$/;
const FULL_ARCHIVE_SUBDIRS = new Set([
    "archive-common-full",
    "archive-medium-full",
    "archive-android-full",
]);

export function buildArchiveList(baseUrl: string, cdnDir: string, subdir: string): { location: string; size: number; sha256: string }[] {
    if (!FULL_ARCHIVE_SUBDIRS.has(subdir)) {
        console.error(`[CDN] rejecting full archive subdirectory: ${subdir}`);
        return [];
    }
    const resolvedCdnDir = path.resolve(cdnDir);
    const dir = path.resolve(resolvedCdnDir, subdir);
    if (path.dirname(dir) !== resolvedCdnDir) {
        console.error(`[CDN] rejecting full archive path outside CDN root: ${dir}`);
        return [];
    }
    try {
        const directoryStats = lstatSync(dir);
        if (directoryStats.isSymbolicLink() || !directoryStats.isDirectory()) {
            console.error(`[CDN] rejecting unsafe full archive directory: ${dir}`);
            return [];
        }
        return readdirSync(dir)
            .filter(name => name.endsWith(".zip"))
            .flatMap(name => {
                const match = FULL_ARCHIVE_RE.exec(name);
                if (match === null) {
                    console.error(`[CDN] skipping noncanonical full archive: ${path.join(dir, name)}`);
                    return [];
                }
                const seq = Number(match[1]);
                if (!Number.isSafeInteger(seq) || seq < 1 || seq > MAX_ARCHIVE_SEQ) {
                    console.error(
                        `[CDN] skipping full archive sequence outside 1..${MAX_ARCHIVE_SEQ}: ${path.join(dir, name)}`,
                    );
                    return [];
                }
                const archivePath = path.join(dir, name);
                const stats = lstatSync(archivePath);
                if (stats.isSymbolicLink() || !stats.isFile()) {
                    console.error(`[CDN] skipping unsafe full archive path: ${archivePath}`);
                    return [];
                }
                return {
                    name,
                    seq,
                    archive: {
                        location: `${baseUrl}/${subdir}/${name}`,
                        size: stats.size,
                        sha256: ""
                    },
                };
            })
            .sort((left, right) => left.seq - right.seq || left.name.localeCompare(right.name))
            .map(({ archive }) => archive);
    } catch (e) {
        console.error(`[CDN] buildArchiveList failed for ${subdir}:`, (e as Error).message);
        return [];
    }
}

export function buildDiffList(
    baseUrl: string,
    snapshot: ReleaseGraphSnapshot,
    releasePath: ReleasePathResult = findReleasePath(snapshot, snapshot.fullBase),
): DiffGroup[] {
    const normalizedBase = baseUrl.replace(/\/$/, "");
    return releasePath.edges.map(edge => ({
        original_version: edge.from,
        version: edge.to,
        archive: edge.archives.map(archive => ({
            location: `${normalizedBase}/${archive.relativePath}`,
            size: archive.size,
            sha256: archive.sha256,
        })),
    }));
}

const cdnDir = resolveCnCdnDir();

// 启动时扫描一次，动态计算总大小
const TOTAL_SIZE = (() => {
    let total = 0;
    for (const subdir of ["archive-common-full","archive-medium-full","archive-android-full","archive-common-diff","archive-medium-diff","archive-android-diff"]) {
        try {
            for (const f of readdirSync(path.join(cdnDir, subdir)).filter(f => f.endsWith(".zip")))
                total += statSync(path.join(cdnDir, subdir, f)).size;
        } catch (e) {
            console.error(`[CDN] TOTAL_SIZE failed for ${subdir}:`, (e as Error).message);
        }
    }
    return total;
})();

const routes = async (fastify: FastifyInstance) => {
    fastify.post("/version_info", async (request: FastifyRequest, reply: FastifyReply) => {
        const baseUrl = getCdnBase(request);
        reply.type("application/json");
        reply.status(200).send({
            data_headers: generateDataHeaders(),
            data: getVersionInfo(baseUrl)
        });
    });

    fastify.post("/get_path", async (request: FastifyRequest, reply: FastifyReply) => {
        const baseUrl = getCdnBase(request);
        const resVer = request.headers['res_ver'] as string | undefined;
        const snapshot = getCnReleaseGraphSnapshot();
        const {
            targetVersion,
            isFirstTime: first,
            fullVersion,
            path: selectedPath,
        } = computeAssetTarget(resVer, snapshot);

        const fullArchives = first
            ? [
                ...buildArchiveList(baseUrl, snapshot.cdnDir, "archive-common-full"),
                ...buildArchiveList(baseUrl, snapshot.cdnDir, "archive-medium-full"),
                ...buildArchiveList(baseUrl, snapshot.cdnDir, "archive-android-full"),
            ]
            : [];

        const diffArchives = buildDiffList(baseUrl, snapshot, selectedPath);

        reply.type("application/json");
        reply.status(200).send({
            data_headers: generateDataHeaders({ asset_update: true }),
            data: {
                info: {
                    client_asset_version: resVer ?? "",
                    target_asset_version: targetVersion,
                    eventual_target_asset_version: targetVersion,
                    is_initial: first,
                    latest_maj_first_version: "1.4.0"
                },
                full: {
                    version: fullVersion,
                    archive: fullArchives
                },
                diff: diffArchives,
                asset_version_hash: ""
            }
        });
    });
};

export default routes;

export const CDN_TOTAL_SIZE = TOTAL_SIZE;
export const ENTITY_LISTS_DIR = entityListsDirName();
