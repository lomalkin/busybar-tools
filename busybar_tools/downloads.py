import logging
import os
from urllib import request

from busybar_tools.config import FETCH_TIMEOUT_DEFAULT, HTTP_USER_AGENT


def _request(url):
    return request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})


def download_file(url, filename, directory, progress=False):
    logging.info("Downloading %s to %s ...", url, directory)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)

    with request.urlopen(_request(url)) as response:
        total = int(response.headers.get("Content-Length", 0) or 0)
        downloaded = 0
        with open(path, "wb") as output:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if progress:
                    _print_progress(filename, downloaded, total)
    if progress:
        print(flush=True)
    return path if os.path.isfile(path) else None


def _print_progress(filename, downloaded, total):
    if total > 0:
        percent = downloaded * 100 // total
        bar_len = 30
        filled = bar_len * percent // 100
        bar = "=" * filled + (">" + " " * (bar_len - filled - 1) if filled < bar_len else "")
        print(
            f"\r{filename}: {downloaded / 1_048_576:.1f}/{total / 1_048_576:.1f} MB "
            f"[{bar}] {percent}%",
            end="",
            flush=True,
        )
    else:
        print(f"\r{filename}: {downloaded / 1_048_576:.1f} MB", end="", flush=True)


def fetch_text(url, timeout=FETCH_TIMEOUT_DEFAULT):
    try:
        with request.urlopen(_request(url), timeout=timeout) as response:
            if response.status == 200:
                return response.read().decode()
    except Exception as exc:
        logging.error("Error fetching %s: %s", url, exc)
    return None

