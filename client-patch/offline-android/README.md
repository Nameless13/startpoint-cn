# Offline Android APK builder

`build_offline_apk.py` builds one locked Android APK for the offline bundle. It
is a library stage for the release orchestrator; it does not create, rotate or
bootstrap signing keys.

## Inputs

Construct `OfflineApkBuildConfig` with:

- the accepted source APK and tracked `base-lock.json`;
- new final APK and report destinations;
- an ASCII-only work directory (the final filename may contain Chinese text);
- a `Toolchain` returned by `mod-tools/wf_offline_toolchain.py`;
- a dedicated `SigningConfig` loaded from the offline release home.

Set the keystore password only in `WF_OFFLINE_KEYSTORE_PASSWORD`. The password
is passed to apksigner as `env:WF_OFFLINE_KEYSTORE_PASSWORD`; it is never put in
the command line or report. Missing tools, keystore, password, accepted lock or
locked source evidence fail closed.

Call:

```python
report = build_offline_apk(config)
```

The builder intentionally has no key-generation fallback. Use Task 7's
interactive signer initialization separately when provisioning a new release
home.

## Fixed build and verification order

The SWF is patched exactly in this order:

1. `abyss-mode-equipment`
2. `seris-phase4`
3. `render-scale`
4. `resource-version`

It then performs one APK rewrite, one zipalign build and one apksigner sign.
Only the main SWF and exact, case-sensitive, top-level signer members may
change; nested `META-INF/AIR/**`, the manifest, DEX and native members must stay
byte-identical. Lower-case signature-like member names are ordinary members
and are preserved.

After signing, the builder runs `zipalign -c -p -v 4` and
`apksigner verify --verbose --print-certs` through the selected toolchain. It
requires v1, v2 and v3 signatures and the configured dedicated certificate
fingerprint. The signed SWF is extracted again and all four patch verifiers are
rerun. The final inspection additionally binds:

- all nine Seris sites and all three render sites;
- `fullResourceVersion=1.4.196` and `isFullPackage=true`;
- the active offline, resource-version, DummyRemote and save-method hashes;
- the unchanged package/version, external-storage permission count, manifest,
  DEX and native hashes.

The signer verification is bound to the same whole-APK SHA-256 that is staged
for final publication.

## Transaction and report guarantees

All tool-visible intermediates live under a private ASCII transaction. The
source APK and accepted lock are identity-gated; the accepted lock is loaded
once and its frozen mapping is shared by every patch/verifier. A failure,
cancellation or competing destination leaves no builder-owned final pair and
never replaces an existing APK or report.

On Windows, the transaction root and destination parent are bound to stable
directory handles. The parent handle denies delete sharing through publication;
the transaction root is rename-locked and removed by its exact handle. APK and
report staging files likewise stay open by identity through no-replace rename,
so cleanup cannot delete a same-name competitor after a path swap.

The APK and canonical UTF-8/LF JSON report are published as an exclusive pair.
The report contains only public hashes, patch order, sanitized stage evidence,
resource version, signature schemes and certificate fingerprint. It contains
no absolute paths, private-key path, password, environment or command line.

## Focused verification

```powershell
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_baseline.py -v
python -X utf8 -m unittest mod-tools/tests/test_offline_apk_builder.py -v
python -X utf8 -m unittest mod-tools/tests/test_abyss_apk_builder.py -v
```
