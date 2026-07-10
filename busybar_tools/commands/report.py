import logging

from busybar_tools.device import wait_for_device_maybe
from busybar_tools.report import ReportOptions, create_report


def run_report(args):
    wait_for_device_maybe(args)
    logging.info("Collecting device report...")
    path = create_report(
        ReportOptions(
            device=args.device,
            cli_port=args.port,
            http_port=args.http_port,
            output=args.output,
            api_token=args.api_token,
            timeout=args.timeout,
            include_logs=args.with_logs,
            include_screens=args.screens,
            include_cli=args.cli,
        )
    )
    print(path)
    return 0


__all__ = ["run_report"]
