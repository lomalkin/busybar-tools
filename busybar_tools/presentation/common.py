import typer

from busybar_tools.config import DEVICE_IP_REF
from busybar_tools.options import DeviceEndpoint, FirmwareSelection

SOURCE_HELP = (
    "Firmware source. Accepted forms, in priority order: explicit URL (http/https), "
    "local bundle file, local directory, or update-server tag/branch."
)


def endpoint(device, port):
    if device.lower() in ("r", "ref"):
        device = DEVICE_IP_REF
    return DeviceEndpoint(device, port)


def finish(result):
    if result and result != 0:
        raise typer.Exit(int(result))
    return result or 0


def bundle_type(update, bkp, default):
    if update and bkp:
        raise typer.BadParameter("--update and --bkp are mutually exclusive")
    return "update" if update else "bkp" if bkp else default


def signed_value(signed, unsigned):
    if signed and unsigned:
        raise typer.BadParameter("--signed and --unsigned are mutually exclusive")
    return not unsigned


def firmware_selection(
    source,
    target,
    update,
    bkp,
    signed,
    unsigned,
    default_bundle="update",
    save_as_recovery=False,
):
    return FirmwareSelection(
        source=source,
        target=target,
        bundle_type=bundle_type(update, bkp, default_bundle),
        signed=signed_value(signed, unsigned),
        save_as_recovery=save_as_recovery,
    )

