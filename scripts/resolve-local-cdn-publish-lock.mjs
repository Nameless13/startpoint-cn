import path from "node:path"

const [, , rawRepoRoot] = process.argv
if (!rawRepoRoot) {
    console.error("Usage: node resolve-local-cdn-publish-lock.mjs <repo-root>")
    process.exit(2)
}

const repoRoot = path.resolve(rawRepoRoot)
const configured = process.env.CDN_DIR || ".cdn"
if (configured.includes("\0")) {
    console.error("CDN_DIR contains a NUL byte")
    process.exit(1)
}
const cdnParent = path.isAbsolute(configured)
    ? path.normalize(configured)
    : path.resolve(repoRoot, configured)

process.stdout.write(
    path.join(cdnParent, "cn", ".wf-local-1.4.312.lock"),
)
