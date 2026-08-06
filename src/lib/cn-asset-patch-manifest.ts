import { readFileSync } from "node:fs";
import path from "node:path";


const VERSION_RE = /^\d+\.\d+\.\d+$/;
const TOKEN_RE = /^[a-z0-9][a-z0-9_-]*$/;
const ARCHIVE_RE = /^pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-([1-9]\d*)-(.+)\.zip$/;
const SHA256_RE = /^[0-9a-f]{64}$/;


export interface DeclaredPatchArchiveIntegrity {
    size: number;
    sha256: string;
}


export interface DeclaredPatchArchive {
    name: string;
    from: string;
    to: string;
    seq: number;
    integrity?: DeclaredPatchArchiveIntegrity;
}

export interface DeclaredPatchEntry {
    id: string;
    archives: readonly DeclaredPatchArchive[];
}

export interface DeclaredPatchManifest {
    entries: readonly DeclaredPatchEntry[];
    issues: readonly string[];
}

export type DeclaredPatchEdges = ReadonlyMap<string, ReadonlySet<string>>;


export function declaredPatchEdgeKey(from: string, to: string): string {
    return `${from}\u0000${to}`;
}


function versionParts(value: string): number[] {
    return value.split(".").map(Number);
}


function isIncreasingEdge(from: string, to: string): boolean {
    const left = versionParts(from);
    const right = versionParts(to);
    return right.some((part, index) => (
        part > left[index]
        && right.slice(0, index).every((prior, priorIndex) => prior === left[priorIndex])
    ));
}


function issue(message: string): DeclaredPatchManifest {
    return { entries: [], issues: [message] };
}


export function readDeclaredPatchManifest(assetPatchRoot: string): DeclaredPatchManifest {
    let value: unknown;
    try {
        value = JSON.parse(readFileSync(path.join(assetPatchRoot, "manifest.json"), "utf8"));
    } catch (error) {
        return issue(`asset-patch manifest is unreadable or invalid JSON: ${(error as Error).message}`);
    }
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
        return issue("asset-patch manifest must be an object");
    }
    const manifest = value as Record<string, unknown>;
    if (typeof manifest.cdn_version !== "string" || !VERSION_RE.test(manifest.cdn_version)) {
        return issue("asset-patch manifest cdn_version is invalid");
    }
    if (!Array.isArray(manifest.patches)) {
        return issue("asset-patch manifest patches must be an array");
    }

    const entries: DeclaredPatchEntry[] = [];
    const issues: string[] = [];
    const ids = new Set<string>();
    const edgeOwners = new Map<string, string>();
    for (const [index, rawPatch] of manifest.patches.entries()) {
        if (typeof rawPatch !== "object" || rawPatch === null || Array.isArray(rawPatch)) {
            issues.push(`asset-patch manifest patch ${index} must be an object`);
            continue;
        }
        const patch = rawPatch as Record<string, unknown>;
        if (patch.enabled !== true) continue;
        const id = patch.id;
        if (typeof id !== "string" || !TOKEN_RE.test(id)) {
            issues.push(`asset-patch manifest patch ${index} has invalid id`);
            continue;
        }
        if (ids.has(id)) {
            issues.push(`asset-patch manifest has duplicate patch id: ${id}`);
            continue;
        }
        ids.add(id);
        if (patch.type !== "patch") {
            issues.push(`asset-patch manifest patch ${id} has invalid type`);
            continue;
        }
        const from = patch.depends_on;
        const to = patch.version;
        const chain = patch.chain;
        if (
            typeof from !== "string"
            || typeof to !== "string"
            || !VERSION_RE.test(from)
            || !VERSION_RE.test(to)
            || !isIncreasingEdge(from, to)
            || !Array.isArray(chain)
            || chain.length === 0
        ) {
            issues.push(`asset-patch manifest patch ${id} has invalid edge or chain`);
            continue;
        }

        const archives: DeclaredPatchArchive[] = [];
        const names = new Set<string>();
        let malformed = false;
        for (const rawName of chain) {
            if (
                typeof rawName !== "string"
                || path.posix.basename(rawName) !== rawName
                || path.win32.basename(rawName) !== rawName
                || names.has(rawName)
            ) {
                malformed = true;
                break;
            }
            const match = ARCHIVE_RE.exec(rawName);
            const seq = match === null ? NaN : Number(match[3]);
            if (match === null || !Number.isSafeInteger(seq)) {
                malformed = true;
                break;
            }
            names.add(rawName);
            archives.push({ name: rawName, from: match[1], to: match[2], seq });
        }
        if (malformed) {
            issues.push(`asset-patch manifest patch ${id} has invalid archive names`);
            continue;
        }

        const rawIntegrity = patch.archive_integrity;
        if (rawIntegrity !== undefined) {
            if (!Array.isArray(rawIntegrity) || rawIntegrity.length !== archives.length) {
                issues.push(
                    `asset-patch manifest patch ${id} archive_integrity must exactly cover chain`,
                );
                continue;
            }
            for (const [archiveIndex, rawItem] of rawIntegrity.entries()) {
                if (typeof rawItem !== "object" || rawItem === null || Array.isArray(rawItem)) {
                    malformed = true;
                    break;
                }
                const integrity = rawItem as Record<string, unknown>;
                const size = integrity.size;
                const sha256 = integrity.sha256;
                if (
                    integrity.name !== archives[archiveIndex].name
                    || typeof size !== "number"
                    || !Number.isSafeInteger(size)
                    || size <= 0
                    || typeof sha256 !== "string"
                    || !SHA256_RE.test(sha256)
                ) {
                    malformed = true;
                    break;
                }
                archives[archiveIndex] = {
                    ...archives[archiveIndex],
                    integrity: { size, sha256 },
                };
            }
            if (malformed) {
                issues.push(
                    `asset-patch manifest patch ${id} has invalid archive_integrity`,
                );
                continue;
            }
        }

        const edgeOrder: string[] = [];
        const byEdge = new Map<string, DeclaredPatchArchive[]>();
        for (const archive of archives) {
            if (!isIncreasingEdge(archive.from, archive.to)) {
                malformed = true;
                break;
            }
            const key = declaredPatchEdgeKey(archive.from, archive.to);
            if (!byEdge.has(key)) edgeOrder.push(key);
            const grouped = byEdge.get(key) ?? [];
            grouped.push(archive);
            byEdge.set(key, grouped);
        }
        for (const grouped of byEdge.values()) {
            const sequences = grouped.map(archive => archive.seq).sort((left, right) => left - right);
            if (sequences.some((sequence, sequenceIndex) => sequence !== sequenceIndex + 1)) {
                malformed = true;
                issues.push(`asset-patch manifest patch ${id} archive sequence is not contiguous`);
                break;
            }
        }
        const orderedEdges = edgeOrder.map(key => byEdge.get(key)![0]);
        if (
            malformed
            || orderedEdges.length === 0
            || orderedEdges[0].from !== from
            || orderedEdges[orderedEdges.length - 1].to !== to
            || orderedEdges.some((edge, edgeIndex) => (
                edgeIndex > 0 && orderedEdges[edgeIndex - 1].to !== edge.from
            ))
        ) {
            if (!issues.some(item => item.includes(`patch ${id} archive sequence`))) {
                issues.push(`asset-patch manifest patch ${id} chain is disconnected from its edge`);
            }
            continue;
        }
        for (const edge of orderedEdges) {
            const key = declaredPatchEdgeKey(edge.from, edge.to);
            const owner = edgeOwners.get(key);
            if (owner !== undefined) {
                issues.push(
                    `asset-patch manifest has duplicate edge ${edge.from}->${edge.to}: ${owner}, ${id}`,
                );
            } else {
                edgeOwners.set(key, id);
            }
        }
        entries.push({ id, archives });
    }

    return issues.length > 0
        ? { entries: [], issues: [...new Set(issues)] }
        : { entries, issues: [] };
}
