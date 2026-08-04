from __future__ import annotations

import binascii
import logging

import typer

from busybar_tools.commands.storage import StorageService
from busybar_tools.config import DEVICE_IP, DEVICE_PORT
from busybar_tools.presentation.common import endpoint

app = typer.Typer(help="Run storage operations on the device.")


def _service(ctx: typer.Context) -> StorageService:
    service = ctx.obj
    if not isinstance(service, StorageService):
        raise RuntimeError("Storage command context was not initialized")
    return service


@app.callback()
def storage_options(
    ctx: typer.Context,
    device: str = typer.Option(
        DEVICE_IP,
        "-d",
        "--device",
        "--host",
        help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}",
    ),
    port: int = typer.Option(
        DEVICE_PORT,
        "-p",
        "--port",
        help=f"Device TCP port, default: {DEVICE_PORT}",
    ),
    no_wait: bool = typer.Option(
        False,
        "--no-wait",
        help="Skip the device reachability check before the operation",
    ),
):
    ctx.obj = StorageService(endpoint(device, port), wait_before=not no_wait)


@app.command("mkdir", help="Create a directory")
def mkdir(ctx: typer.Context, device_path: str):
    logging.debug('Creating "%s"', device_path)
    _service(ctx).mkdir(device_path)


@app.command("format_ext", help="Format the external flash card")
def format_external(ctx: typer.Context):
    logging.debug("Formatting /ext SD card")
    _service(ctx).format_external()


@app.command("remove", help="Remove a file or directory")
def remove(ctx: typer.Context, device_path: str):
    logging.debug('Removing "%s"', device_path)
    _service(ctx).remove(device_path)


@app.command("read", help="Read a file")
def read(ctx: typer.Context, device_path: str):
    logging.debug('Reading "%s"', device_path)
    data = _service(ctx).read(device_path)
    try:
        typer.echo("Text data:")
        typer.echo(data.decode())
    except UnicodeDecodeError:
        typer.echo("Binary hexadecimal data:")
        typer.echo(binascii.hexlify(data).decode())


@app.command("size", help="Print a file size")
def size(ctx: typer.Context, device_path: str):
    logging.debug('Getting size of "%s"', device_path)
    typer.echo(_service(ctx).size(device_path))


@app.command("receive", help="Receive a file or directory")
def receive(ctx: typer.Context, device_path: str, local_path: str):
    _service(ctx).receive(device_path, local_path)


@app.command("send", help="Send a file or directory")
def send(
    ctx: typer.Context,
    local_path: str,
    device_path: str,
    force: bool = typer.Option(False, "-f", "--force", help="Force sending"),
):
    _service(ctx).send(local_path, device_path, force)


@app.command("list", help="Recursively list files and directories")
def list_files(
    ctx: typer.Context,
    device_path: str = typer.Argument("/", help="Device directory to list"),
):
    logging.debug('Listing "%s"', device_path)
    for entry in _service(ctx).list(device_path):
        typer.echo(entry)


@app.command("stress", help="Run a destructive storage stress test")
def stress(
    ctx: typer.Context,
    device_path: str,
    file_size: int,
    count: int = typer.Option(10, "-c", "--count", help="Iteration count"),
):
    allow_internal = False
    if device_path.startswith(("/int", "/any")):
        logging.error("This test wears out flash memory; never use it with internal storage")
        allow_internal = (
            typer.prompt("Type 'void' to continue").strip().lower() == "void"
            and typer.prompt("Type 'because' to confirm again").strip().lower() == "because"
        )
    _service(ctx).stress(
        device_path,
        file_size,
        count,
        allow_internal=allow_internal,
    )


__all__ = ["app"]
