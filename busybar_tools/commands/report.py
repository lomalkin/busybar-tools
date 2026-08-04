import logging

from busybar_tools.device import ensure_device_reachable
from busybar_tools.report import ReportOptions, create_report


def run_report(options: ReportOptions, wait_before=True, verbose=True):
    endpoint = options.endpoint
    ensure_device_reachable(endpoint, enabled=wait_before, verbose=verbose)
    logging.info("Collecting device report...")
    path = create_report(options)
    print(path)
    return 0


__all__ = ["run_report"]
