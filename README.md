
HPE/Juniper Networks Platform Support for SONiC
==============================================

This repository packages the Juniper QFX5241 SONiC platform support and its shared Juniper platform components. The first phase targets QFX5241 only.

## Packages

- `sonic-platform-juniper-common` provides shared utilities, Python platform code, daemons, and the `juniper-common-platform-init.service` unit.
- `sonic-platform-juniper-qfx5241` provides QFX5241 kernel modules, platform utilities, device data, and the `pddf-platform-init.service` unit. It depends on the common package.

The common initialization service runs before PDDF platform initialization. The QFX5241 unit runs the QFX5241 pre-initialization hook, installs PDDF devices, and runs the post-initialization hook.

## Platform Selection

The default platform selection is `qfx5241`, set by `MODULE_DIRS` in `debian/rules`. Kernel modules are selected for the QFX5241 package from its PDDF device data and their module dependencies.

## Tests

Run the package unit tests from the repository root:

```sh
python3 -m pytest
```
