#!/usr/bin/env python3

import binascii
import filecmp
import logging
import os
import tempfile

import typer

from busybar_tools.config import DEVICE_IP, DEVICE_PORT
from busybar_tools.flipper.storage_socket import FlipperStorage, FlipperStorageOperations


app = typer.Typer(help="BUSY Bar storage utility.")


def _port(host, port):
    return host, int(port)


def _run_storage_op(func):
    try:
        result = func()
        return result if isinstance(result, int) else 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


@app.callback()
def main_options(
    ctx: typer.Context,
    host: str = typer.Option(DEVICE_IP, "--host", help=f"Device IP, default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device TCP port, default: {DEVICE_PORT}"),
    debug: bool = typer.Option(False, "-d", "--debug", help="Enable debug logging"),
):
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    ctx.obj = {"host": host, "port": port}


@app.command("mkdir", help="Create directory")
def mkdir(ctx: typer.Context, flipper_path: str):
    def op():
        logging.debug(f'Creating "{flipper_path}"')
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            storage.mkdir(flipper_path)

    raise typer.Exit(_run_storage_op(op))


@app.command("format_ext", help="Format flash card")
def format_ext(ctx: typer.Context):
    def op():
        logging.debug("Formatting /ext SD card")
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            storage.format_ext()

    raise typer.Exit(_run_storage_op(op))


@app.command("remove", help="Remove file/directory")
def remove(ctx: typer.Context, flipper_path: str):
    def op():
        logging.debug(f'Removing "{flipper_path}"')
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            storage.remove(flipper_path)

    raise typer.Exit(_run_storage_op(op))


@app.command("read", help="Read file")
def read(ctx: typer.Context, flipper_path: str):
    def op():
        logging.debug(f'Reading "{flipper_path}"')
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            data = storage.read_file(flipper_path)
            try:
                print("Text data:")
                print(data.decode())
            except Exception:
                print("Binary hexadecimal data:")
                print(binascii.hexlify(data).decode())

    raise typer.Exit(_run_storage_op(op))


@app.command("size", help="Size of file")
def size(ctx: typer.Context, flipper_path: str):
    def op():
        logging.debug(f'Getting size of "{flipper_path}"')
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            print(storage.size(flipper_path))

    raise typer.Exit(_run_storage_op(op))


@app.command("receive", help="Receive file")
def receive(ctx: typer.Context, flipper_path: str, local_path: str):
    def op():
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            FlipperStorageOperations(storage).recursive_receive(flipper_path, local_path)

    raise typer.Exit(_run_storage_op(op))


@app.command("send", help="Send file or directory")
def send(
    ctx: typer.Context,
    local_path: str,
    flipper_path: str,
    force: bool = typer.Option(False, "-f", "--force", help="Force sending"),
):
    def op():
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            FlipperStorageOperations(storage).recursive_send(flipper_path, local_path, force)

    raise typer.Exit(_run_storage_op(op))


@app.command("list", help="Recursively list files and dirs")
def list_files(ctx: typer.Context, flipper_path: str = "/"):
    def op():
        logging.debug(f'Listing "{flipper_path}"')
        with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
            storage.list_tree(flipper_path)

    raise typer.Exit(_run_storage_op(op))


@app.command("stress", help="Stress test")
def stress(
    ctx: typer.Context,
    flipper_path: str,
    file_size: int,
    count: int = typer.Option(10, "-c", "--count", help="Iteration count"),
):
    def op():
        logging.error("This test is wearing out flash memory.")
        logging.error("Never use it with internal storage (/int)")

        if flipper_path.startswith("/int") or flipper_path.startswith("/any"):
            logging.error("Stop at this point or device warranty will be void")
            say = input("Anything to say? ").strip().lower()
            if say != "void":
                return 2
            say = input("Why, Mr. Anderson? ").strip().lower()
            if say != "because":
                return 3

        with tempfile.TemporaryDirectory() as tmpdirname:
            send_file_name = os.path.join(tmpdirname, "send")
            receive_file_name = os.path.join(tmpdirname, "receive")
            with open(send_file_name, "w") as fout:
                fout.write("A" * file_size)

            with FlipperStorage(_port(ctx.obj["host"], ctx.obj["port"])) as storage:
                if storage.exist_file(flipper_path):
                    logging.error("File exists, remove it first")
                    return
                remaining = count
                while remaining > 0:
                    storage.send_file(send_file_name, flipper_path)
                    storage.receive_file(flipper_path, receive_file_name)
                    if not filecmp.cmp(receive_file_name, send_file_name):
                        logging.error("Files mismatch")
                        break
                    storage.remove(flipper_path)
                    os.unlink(receive_file_name)
                    remaining -= 1

    raise typer.Exit(_run_storage_op(op))


if __name__ == "__main__":
    app()
