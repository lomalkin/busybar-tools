# Architecture

`busybar-tools` is organized around a thin presentation layer and explicit application inputs.
The command line is not used as an internal API.

## Layers

- `presentation/` declares Typer arguments and converts them into immutable option dataclasses.
- `commands/` orchestrates user operations and contains no argument parsing.
- `device/` owns the BUSY Bar CLI and storage protocols plus device information and operations.
- `firmware/` owns update indexes, source resolution, downloads, cache validation, and bundles.
- `dfu/` owns DfuSe parsing, recovery resolution, and USB backends.
- `report/` owns diagnostic collectors, redaction, manifests, and summaries.
- `api.py` and `transport.py` are the shared HTTP and TCP infrastructure boundaries.

## Dependency Rules

1. Presentation may depend on commands and typed options.
2. Commands may coordinate domains, but domains must not import presentation or commands.
3. Device and firmware code receive `DeviceEndpoint` and `FirmwareSelection`, not CLI namespaces.
4. Expected user-facing failures derive from `BusybarError`.
5. Hardware access must remain behind explicitly marked hardware tests; destructive operations require `--run-flash`.

## Extension Points

- Add a DFU implementation under `dfu/backends/` and select it in `dfu/recovery.py`.
- Add report collectors inside `report/`; collector failures must remain isolated in the manifest.
- Add a CLI command declaration under `presentation/` and its behavior under `commands/`.

