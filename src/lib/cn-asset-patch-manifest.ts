import { readFileSync } from "node:fs";
import path from "node:path";


const VERSION_RE = /^\d+\.\d+\.\d+$/;
const ARCHIVE_RE = /^pinball-(\d+\.\d+\.\d+)-(\d+\.\d+\.\d+)-([1-9]\d*)-(.+)\.zip$/;


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


export function readDeclaredPatchEdges(assetPatchRoot: string): DeclaredPatchEdges {
    const declared = new Map<string, Set<string>>();
    let value: unknown;
    try {
        value = JSON.parse(readFileSync(path.join(assetPatchRoot, "manifest.json"), "utf8"));
    } catch {
        return declared;
    }
    if (typeof value !== "object" || value === null || Array.isArray(value)) return declared;
    const patches = (value as { patches?: unknown }).patches;
    if (!Array.isArray(patches)) return declared;
    for (const patch of patches) {
        if (typeof patch !== "object" || patch === null || Array.isArray(patch)) continue;
        const item = patch as Record<string, unknown>;
        if (item.enabled !== true || item.type !== "patch") continue;
        const from = item.depends_on;
        const to = item.version;
        const chain = item.chain;
        if (
            typeof from !== "string"
            || typeof to !== "string"
            || !VERSION_RE.test(from)
            || !VERSION_RE.test(to)
            || !isIncreasingEdge(from, to)
            || !Array.isArray(chain)
            || chain.length === 0
        ) continue;
        const names = new Set<string>();
        let valid = true;
        for (const raw of chain) {
            if (
                typeof raw !== "string"
                || path.posix.basename(raw) !== raw
                || path.win32.basename(raw) !== raw
            ) {
                valid = false;
                break;
            }
            const match = ARCHIVE_RE.exec(raw);
            if (match === null || match[1] !== from || match[2] !== to) {
                valid = false;
                break;
            }
            names.add(raw);
        }
        if (!valid || names.size !== chain.length) continue;
        const key = declaredPatchEdgeKey(from, to);
        const existing = declared.get(key) ?? new Set<string>();
        for (const name of names) existing.add(name);
        declared.set(key, existing);
    }
    return declared;
}
