import platform
import subprocess
import time


def _ping_command(host, timeout):
    timeout = max(1, int(timeout))
    system = platform.system()
    if system == "Windows":
        return ["ping", "-n", "1", "-w", str(max(1000, timeout * 1000)), host]
    if system == "Darwin":
        return ["ping", "-c", "1", "-t", str(timeout), host]
    return ["ping", "-c", "1", "-W", str(timeout), host]


def network_ping_bool(host, timeout=1, verbose=False):
    try:
        output = subprocess.check_output(
            _ping_command(host, timeout),
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        if verbose:
            print(output)
    except (OSError, subprocess.CalledProcessError):
        return False
    if platform.system() == "Windows":
        output_lower = output.lower()
        if "unreachable" in output_lower or "timed out" in output_lower or "ttl=" not in output_lower:
            return False
    return True


def wait_for_device(ip, timeout=None, verbose=False, delay=1, success_ping_as=True, verbose_in_place=True):
    result = {"ip": ip, "try_counter": 0, "success": False}

    def print_in_place(message):
        print(f"\r\033[K{message}", end="", flush=True)

    started = time.monotonic()
    if verbose and verbose_in_place:
        print_in_place(f"Ping {ip}... ")
    while True:
        ping_result = network_ping_bool(ip, delay)
        elapsed = int(time.monotonic() - started)
        result["try_counter"] += 1
        message = f"{result['try_counter']}: PING {ip} ({elapsed}s)"
        if ping_result == success_ping_as:
            result["success"] = True
            if verbose:
                print_in_place(message + ": OK") if verbose_in_place else print(message + ": OK")
            break
        if verbose:
            print_in_place(message + ": Failed") if verbose_in_place else print(message + ": Failed")
        if timeout is not None and time.monotonic() - started >= timeout:
            break
        time.sleep(delay)
    if verbose and verbose_in_place:
        print()
    return result

