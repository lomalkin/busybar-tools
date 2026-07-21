from typing import Optional

import typer

from busybar_tools.commands.cli_terminal import run_cli_terminal
from busybar_tools.commands.factory_reset import run_factory_reset
from busybar_tools.commands.report import run_report
from busybar_tools.commands.wait import run_clean, run_wait_for_device
from busybar_tools.config import DEVICE_IP, DEVICE_PORT
from busybar_tools.options import CliOptions, FactoryResetOptions, WaitOptions
from busybar_tools.presentation.common import endpoint, finish
from busybar_tools.presentation.storage import app as storage_app
from busybar_tools.report import ReportOptions


def register(app):
    app.command("cli", context_settings={"allow_extra_args": True, "ignore_unknown_options": True}, help="CLI terminal session to the device")(cli_terminal)
    app.command("report", help="Collect a diagnostic report archive from the device")(report)
    app.add_typer(storage_app, name="storage")
    app.command("factory-reset", help="Factory reset the device")(factory_reset)
    app.command("wait", help="Wait for the device to be reachable via ping")(wait)
    app.command("clean", help="Clean the package tmp/cache directory")(clean)


def cli_terminal(
    ctx: typer.Context,
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    interactive: bool = typer.Option(False, "-i", "--interactive", help="After running command arguments, stay interactive"),
    timeout: int = typer.Option(5, "--timeout", help="Per-command response wait cap for non-interactive runs"),
):
    return finish(run_cli_terminal(CliOptions(
        endpoint=endpoint(device, port), wait_before=not no_wait,
        interactive=interactive, timeout=timeout, commands=tuple(ctx.args),
    )))


def report(
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device CLI port, default: {DEVICE_PORT}"),
    http_port: int = typer.Option(80, "--http-port", help="Device HTTP API port, default: 80"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output .zip path"),
    api_token: Optional[str] = typer.Option(None, "--api-token", help="HTTP API token for devices with access key enabled"),
    timeout: int = typer.Option(5, "--timeout", help="HTTP request timeout in seconds"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    with_logs: bool = typer.Option(True, "--with-logs/--no-logs", help="Try to include firmware log dump"),
    screens: bool = typer.Option(True, "--screens/--no-screens", help="Include raw display frame captures"),
    cli: bool = typer.Option(True, "--cli/--no-cli", help="Include read-only CLI diagnostics"),
):
    options = ReportOptions(
        endpoint=endpoint(device, port), http_port=http_port, output=output,
        api_token=api_token, timeout=timeout, include_logs=with_logs,
        include_screens=screens, include_cli=cli,
    )
    return finish(run_report(options, wait_before=not no_wait))


def factory_reset(
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Skip the device reachability check before the operation"),
    shipping_mode: bool = typer.Option(False, "--shipping-mode", "-s", help="Enter shipping mode after reset"),
    no_wait_after: bool = typer.Option(False, "--no-wait-after", help="Skip waiting for the device to come back online after reset"),
    offline_timeout: int = typer.Option(180, "--offline-timeout", help="How long to wait for the device to drop offline"),
):
    return finish(run_factory_reset(FactoryResetOptions(
        endpoint=endpoint(device, port), wait_before=not no_wait,
        shipping_mode=shipping_mode, wait_after=not no_wait_after,
        offline_timeout=offline_timeout,
    )))


def wait(
    device: str = typer.Option(DEVICE_IP, "-d", "--device", help=f"Device IP (or 'r'/'ref'), default: {DEVICE_IP}"),
    port: int = typer.Option(DEVICE_PORT, "-p", "--port", help=f"Device port, default: {DEVICE_PORT}"),
):
    return finish(run_wait_for_device(WaitOptions(endpoint=endpoint(device, port))))


def clean():
    return finish(run_clean())
