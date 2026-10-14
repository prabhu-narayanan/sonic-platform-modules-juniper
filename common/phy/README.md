<!-- Copyright (c) 2026 Hewlett Packard Enterprise Development LP. All rights reserved. -->

# common/phy — Broadcom PAI-SDK build (design proposal)

## 1. Summary

Consolidate the Broadcom PAI-SDK PHY build from the per-platform trees
(`qfx5252/agera-pai`, `qfx5252/barchetta-pai`) into a **single shared tree**,
`platform/broadcom/sonic-platform-modules-juniper/common/phy`, that:

- receives the vendor SDK tarballs (placed into `common/phy/` at **checkout
  time**; not tracked in git — only a version pointer is committed),
- at **build time** unpacks those tarballs and applies per-SDK patches, then
  builds **one** `libbrcm_pai.so` containing all PHY families
  (EPDM + PAI + Agera + Barchetta), shared by both gbsyncd dockers,
- packages the result as the `libsaigearbox` Debian package.

```
checkout: copy *.tgz --> common/phy/     make: unpack + patch + compile --> libbrcm_pai.so --> libsaigearbox.deb
          ^ pointer in git   ^ .gitignore'd     ^ scripts/extract_and_patch.sh
```

> **Model.** We follow the Broadcom convention — pristine vendor tarballs live
> in `/volume` (versioned via the committed pointer), and only lightweight build
> logic plus any required patches live in the repo. Our case differs in one way:
> `libbrcm_pai.so` is **not** a stock vendor binary. It is an **HPE-composed**
> library, built by whole-archiving four Broadcom SDKs (EPDM, PAI, Agera,
> Barchetta) with HPE-specific build flags. We also retain the ability to apply
> HPE source deltas to any individual SDK via the `patches/<sdk>/` dirs.

## 2. Directory layout

```
common/phy/
├── .gitignore              ignores *.tgz, extracted vendor dirs, output/, .prepared
├── scripts/
│   └── extract_and_patch.sh   build-time: unpack *.tgz + apply per-SDK patches
├── Makefile                .prepared stamp -> extract_and_patch -> output/libbrcm_pai.so
├── patches/                Juniper patches applied on the pristine drops (tracked)
│   └── epdm/ pai/ agera/ barchetta/    (one *.patch set per SDK)
├── debian/                 libsaigearbox packaging (control, rules, changelog, compat)
│
├── *.tgz                   vendor tarballs, placed by checkout          [gitignored]
├── epdm/                   extracted, PHY-agnostic core                 [gitignored]
├── pai/                    extracted, PAI 4.0 + MDIO dispatcher         [gitignored]
├── agera/AGR3_1_0/         extracted vendor phymod SDK                  [gitignored]
└── barchetta/BARC_3_6/     extracted vendor phymod SDK                  [gitignored]
```

Tracked: `.gitignore`, `scripts/`, `Makefile`, `patches/`, `debian/`.
The `*.tgz` and all extracted dirs are build-time only and **not** committed.

## 3. Checkout vs build split

- **Checkout (`sonic-checkout`)** copies the versioned tarballs from `/volume`
  (per `sonic-juniper/pointers/pai_sdk_pointer.mk`) into `common/phy/`. It does
  **not** unpack them.
- **Build (`make`)** does the rest: a `.prepared` stamp runs
  `scripts/extract_and_patch.sh`, which unpacks each `*.tgz` into its canonical
  dir (`epdm/`, `pai/`, `agera/AGR3_1_0/`, `barchetta/BARC_3_6/`) and applies the
  per-SDK patches, before anything compiles.

Bumping the SDK = publish a new tag on `/volume` and change one line in the
pointer.

## 4. Build

`make` builds a single `libbrcm_pai.so` containing **all** PHY families —
EPDM + PAI + Agera (AGR3_1_0) + Barchetta (BARC_3_6). There is no per-platform
selection: the same library serves both gbsyncd dockers, and each drives
whichever PHY its board carries at runtime.

```bash
make          # unpack + patch + build output/libbrcm_pai.so
make clean    # remove extracted dirs, output/, .prepared — keeps the *.tgz
```

Idempotent: extraction is no-clobber and patches use `patch --forward`, so a
re-run over an already-prepared tree is a no-op.

## 5. Patches

`extract_and_patch.sh` applies patches from `patches/<sdk>/*.patch` on top of the
pristine vendor drop, per component:

| Folder | Applied in |
|---|---|
| `patches/epdm/`      | `epdm/` |
| `patches/pai/`       | `pai/` |
| `patches/agera/`     | `agera/AGR3_1_0/` |
| `patches/barchetta/` | `barchetta/BARC_3_6/` |

The `patches/` folders are tracked; the extracted trees they apply to are not.
Note the Agera `-fPIC` link fix is handled in the Makefile via `PHYMOD_CFLAGS`
(not a patch), so no patch is currently required to build.

## 6. Adding a new retimer SDK (e.g. BCM84894)

`libbrcm_pai.so` is HPE-composed, so onboarding a new retimer (for example
**BCM84894**) follows the same pattern as the existing SDKs:

1. **Publish the pristine tarball to `/volume`** and bump the pointer. The
   vendor `*.tgz` is never committed — only its version is, via
   `sonic-juniper/pointers/pai_sdk_pointer.mk`. Checkout copies it into
   `common/phy/`.
2. **Add an HPE patch dir** `patches/bcm84894/` for any HPE source deltas on
   top of the pristine drop (leave a `.gitkeep` if none yet).
3. **Extract + patch** — add one `prepare` line in
   `scripts/extract_and_patch.sh`:

   ```sh
   prepare "BCM84894_<ver>.tgz"  "bcm84894/<TOPDIR>"  "bcm84894"
   ```

4. **Build + link** — in the `Makefile`, add the SDK's compile flags and static
   library, then include it in the whole-archive link of `libbrcm_pai.so`
   (mirroring the Agera/Barchetta `PHYMOD_CFLAGS` handling if it is a phymod
   SDK), and add its extracted dir to the `clean` target.

The result stays a single `libbrcm_pai.so` carrying every PHY family, shared by
both gbsyncd dockers.

## 7. Packaging

`debian/` builds the `libsaigearbox` package. `debian/rules` runs `make` and
installs the resulting `libbrcm_pai.so` as `libsai.so.1.0` (+ `.1` /
unversioned symlinks).

## 8. Repos touched

| Repo | Change |
|---|---|
| `sonic-platform` (double-commit) | `common/phy/` (this tree) |
| `sonic-juniper` | `pointers/pai_sdk_pointer.mk` (version pointer) |
| `sonic-juniper-build` | `checkout/sonic-checkout` (copies the *.tgz into common/phy) |

## 9. Status / remaining work

- [x] `common/phy` tree: `.gitignore`, `scripts/`, `Makefile`, `patches/`, `debian/`
- [x] Version pointer
- [x] Single library for both gbsyncd dockers (no per-platform PHY selection)
- [x] Build-time unpack + per-SDK patch flow (Makefile `.prepared` stamp)
- [ ] `sonic-checkout`: copy the *.tgz into common/phy at checkout
- [ ] (Optional) Migrate `barchetta/adapter` (FPGA MDIO transport) to enable the
      FPGA MDIO path for Barchetta; the library builds without it today
- [ ] Publish the SDK tarballs to the team `/volume` path referenced by the pointer
- [ ] Reconcile the consuming `*.mk` (currently `libsaiagera` / `libsaibarchetta`)
      with the unified `libsaigearbox` package, and repoint `_SRC_PATH` to `common/phy`
