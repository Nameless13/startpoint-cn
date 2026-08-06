import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { buildArchiveList } from "../routes/cn/asset";


const FULL_ROOTS = ["common", "medium", "android"] as const;


function fullFixture(): { root: string; cleanup(): void } {
    const workspace = mkdtempSync(path.join(os.tmpdir(), "wf-full-archive-order-"));
    const root = path.join(workspace, "cdn");
    mkdirSync(root);
    for (const archiveRoot of FULL_ROOTS) {
        mkdirSync(path.join(root, `archive-${archiveRoot}-full`));
    }
    return {
        root,
        cleanup() {
            const resolved = path.resolve(workspace);
            const temp = path.resolve(os.tmpdir());
            assert.ok(resolved.startsWith(`${temp}${path.sep}`));
            assert.ok(path.basename(resolved).startsWith("wf-full-archive-order-"));
            rmSync(resolved, { recursive: true, force: true });
        },
    };
}


function writeFull(root: string, archiveRoot: typeof FULL_ROOTS[number], seq: string): void {
    const directory = path.join(root, `archive-${archiveRoot}-full`);
    writeFileSync(path.join(directory, `pinball-1.4.0-${seq}-fixture.zip`), `seq-${seq}`);
}


test("full archive lists keep roots grouped and sequences numeric", () => {
    const f = fullFixture();
    try {
        for (const seq of ["1", "10", "11", "2"]) writeFull(f.root, "common", seq);
        writeFull(f.root, "medium", "1");
        writeFull(f.root, "android", "1");

        const archives = FULL_ROOTS.flatMap(archiveRoot => buildArchiveList(
            "https://fixture.invalid",
            f.root,
            `archive-${archiveRoot}-full`,
        ));

        assert.deepEqual(archives.map(archive => archive.location), [
            "https://fixture.invalid/archive-common-full/pinball-1.4.0-1-fixture.zip",
            "https://fixture.invalid/archive-common-full/pinball-1.4.0-2-fixture.zip",
            "https://fixture.invalid/archive-common-full/pinball-1.4.0-10-fixture.zip",
            "https://fixture.invalid/archive-common-full/pinball-1.4.0-11-fixture.zip",
            "https://fixture.invalid/archive-medium-full/pinball-1.4.0-1-fixture.zip",
            "https://fixture.invalid/archive-android-full/pinball-1.4.0-1-fixture.zip",
        ]);
    } finally {
        f.cleanup();
    }
});


test("full archive lists accept max safe sequence and skip invalid names", () => {
    const f = fullFixture();
    try {
        writeFull(f.root, "common", "9007199254740991");
        writeFull(f.root, "common", "9007199254740992");
        writeFull(f.root, "common", "01");

        const archives = buildArchiveList(
            "https://fixture.invalid",
            f.root,
            "archive-common-full",
        );

        assert.deepEqual(archives.map(archive => path.basename(archive.location)), [
            "pinball-1.4.0-9007199254740991-fixture.zip",
        ]);
    } finally {
        f.cleanup();
    }
});


test("full archive lists reject subdirectories outside the three allowed roots", () => {
    const f = fullFixture();
    try {
        const outside = path.join(path.dirname(f.root), "outside");
        mkdirSync(outside);
        writeFileSync(
            path.join(outside, "pinball-1.4.0-1-outside.zip"),
            "outside",
        );

        assert.deepEqual(buildArchiveList(
            "https://fixture.invalid",
            f.root,
            "../outside",
        ), []);
    } finally {
        f.cleanup();
    }
});


test("full archive lists reject symlinked files or archive roots", () => {
    const f = fullFixture();
    try {
        const outside = path.join(path.dirname(f.root), "outside.zip");
        const archiveRoot = path.join(f.root, "archive-common-full");
        const linked = path.join(
            archiveRoot,
            "pinball-1.4.0-1-linked.zip",
        );
        writeFileSync(outside, "outside");
        try {
            symlinkSync(outside, linked, "file");
        } catch (error) {
            const code = (error as NodeJS.ErrnoException).code;
            if (code === "EPERM" || code === "EACCES") {
                const outsideRoot = path.join(path.dirname(f.root), "outside-root");
                rmSync(archiveRoot, { recursive: true });
                mkdirSync(outsideRoot);
                writeFileSync(
                    path.join(outsideRoot, "pinball-1.4.0-1-linked.zip"),
                    "outside",
                );
                symlinkSync(outsideRoot, archiveRoot, "junction");
            } else {
                throw error;
            }
        }

        assert.deepEqual(buildArchiveList(
            "https://fixture.invalid",
            f.root,
            "archive-common-full",
        ), []);
    } finally {
        f.cleanup();
    }
});
