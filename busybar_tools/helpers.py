import logging
import os, sys
import json

import http.client
from urllib.parse import urlparse
from urllib import request

import shutil, platform
import re, hashlib

import subprocess, time

from busybar_tools.config import PROJECT_NAME, FETCH_TIMEOUT_DEFAULT, UPDATE_SERVER_BASE, HTTP_USER_AGENT


def _make_request(url):
    """Build a urllib Request with a non-default User-Agent.

    The update mirror's CDN blocks the default "Python-urllib/x.y" UA with HTTP 403.
    """
    return request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})


def _ping_command(host, timeout):
    timeout = max(1, int(timeout))
    system = platform.system()
    if system == "Windows":
        timeout_ms = max(1000, timeout * 1000)
        return ["ping", "-n", "1", "-w", str(timeout_ms), host]
    if system == "Darwin":
        return ["ping", "-c", "1", "-t", str(timeout), host]
    return ["ping", "-c", "1", "-W", str(timeout), host]
    
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s')

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # fh = logging.FileHandler("tmp/app.log")
    # fh.setLevel(logging.DEBUG)
    # fh.setFormatter(formatter)
    # logger.addHandler(fh)

def print_pretty(data, return_instead_of_print=False):
    def _out_handler(data):
        if return_instead_of_print:
            return data
        else:
            print(data)

    def _convert_to_json(data):
        if isinstance(data, dict) or isinstance(data, list):
            return json.dumps(data, indent=4)
        try:
            parsed_json = json.loads(data)
            return json.dumps(parsed_json, indent=4)
        except (json.JSONDecodeError, TypeError):
            return data

    if isinstance(data, str):
        try:
            parsed_data = json.loads(data)
            return _out_handler(_convert_to_json(parsed_data))
        except (json.JSONDecodeError, TypeError):
            return _out_handler(data)
    else:
        return _out_handler(_convert_to_json(data))

def network_ping_bool(host, timeout=1, verbose=False):
    try:
        output = subprocess.check_output(
            _ping_command(host, timeout),
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        if verbose:
            print(output)
    except subprocess.CalledProcessError:
        return False
    # Windows `ping` exits 0 even when the reply is an ICMP error such as
    # "Destination host unreachable" or "Request timed out" (any received packet
    # counts as success). A genuine echo reply always carries a TTL field, so we
    # require it and reject the error responses. Without this the reboot-wait
    # races through while the device is still down and the CLI isn't up yet.
    if platform.system() == "Windows":
        low = output.lower()
        if "unreachable" in low or "timed out" in low or "ttl=" not in low:
            return False
    return True

def wait_for_device(
    ip, timeout = None, verbose=False, delay=1, success_ping_as=True, verbose_in_place=True
):
    data = {
        "ip": ip,
        "try_counter": 0,
        "success": False,
    }

    def _print_in_place(msg: str):
        print(f"\r\033[K{msg}", end="", flush=True)  # \033[K to clear the line

    ts = time.time()
    if verbose and verbose_in_place:
        _print_in_place(f"Ping {ip}... ")
    while True:
        res = network_ping_bool(ip, delay)
        time_elapsed_int = int(time.time() - ts)
        data["try_counter"] += 1
        msg = f"{data['try_counter']}: PING {ip} ({time_elapsed_int}s)"
        if res == success_ping_as:
            data["success"] = True
            if verbose:
                if verbose_in_place:
                    _print_in_place(msg + ": OK")
                else:
                    print(msg + ": OK")
            break
        else:
            if verbose:
                if verbose_in_place:
                    _print_in_place(msg + ": Failed")
                else:
                    print(msg + ": Failed")
        if timeout is not None and ts + timeout <= time.time():
            break
        time.sleep(delay)
    if verbose and verbose_in_place:
        print("")  # move to next line after loop
    return data

def file_download(file_url, file_name, dir, progress=False):
    logging.info(f"Downloading {file_url} to {dir} ...")
    os.makedirs(dir, exist_ok=True)

    file_path = os.path.join(dir, file_name)

    def _print_progress(downloaded, total_size):
        if total_size > 0:
            percent = downloaded * 100 // total_size
            bar_len = 30
            filled = bar_len * percent // 100
            bar = ('=' * filled + '>' + ' ' * (bar_len - filled - 1)) if filled < bar_len else '=' * bar_len
            dl_mb = downloaded / 1_048_576
            total_mb = total_size / 1_048_576
            print(f"\r{file_name}: {dl_mb:.1f}/{total_mb:.1f} MB [{bar}] {percent}%", end="", flush=True)
        else:
            print(f"\r{file_name}: {downloaded / 1_048_576:.1f} MB", end="", flush=True)

    # Stream with a custom User-Agent (urlretrieve cannot set headers without a global opener;
    # the update mirror's CDN 403s the default urllib UA).
    with request.urlopen(_make_request(file_url)) as response:
        total_size = int(response.headers.get("Content-Length", 0) or 0)
        downloaded = 0
        with open(file_path, "wb") as out:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress:
                    _print_progress(downloaded, total_size)
    if progress:
        print(flush=True)

    if os.path.isfile(file_path):
        return file_path
    return False

def busybar_workdir_get(subdir = None, suffix_len=4) -> str:
    script_path = os.path.dirname(os.path.abspath(__file__))
    script_hash = hashlib.sha256(script_path.encode()).hexdigest()[:suffix_len]

    # cross-platform way to get a persistent tmp dir
    TMP_SUBDIR = f"{PROJECT_NAME}_{script_hash}"
    if platform.system() == "Windows":
        tmp_dir = os.path.join(os.getenv("TEMP"), TMP_SUBDIR)
    else:
        tmp_dir = os.path.join("/tmp", TMP_SUBDIR)

    if subdir is not None:
        tmp_dir = os.path.join(tmp_dir, subdir)

    os.makedirs(tmp_dir, exist_ok=True)

    logging.debug(f"Workdir: {tmp_dir}")

    return tmp_dir

def url_to_dir_name(url: str) -> str:
    base = re.sub(r'[^a-z0-9_]+', '_', url.lower())
    base = re.sub(r'_+', '_', base).strip('_') or '_'

    # Cleaning:
    base = base.replace('https_', '')
    base = base.replace('http_', '')
    base = base.replace('update_flipperzero_one_builds_', '')
    base = base.replace('update_busy_app_builds_', '')
    # TODO: calc from actual URL dynamically UPDATE_SERVER_BASE
    # https://update.busy.app/builds/busybar-firmware/
    

    base = base[:64]    # Crop to 64 chars

    h = hashlib.sha256(url.encode('utf-8')).hexdigest()[:8]
    return f"{base}_{h}"


def fetch_url(url, timeout=FETCH_TIMEOUT_DEFAULT):
    try:
        with request.urlopen(_make_request(url), timeout=timeout) as response:
            if response.status == 200:
                return response.read().decode()
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
    return None


# def busybar_api_update(device_ip, upd_bundle_tar, verbose=True):
#     logging.info(f"Uploading {upd_bundle_tar} to {device_ip}")
#     url = f"http://{device_ip}/api/update"
#     parsed = urlparse(url)

#     conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80)

#     with open(upd_bundle_tar, "rb") as f:
#         data = f.read()

#     headers = {
#         "Content-Type": "application/octet-stream",
#         "Content-Length": str(len(data)),
#     }

#     conn.request("POST", parsed.path, body=data, headers=headers)
#     response = conn.getresponse()

#     if verbose:
#         print("Status:", response.status, response.reason)
#         print("Headers:")
#         for k, v in response.getheaders():
#             print(f"  {k}: {v}")
#         print("Body:")
        
#         print(response.read().decode(errors="replace"))

#     conn.close()

#     return response.status


def busybar_api_update(device_ip, upd_bundle_tar, verbose=True):
    logging.info(f"Uploading {upd_bundle_tar} to {device_ip}")
    url = f"http://{device_ip}/api/update"
    parsed = urlparse(url)

    total_size = os.path.getsize(upd_bundle_tar)

    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80)
    try:
        conn.putrequest("POST", parsed.path or "/")
        conn.putheader("Content-Type", "application/octet-stream")
        conn.putheader("Content-Length", str(total_size))
        conn.endheaders()

        sent = 0
        chunk_size = 65536
        last_percent = -1

        with open(upd_bundle_tar, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                conn.send(chunk)
                sent += len(chunk)

                percent = int(sent * 100 / total_size) if total_size else 100
                if percent != last_percent:
                    if verbose:
                        print(f"\rUpload via HTTP: {percent:3d}%", end="", file=sys.stdout, flush=True)
                    last_percent = percent

        if last_percent >= 0:
            if verbose:
                print(file=sys.stdout, flush=True)

        response = conn.getresponse()

        if verbose:
            print("Status:", response.status, response.reason)
            print("Headers:")
            for k, v in response.getheaders():
                print(f"  {k}: {v}")
            print("Body:")
            body = response.read().decode(errors="replace")
            try:
                print_pretty(json.loads(body))
            except json.JSONDecodeError:
                print(body)
        else:
            _ = response.read()

        ret = response.status
        if ret == 200:
            return 0

    finally:
        conn.close()
    
    return 1


def busybar_type_by_filename(filename: str) -> None:
    # example:
    # busybar-f21-sil_firmware-porta_furi-state-02102025-473f0eb6.elf
    # ('f21', 'sil_firmware', 'factory-02102025-01b3a988', None, 'factory-02102025-01b3a988', 'elf')
    # https://github.com/flipperdevices/flipper-update-indexer/blob/cba82ded47e9b3aeb278a7b1925d0fc1faa4113a/indexer/src/models.py#L237
    # regex = re.compile(
    #     r"^busybar-(\w+)-(\w+)-([0-9.]+(-rc)?|(dev-\w+-\w+))\.(\w+)$"
    # )
    # regex = re.compile(
    #     r"^busybar-(\w+)-(\w+)-([0-9.]+(-rc)?|(\w+-\w+-\w+))\.(\w+)$"
    # )
    regex = re.compile(
        r"^busybar-(\w+)-(\w+)-(.*)\.(\w+)$"
    )
    match = regex.match(filename)
    if not match:
        exception_msg = f"Unknown file {filename}"
        logging.exception(exception_msg)
        raise Exception(exception_msg)
    # print_pretty(match.groups())
    type = match.group(2) + "_" + match.group(4)
    return type

def busybar_update_get_index_file_name(target_num):
    return f"busybar-f{int(target_num)}-sha256sum.txt"

def busybar_update_parse_index(index_data, url_base):
    files = []
    lines = index_data.splitlines()
    for line in lines:
        hash, filename = line.split(maxsplit=1)
        hash = hash.strip()
        filename = os.path.basename(filename.strip())

        file = {
            "sha256sum": hash,
            "file_name": filename,
            "file_url": url_base + filename,
            "file_type": busybar_type_by_filename(filename)
        }
        files.append(file)

    return files

def busybar_update_url_normalize(branch):
    if branch.startswith("https://"):
        url = branch
    elif branch.startswith("http://"):
        url = branch
    else:
        if branch.startswith("/"):
            branch = branch[1:]

        if UPDATE_SERVER_BASE.endswith('/'):
            url = UPDATE_SERVER_BASE + branch
        else:
            url = UPDATE_SERVER_BASE + '/' + branch

    if not url.endswith('/'):
        url += '/'

    return url

def file_sha256(file_path):
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        logging.warning(f"Can't calculate SHA256 for {file_path}: {e}")
    return None

def bundle_download(files, dir):
    os.makedirs(dir, exist_ok=True)
    
    for file in files:
        if file_download(file, dir):
            print("OK")
        else:
            print(f"Failed!")

