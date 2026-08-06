import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import {
    mkdtempSync,
    mkdirSync,
    readFileSync,
    rmSync,
    unlinkSync,
    writeFileSync,
} from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { Open } from "unzipper";

import {
    buildReleaseGraph,
    findReleasePath,
    getCnReleaseGraphSnapshot,
    resetCnReleaseGraphCache,
} from "../lib/cn-asset-graph";
import type { ReleaseGraphSnapshot } from "../lib/cn-asset-graph";
import { computeAssetTarget } from "../lib/version";
import { buildDiffList } from "../routes/cn/asset";


const DIFF_DIRS = {
    common: "archive-common-diff",
    medium: "archive-medium-diff",
    android: "archive-android-diff",
} as const;


function sha256(raw: Buffer): string {
    return createHash("sha256").update(raw).digest("hex");
}


function crc32(raw: Buffer): number {
    let checksum = 0xffffffff;
    for (const byte of raw) {
        checksum ^= byte;
        for (let bit = 0; bit < 8; bit += 1) {
            checksum = (checksum >>> 1) ^ (checksum & 1 ? 0xedb88320 : 0);
        }
    }
    return (checksum ^ 0xffffffff) >>> 0;
}


function storedZip(member: string, payload: string): Buffer {
    const name = Buffer.from(member);
    const raw = Buffer.from(payload);
    const checksum = crc32(raw);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8);
    local.writeUInt16LE(0, 10);
    local.writeUInt16LE(0x21, 12);
    local.writeUInt32LE(checksum, 14);
    local.writeUInt32LE(raw.length, 18);
    local.writeUInt32LE(raw.length, 22);
    local.writeUInt16LE(name.length, 26);
    local.writeUInt16LE(0, 28);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(0, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0x21, 14);
    central.writeUInt32LE(checksum, 16);
    central.writeUInt32LE(raw.length, 20);
    central.writeUInt32LE(raw.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt16LE(0, 30);
    central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34);
    central.writeUInt16LE(0, 36);
    central.writeUInt32LE(0, 38);
    central.writeUInt32LE(0, 42);

    const centralSize = central.length + name.length;
    const centralOffset = local.length + name.length + raw.length;
    const end = Buffer.alloc(22);
    end.writeUInt32LE(0x06054b50, 0);
    end.writeUInt16LE(0, 4);
    end.writeUInt16LE(0, 6);
    end.writeUInt16LE(1, 8);
    end.writeUInt16LE(1, 10);
    end.writeUInt32LE(centralSize, 12);
    end.writeUInt32LE(centralOffset, 16);
    end.writeUInt16LE(0, 20);
    return Buffer.concat([local, name, raw, central, name, end]);
}


interface GraphFixture {
    root: string;
    cdnDir: string;
    assetPatchRoot: string;
    activeManifest: string;
    cleanup(): void;
}


function fixture(): GraphFixture {
    const root = mkdtempSync(path.join(os.tmpdir(), "wf-release-graph-"));
    const cdnDir = path.join(root, "cdn");
    const assetPatchRoot = path.join(root, "asset-patch");
    for (const directory of Object.values(DIFF_DIRS)) {
        mkdirSync(path.join(cdnDir, directory), { recursive: true });
    }
    mkdirSync(path.join(cdnDir, "character-releases"), { recursive: true });
    mkdirSync(path.join(assetPatchRoot, "active"), { recursive: true });
    return {
        root,
        cdnDir,
        assetPatchRoot,
        activeManifest: path.join(cdnDir, "character-releases", "active.json"),
        cleanup() {
            const resolved = path.resolve(root);
            const temp = path.resolve(os.tmpdir());
            assert.ok(resolved.startsWith(`${temp}${path.sep}`));
            assert.ok(path.basename(resolved).startsWith("wf-release-graph-"));
            rmSync(resolved, { recursive: true, force: true });
        },
    };
}


function writeLegacy(
    f: GraphFixture,
    from: string,
    to: string,
    root: keyof typeof DIFF_DIRS = "common",
    label = "fixture",
): string {
    const name = `pinball-${from}-${to}-1-${label}.zip`;
    writeFileSync(path.join(f.cdnDir, DIFF_DIRS[root], name), Buffer.from(`${root}:${from}:${to}:${label}`));
    return name;
}


function writeSequencedLegacy(
    f: GraphFixture,
    from: string,
    to: string,
    root: keyof typeof DIFF_DIRS,
    seq: number,
    label: string,
    member: string,
    payload: string,
): string {
    const name = `pinball-${from}-${to}-${seq}-${label}.zip`;
    writeFileSync(path.join(f.cdnDir, DIFF_DIRS[root], name), storedZip(member, payload));
    return name;
}


async function replayLegacyArchives(
    f: GraphFixture,
    locations: string[],
): Promise<Map<string, string>> {
    const baseUrl = "https://fixture.invalid/";
    const final = new Map<string, string>();
    for (const location of locations) {
        assert.ok(location.startsWith(baseUrl));
        const relative = location.slice(baseUrl.length);
        const archive = await Open.buffer(
            readFileSync(path.join(f.cdnDir, ...relative.split("/"))),
        );
        for (const entry of archive.files) {
            if (entry.type !== "File") continue;
            final.set(entry.path, (await entry.buffer()).toString());
        }
    }
    return final;
}


function writePatch(f: GraphFixture, from: string, to: string, label = "patch"): string {
    const name = `pinball-${from}-${to}-1-${label}.zip`;
    writeFileSync(path.join(f.assetPatchRoot, "active", name), Buffer.from(`patch:${from}:${to}:${label}`));
    return name;
}


interface CharacterOptions {
    corruptRelease?: number;
    missingRelease?: number;
    missingRoot?: keyof typeof DIFF_DIRS;
}


function writeCharacterChain(
    f: GraphFixture,
    basePatch: number,
    tailPatch: number,
    options: CharacterOptions = {},
): void {
    const releases: any[] = [];
    for (let patchValue = basePatch; patchValue < tailPatch; patchValue += 1) {
        const from = `1.4.${patchValue}`;
        const to = `1.4.${patchValue + 1}`;
        const releaseIndex = patchValue - basePatch;
        const releaseId = `release-${releaseIndex + 1}`;
        const archives = (Object.keys(DIFF_DIRS) as Array<keyof typeof DIFF_DIRS>).map(root => {
            const relative = `${DIFF_DIRS[root]}/pinball-${from}-${to}-1-charpkg-fixture-${releaseId}-${root}.zip`;
            const raw = Buffer.from(`character:${releaseIndex}:${root}`);
            const disk = path.join(f.cdnDir, ...relative.split("/"));
            writeFileSync(disk, raw);
            if (options.missingRelease === releaseIndex && options.missingRoot === root) unlinkSync(disk);
            return {
                root,
                relative_path: relative,
                size: raw.length,
                sha256: options.corruptRelease === releaseIndex && root === "medium"
                    ? "0".repeat(64)
                    : sha256(raw),
            };
        });
        releases.push({
            release_id: releaseId,
            package_id: "fixture",
            from_version: from,
            version: to,
            package_manifest_sha256: `${releaseIndex + 1}`.repeat(64),
            archives,
        });
    }
    writeFileSync(f.activeManifest, JSON.stringify({
        schema_version: 1,
        base_version: `1.4.${basePatch}`,
        releases,
    }));
}


function build(
    f: GraphFixture,
    fullBase: string,
    supportedBases: string[] = [fullBase],
): ReleaseGraphSnapshot {
    return buildReleaseGraph({
        cdnDir: f.cdnDir,
        assetPatchRoot: f.assetPatchRoot,
        fullBase,
        supportedBases,
    });
}


test("archive replay uses root, numeric sequence, and relative path order", async () => {
    const f = fixture();
    const from = "1.4.106";
    const to = "1.4.107";
    try {
        for (const seq of [1, 2, 9, 10, 11]) {
            writeSequencedLegacy(
                f, from, to, "common", seq, "numeric",
                "shared-sequence.bin", `seq-${seq}`,
            );
        }
        writeSequencedLegacy(
            f, from, to, "common", 9, "relative-a",
            "relative-tie.bin", "relative-a",
        );
        writeSequencedLegacy(
            f, from, to, "common", 9, "relative-z",
            "relative-tie.bin", "relative-z",
        );
        writeSequencedLegacy(
            f, from, to, "common", 11, "root-common",
            "root-tie.bin", "common-seq-11",
        );
        writeSequencedLegacy(
            f, from, to, "medium", 1, "root-medium",
            "root-tie.bin", "medium-seq-1",
        );
        const graph = build(f, from);
        const edge = graph.edges.find(item => item.from === from && item.to === to);
        assert.ok(edge);
        assert.deepEqual(
            edge.archives
                .filter(archive => archive.relativePath.endsWith("-numeric.zip"))
                .map(archive => archive.seq),
            [1, 2, 9, 10, 11],
        );

        const groups = buildDiffList("https://fixture.invalid", graph);
        assert.equal(groups.length, 1);
        const final = await replayLegacyArchives(
            f,
            groups[0].archive.map(archive => archive.location),
        );
        assert.equal(final.get("shared-sequence.bin"), "seq-11");
        assert.equal(final.get("relative-tie.bin"), "relative-z");
        assert.equal(final.get("root-tie.bin"), "medium-seq-1");
    } finally {
        f.cleanup();
    }
});


test("archive sequence accepts Number.MAX_SAFE_INTEGER and rejects the next value", () => {
    const f = fixture();
    const from = "1.4.107";
    const to = "1.4.217";
    const maxSeq = 9_007_199_254_740_991;
    try {
        writeSequencedLegacy(
            f, from, to, "common", maxSeq, "max",
            "max.bin", "max",
        );
        writeSequencedLegacy(
            f, from, to, "common", maxSeq + 1, "overflow",
            "overflow.bin", "overflow",
        );

        const graph = build(f, from);
        const edge = graph.edges.find(item => item.from === from && item.to === to);
        assert.ok(edge);
        assert.deepEqual(edge.archives.map(archive => archive.seq), [maxSeq]);
        assert.match(graph.issues.join("\n"), /sequence.*9007199254740992/);
    } finally {
        f.cleanup();
    }
});


test("archive ordering keeps source as the final stable tie-breaker", () => {
    const f = fixture();
    const from = "1.4.107";
    const to = "1.4.108";
    try {
        const name = writeSequencedLegacy(
            f, from, to, "common", 1, "source-tie",
            "source.bin", "same-archive",
        );
        const relativePath = `${DIFF_DIRS.common}/${name}`;
        const graph = buildReleaseGraph({
            cdnDir: f.cdnDir,
            assetPatchRoot: f.assetPatchRoot,
            fullBase: from,
            supportedBases: [from],
            characterChain: {
                baseVersion: from,
                tailVersion: to,
                error: null,
                releases: [{
                    release_id: "source-a",
                    package_id: "fixture",
                    from_version: from,
                    version: to,
                    package_manifest_sha256: "0".repeat(64),
                    archives: [{
                        root: "common",
                        relative_path: relativePath,
                        size: 1,
                        sha256: "0".repeat(64),
                    }],
                }],
            },
        });
        const edge = graph.edges.find(item => item.from === from && item.to === to);
        assert.ok(edge);
        const tied = edge.archives.filter(archive => archive.relativePath === relativePath);
        assert.deepEqual(tied.map(archive => ({
            root: archive.root,
            seq: archive.seq,
            relativePath: archive.relativePath,
            source: archive.source,
        })), [
            { root: "common", seq: 1, relativePath, source: "character:source-a" },
            { root: "common", seq: 1, relativePath, source: "legacy:common" },
        ]);
    } finally {
        f.cleanup();
    }
});


test("character chain may attach at a reachable earlier node and merge four roots", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.102", "1.4.133");
        writeLegacy(f, "1.4.138", "1.4.139");
        writePatch(f, "1.4.138", "1.4.139");
        writeCharacterChain(f, 133, 140);
        const graph = build(f, "1.4.102", ["1.4.102", "1.4.133"]);
        const result = findReleasePath(graph, "1.4.102");
        assert.equal(result.targetVersion, "1.4.140");
        assert.deepEqual(result.edges.map(edge => `${edge.from}->${edge.to}`), [
            "1.4.102->1.4.133",
            "1.4.133->1.4.134",
            "1.4.134->1.4.135",
            "1.4.135->1.4.136",
            "1.4.136->1.4.137",
            "1.4.137->1.4.138",
            "1.4.138->1.4.139",
            "1.4.139->1.4.140",
        ]);
        const merged = graph.edges.find(edge => edge.from === "1.4.138" && edge.to === "1.4.139");
        assert.ok(merged);
        assert.deepEqual(
            new Set(merged.archives.map(archive => archive.root)),
            new Set(["common", "medium", "android", "patch"]),
        );
        assert.equal(graph.issues.length, 0);
        assert.ok(graph.supported.every(item => item.reachable));
    } finally {
        f.cleanup();
    }
});


for (const failure of ["corrupt", "missing"] as const) {
    test(`${failure} character archive truncates the manifest chain`, () => {
        const f = fixture();
        try {
            writeCharacterChain(f, 133, 135, failure === "corrupt"
                ? { corruptRelease: 0 }
                : { missingRelease: 0, missingRoot: "android" });
            const graph = build(f, "1.4.133");
            assert.equal(graph.tailVersion, "1.4.133");
            assert.equal(graph.edges.length, 0);
            assert.match(graph.issues.join("\n"), failure === "corrupt" ? /hash\/size mismatch/ : /missing/);
        } finally {
            f.cleanup();
        }
    });
}


test("backward cycle edge is rejected", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.0", "1.4.1");
        writeLegacy(f, "1.4.1", "1.4.0", "common", "cycle");
        const graph = build(f, "1.4.0");
        assert.equal(graph.edges.length, 1);
        assert.match(graph.issues.join("\n"), /backward|cycle|non-increasing/);
    } finally {
        f.cleanup();
    }
});


test("isolated high version is reported without becoming the tail", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.0", "1.4.1");
        writeLegacy(f, "9.0.0", "9.0.1", "common", "isolated");
        const graph = build(f, "1.4.0");
        assert.equal(graph.tailVersion, "1.4.1");
        assert.match(graph.issues.join("\n"), /isolated|unreachable/);
        assert.equal(findReleasePath(graph, "1.4.0").targetVersion, "1.4.1");
    } finally {
        f.cleanup();
    }
});


test("path selection is shortest and deterministic for the highest target", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.0", "1.4.1", "common", "a");
        writeLegacy(f, "1.4.0", "1.4.2", "common", "b");
        writeLegacy(f, "1.4.1", "1.4.5", "common", "c");
        writeLegacy(f, "1.4.2", "1.4.5", "common", "d");
        let graph = build(f, "1.4.0");
        assert.deepEqual(
            findReleasePath(graph, "1.4.0").edges.map(edge => edge.to),
            ["1.4.1", "1.4.5"],
        );

        writeLegacy(f, "1.4.0", "1.4.5", "common", "direct");
        graph = build(f, "1.4.0");
        assert.deepEqual(
            findReleasePath(graph, "1.4.0").edges.map(edge => edge.to),
            ["1.4.5"],
        );
    } finally {
        f.cleanup();
    }
});


test("every declared supported base is evaluated against the canonical tail", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.0", "1.4.1");
        writeLegacy(f, "1.4.1", "1.4.2");
        const graph = build(f, "1.4.0", ["1.4.0", "1.4.1", "1.4.2"]);
        assert.equal(graph.tailVersion, "1.4.2");
        assert.deepEqual(graph.supported.map(item => ({
            base: item.baseVersion,
            target: item.targetVersion,
            reachable: item.reachable,
        })), [
            { base: "1.4.0", target: "1.4.2", reachable: true },
            { base: "1.4.1", target: "1.4.2", reachable: true },
            { base: "1.4.2", target: "1.4.2", reachable: true },
        ]);
    } finally {
        f.cleanup();
    }
});


test("load and get_path choose the same reachable target from an injected snapshot", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.102", "1.4.133");
        writePatch(f, "1.4.138", "1.4.139", "fixture-active");
        writeCharacterChain(f, 133, 140);
        const graph = build(f, "1.4.102", ["1.4.102", "1.4.133"]);

        const target = computeAssetTarget("1.4.102", graph);
        assert.equal(target.targetVersion, "1.4.140");
        assert.deepEqual(target.path.edges.map(edge => edge.to), [
            "1.4.133",
            "1.4.134",
            "1.4.135",
            "1.4.136",
            "1.4.137",
            "1.4.138",
            "1.4.139",
            "1.4.140",
        ]);

        const groups = buildDiffList("http://cdn", graph);
        assert.deepEqual(groups.map(group => group.version), target.path.edges.map(edge => edge.to));
        assert.ok(groups.flatMap(group => group.archive).some(archive => (
            archive.location.includes("/asset-patch/active/")
            && archive.location.includes("fixture-active")
        )));
        assert.ok(groups.flatMap(group => group.archive).every(archive => (
            archive.location.startsWith("http://cdn/")
        )));
    } finally {
        f.cleanup();
    }
});


test("a disconnected client keeps its current version and receives no diff path", () => {
    const f = fixture();
    try {
        writeLegacy(f, "1.4.102", "1.4.133");
        writeCharacterChain(f, 133, 140);
        const graph = build(f, "1.4.102");

        const target = computeAssetTarget("1.4.120", graph);
        assert.equal(target.isFirstTime, false);
        assert.equal(target.fullVersion, "1.4.120");
        assert.equal(target.targetVersion, "1.4.120");
        assert.deepEqual(target.path.edges, []);
        assert.deepEqual(buildDiffList("http://cdn", graph, target.path), []);
    } finally {
        f.cleanup();
    }
});


// 2026-07-18 链重锚事故回归:base_version 抬高后,被 active.json 丢弃的
// charpkg 历史边因文件名过滤从 graph 消失,停在中间版本的客户端塌回"已最新"。
// charbridge 命名的硬链接副本(非 charpkg)必须能把老客户端重新接回 tail。
test("re-anchored chain strands old clients until charbridge copies restore the path", () => {
    const f = fixture();
    const roots = Object.keys(DIFF_DIRS) as Array<keyof typeof DIFF_DIRS>;
    const writeHistory = (label: string): void => {
        for (let patch = 133; patch < 140; patch += 1) {
            for (const root of roots) {
                writeLegacy(f, `1.4.${patch}`, `1.4.${patch + 1}`, root, `${label}-old-${root}`);
            }
        }
    };
    try {
        writeLegacy(f, "1.4.0", "1.4.133");
        writeLegacy(f, "1.4.140", "1.4.141");
        writeHistory("charpkg-fixture");
        writeCharacterChain(f, 141, 143);

        const stranded = build(f, "1.4.0");
        assert.equal(stranded.tailVersion, "1.4.133");
        assert.equal(findReleasePath(stranded, "1.4.136").targetVersion, "1.4.136");
        assert.match(
            stranded.issues.join("\n"),
            /character release base is unreachable: 1\.4\.141/,
        );

        writeHistory("charbridge-fixture");
        const bridged = build(f, "1.4.0");
        assert.equal(bridged.tailVersion, "1.4.143");
        assert.deepEqual(bridged.issues, []);
        assert.equal(findReleasePath(bridged, "1.4.133").targetVersion, "1.4.143");
        assert.equal(findReleasePath(bridged, "1.4.136").targetVersion, "1.4.143");
        assert.equal(computeAssetTarget("1.4.136", bridged).targetVersion, "1.4.143");
    } finally {
        f.cleanup();
    }
});


test("cached snapshots invalidate when a diff directory changes", () => {
    const f = fixture();
    resetCnReleaseGraphCache();
    try {
        writeLegacy(f, "1.4.0", "1.4.1");
        const options = {
            cdnDir: f.cdnDir,
            assetPatchRoot: f.assetPatchRoot,
            fullBase: "1.4.0",
            supportedBases: ["1.4.0"],
        };
        const first = getCnReleaseGraphSnapshot(options);
        const cached = getCnReleaseGraphSnapshot(options);
        assert.equal(cached, first);
        assert.equal(first.tailVersion, "1.4.1");
        assert.ok(Object.isFrozen(first));
        assert.ok(Object.isFrozen(first.edges));

        writeLegacy(f, "1.4.1", "1.4.2", "medium", "cache-invalidation");
        const rebuilt = getCnReleaseGraphSnapshot(options);
        assert.notEqual(rebuilt, first);
        assert.equal(rebuilt.tailVersion, "1.4.2");
    } finally {
        resetCnReleaseGraphCache();
        f.cleanup();
    }
});
