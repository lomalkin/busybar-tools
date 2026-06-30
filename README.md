# BUSY Bar Tools
[![PyPI](https://img.shields.io/pypi/v/busybar-tools.svg)](https://pypi.org/project/busybar-tools/) [![Python Versions](https://img.shields.io/pypi/pyversions/busybar-tools.svg)](https://pypi.org/project/busybar-tools/)

Command-line (CLI) tools to manage your BUSY Bar device.

- Easy to install firmware to your BUSY Bar by single command.
- Works on Linux, MacOS and Windows.
- There are no heavy dependencies.

Available as a Python package on [PyPI](https://pypi.org/project/busybar-tools/). Source code available on [GitHub](https://github.com/lomalkin/busybar-tools).

> [!WARNING]
> These are unofficial tools that can potentially lead to device bricking if used incorrectly. Use them at your own risk.

## Installation and Upgrade

The tool is installed with [pipx](https://pipx.pypa.io/). Pick your OS:

**Linux (Ubuntu/Debian)**

    sudo apt install pipx
    pipx ensurepath
    pipx install busybar-tools

**macOS** (Homebrew)

    brew install pipx
    pipx ensurepath
    pipx install busybar-tools

**Windows** (Scoop)

    scoop install pipx
    pipx ensurepath
    pipx install busybar-tools

After the first `pipx ensurepath` you may need to open a new terminal.

**Upgrade** (any OS): `pipx upgrade busybar-tools`


## Usage

    busybar <command> [options]

    commands:
      auto-install     Autodetect target & signing, then install — recommended for most users
      cli              CLI terminal session, or run commands non-interactively
      storage          Run the embedded storage.py utility on the device
      install          Install firmware from an explicit source (low-level)
      fetch            Download (and optionally unpack) a firmware bundle locally
      write-recovery   Write a firmware bundle into the recovery partition (no install)
      install-onboard  Install firmware already staged on the device
      wait             Wait for the device to be reachable
      clean            Clean the package's tmp/cache directory

**Most users want [`busybar auto-install`](#busybar-auto-install).** The firmware commands
`install` / `fetch` / `write-recovery` are explicit/low-level and **require an explicit `source`**.

Options go **after** the command (e.g. `busybar install -t 21 0.10.2`). Run `busybar <command> --help`
for the full list.

Device commands (`auto-install`, `cli`, `storage`, `install`, `write-recovery`, `install-onboard`,
`wait`) accept `-d/--device` (IP; `r`/`ref` = reference device) and `-p/--port` (default 23). All of
them except `wait` also accept `--no-wait` to skip the pre-operation reachability check.

### `busybar auto-install`

Autodetects the hardware target and whether signed firmware is required, fetches the matching update
bundle, installs it, then waits for the reboot and reports the version change.

    busybar auto-install [--via-storage | --via-http] [--no-wait] [--no-wait-after]
                         [-d DEVICE] [-p PORT] [source]

- `source` — update-server tag/branch or URL (default: `dev`). Local files/dirs are not accepted here
  (the bundle is chosen automatically for the detected target/signing — use `install` for those).
- `--no-wait-after` — return right after install instead of waiting for the reboot / version check.

Examples:
- `busybar auto-install` — install the latest `dev` firmware for this device.
- `busybar auto-install 0.10.2` — install a specific tag.

### `busybar cli`

Interactive session, or run commands non-interactively.

    busybar cli [-i] [--timeout SECONDS] [-d DEVICE] [-p PORT] [-- COMMAND ...]

- `busybar cli` — interactive session (`Ctrl+]` to exit).
- `busybar cli -- device_info` — run one command and exit.
- `busybar cli -i -- device_info` — run the command, then stay in the session (same connection).
- `echo device_info | busybar cli` — run commands from stdin (one per line) and exit.

### `busybar storage`

Run the embedded storage.py tool on the device; pass its sub-command after `--`.

- `busybar storage -- list /ext`
- `busybar storage -- send ./local.bin /ext/local.bin`

Sub-commands: `mkdir`, `format_ext`, `remove`, `read`, `size`, `receive`, `send`, `list`.

### `busybar install`

    busybar install [--update | --bkp] [--signed | --unsigned] [--via-storage | --via-http]
                    [--no-install] [-t TARGET] [-d DEVICE] [-p PORT] source

For bracketed pairs the first option is the default. `source` (required) is resolved in priority order:
URL (`http`/`https`) → local bundle file → local directory → update-server tag/branch.

- `-t`, `--target TARGET` — hardware target (default: 22; any integer that exists on the server).
- `--update` | `--bkp` — bundle type (regular firmware vs recovery bundle).
- `--signed` | `--unsigned` — bundle signature (production devices require signed).
- `--via-storage` | `--via-http` — transport; `--via-http` is direct-install only.
- `--no-install` — upload to the staging dir without installing (`--via-storage` only).

Examples:
- `busybar install dev` — install signed firmware from the `dev` branch.
- `busybar install --unsigned 0.10.2` — install a specific unsigned tag/release.
- `busybar install -t 21 0.10.2` — install for hardware target 21.
- `busybar install ./bundle.tgz` — install from a local bundle file.

### `busybar fetch`

Download (and optionally unpack) a firmware bundle locally, without touching the device. Same `source`
and firmware-selection options as `install`.

    busybar fetch [--update | --bkp] [--signed | --unsigned] [-t TARGET] [--unpack] [-o OUTPUT] source

- `--update` | `--bkp` is a type of the bundle to fetch.
- `--unpack` — unpack the downloaded bundle to a directory
- `-o`, `--output DEST` — destination dir or file path (default: package cache). The final path is printed.

Examples:
- `busybar fetch 0.10.2 -o ~/fw/` — download into a directory.
- `busybar fetch dev --unpack -o ./out/` — download and unpack.

### `busybar write-recovery`

Write a firmware bundle into the recovery partition (`/bkp`) **without** installing it (the image used
on factory reset). **DANGER**: a wrong bundle can brick the device.

    busybar write-recovery [--bkp | --update] [--signed | --unsigned] [-t TARGET]
                           [-d DEVICE] [-p PORT] [--no-wait] [--confirm-timeout SECONDS] source

- Defaults to `--bkp` (`--update` is allowed but warns). Storage transport only.
- `--confirm-timeout SECONDS` — countdown before overwriting the partition (default: 3).

Install *from* recovery afterwards with `busybar install-onboard recovery`.

### `busybar install-onboard`

Install firmware already staged on the device (no download/upload).

    busybar install-onboard [-d DEVICE] [-p PORT] [device_path]

- `device_path` — on-device path to install from, or the literal `recovery` for the recovery
  partition (default: the staged update dir).

### `busybar wait` / `busybar clean`

- `busybar wait` — wait until the device is reachable (useful for scripting).
- `busybar clean` — clean the package's local tmp/cache directory.

## Development and Testing

Editable install: `pip install -e .` from the project root (use a virtual environment).

Run tests (`pip install -e ".[test]"`). Offline tests always run first, then live ones:
- `pytest` — the offline test suite.
- `pytest --run-hardware [-vv] [--device IP] [--port N]` — also runs safe live-device tests
  (cli/device_info, storage round-trip in `/ext/tmp`, fetch, install stage-only). Skipped by default;
  self-skip if the device is unreachable. Device can also be set via `BUSYBAR_TEST_DEVICE` /
  `BUSYBAR_TEST_PORT`.
- `pytest --run-flash [-vv] [--device IP]` — also runs destructive tests that **really reflash/reboot** the
  device (install over storage and http, auto-install) and overwrite the recovery partition with a
  pinned version (write-recovery). The run **ends with a factory reset** that rolls out that pinned
  recovery image, so the device is left on the pinned version. Stand-only; these take minutes.
  Tunables (pinned recovery version, flash source) are at the top of `tests/hardware/conftest.py`.

To run a subset (e.g. while iterating, to avoid the full flash run) use the standard pytest selectors:
- by name: `pytest --run-flash -k "write_recovery or factory_reset"`
- by marker: `pytest --run-flash -m "flash and not flash_final"`, or `-m flash_final` for just the reset
- by file/node: `pytest --run-flash tests/hardware/test_install_live.py::test_install_flash`
- add `-s` to see live device output (handy during flashing).

---

# Changelog

## Upcoming features plan
- Easy recovery of Busybar via DFU from any possible broken state
- Factory reset?
- ...create an [issue](https://github.com/lomalkin/busybar-tools/issues) for any feature requests or bug reports!


## 0.8.0
- New `busybar auto-install` command — the recommended path for regular users: it reads the device
  info, autodetects the hardware target and whether signed firmware is required, fetches the matching
  update bundle, installs it, and reports the version change. Accepts only an update-server tag/branch/URL.
  Supports `--via-storage`/`--via-http`, `--no-wait` (skip the pre-check) and `--no-wait-after`
  (skip waiting for the reboot afterwards).
- `install` / `fetch` / `write-recovery` now **require an explicit `source`** (the `dev` default was
  removed; it now lives in `auto-install`).
- `-t/--target` is no longer restricted to a fixed list — it accepts any integer target supported by
  the update server (default still `22`).
- `busybar cli` can now run commands non-interactively: from arguments (`cli -- device_info`) or from
  stdin (`echo device_info | busybar cli`, one command per line). With `-i`, an argument command runs
  and then drops into the interactive session on the same connection.
- CLI restructure for clarity and consistency (**breaking change**):
    - Options are now scoped to the command they affect and go **after** the command
      (e.g. `busybar install -t 21 dev` instead of `busybar -t 21 install`). `-d`/`-p`/`-t` are no longer global.
    - `--download-only` / `--unpack-only` are removed from `install` and replaced by a dedicated `busybar fetch`
      command (with `--unpack` and `-o/--output` to choose where to place the result).
    - `busybar update` is renamed to `busybar install-onboard` (install firmware already staged on the device);
      the recovery partition is now selected with the `recovery` positional keyword instead of a `--recovery` flag.
    - Writing a bundle into the recovery partition is now a dedicated `busybar write-recovery` command
      (defaults to `--bkp`); the `install --save-as-recovery` / `--install` / `--confirm-timeout` options are removed.
    - `--recovery-timeout` is renamed to `--confirm-timeout`.
    - Invalid combinations now fail with a clear error (e.g. `--via-http` with `--no-install`).
    - `busybar storage` now selects the device consistently via `-d`/`-p` (pass storage sub-commands after `--`).
    - Added `--no-wait` to skip the device reachability (ping) check on device-facing commands (except `wait`).
    - `write-recovery` logs a warning when used with `--update` instead of `--bkp` (the intended bundle type for recovery).

## 0.7.0
- Windows support (cli, install, storage)

## 0.6.1
- Embedded storage.py tool to manage storage of your device from any terminal with `busybar storage <storage.py args>` command. You can use following commands directly: mkdir, format_ext, remove, read, size, receive, send, list.

## 0.6.0
- Default U5_TARGET_HW is 22, that corresponds to the production BUSY Bar devices. Default firmware bundle is `--update` and `--signed`.

## 0.5.2
- Fix a bug with installing from local dir.

## 0.5.1
- Support of Directory as a Source.
- `--download-only` and `--unpack-only` options for `busybar install` command to just download or unpack the bundle without invoking update. The `--download-only` option is only applicable if the Update server used as a Source, while `--unpack-only` can be used with any source.
- Return back invokation of the update from the recovery bundle already located in `/bkp/recovery` on the device with `--recovery` arg.

## 0.5.0
- `busybar update` and `busybar update-storage` commands now changed to `busybar install` (breaking change):
    - Support for both signed and unsigned bundles. By default, signed bundles are used, but you can use the `--unsigned` option to use unsigned bundles if needed. All production BUSY Bar devices must use only signed bundles.
    - Progress bar when downloading update files from the update server.
    - Using storage.py transport by default, but can be overridden with `--via-http` option.
    - Default bundle is `--update` (regular user firmware), but can be overridden with `--bkp` (recovery bundle, with welcome animations).
    - Added `--save-as-recovery` option to save the update bundle as a recovery bundle. Both `--update` and `--bkp` bundles can be saved as recovery; intentionally only `--bkp` is meant to be used as a recovery bundle.
    - `.tar` and `.tgz` formats are supported for update bundles now, with fallback to `.tar` if `.tgz` is not available in the source.
    - You can use any locally saved update bundles as a source now. It is actually possible to install it as regular firmware or as a recovery bundle with `--save-as-recovery`.

## 0.4.0
- Python 3.8 compatibility. Python 3.8 is the minimum required version now.
- wait_for_device(): now in single line, calc seconds.

## 0.3.2
- Force enable debug mode before invoking update from recovery. Useful if the device does not allow to start update from recovery due to low battery level. This can potentially lead to bricking the device, so use it with caution.

## 0.3.1
- Fix a bug with device path creation in `busybar update-storage` command.

## 0.3.0
- Fixed CLI `busybar cli`: now it properly works with auto-complete and history navigation with arrow keys.
- Update via storage.py `busybar update-storage`. There is a DANGEROUS option that allows rewriting the device recovery bundle by using the `--save-as-recovery-only` key.
- Invocation of update from `/bkp/recovery` via `busybar update-recovery` command.
- Wait for device available before any operations.

## 0.2.0
- CLI terminal session to device available via `busybar cli` command
- Improved file path handling to more reliably locate update files

## 0.1.0
- Initial release (basic functionality for firmware update)

