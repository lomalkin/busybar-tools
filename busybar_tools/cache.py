import hashlib
import logging
import os
import re
import tempfile

from busybar_tools.config import PROJECT_NAME


def workdir(subdir=None, suffix_len=4):
    package_path = os.path.dirname(os.path.abspath(__file__))
    package_hash = hashlib.sha256(package_path.encode()).hexdigest()[:suffix_len]
    root = os.path.join(tempfile.gettempdir(), f"{PROJECT_NAME}_{package_hash}")
    path = os.path.join(root, subdir) if subdir is not None else root
    os.makedirs(path, exist_ok=True)
    logging.debug("Workdir: %s", path)
    return path


def url_cache_key(url):
    base = re.sub(r"[^a-z0-9_]+", "_", url.lower())
    base = re.sub(r"_+", "_", base).strip("_") or "_"
    base = base.replace("https_", "").replace("http_", "")
    base = base.replace("update_busy_app_builds_", "")[:64]
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    return f"{base}_{digest}"
