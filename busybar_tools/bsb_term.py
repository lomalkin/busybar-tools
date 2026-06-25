import socket
import sys
import select
import platform
import threading
import time

if platform.system() != "Windows":
    import termios
    import tty
else:
    import msvcrt

# socat alternative: socat STDIO,raw,echo=0,opost=1,onlcr=1,escape=0x1d TCP:10.0.4.20:23,crnl

ESCAPE_BYTE = b'\x1d'  # Ctrl+] to exit


CLI_PROMPT = b">: "


def _prelude_bytes(prelude):
    """Encode a prelude command string for the device: normalize newlines to CRLF
    and ensure a trailing CRLF so the last command is executed."""
    if not prelude:
        return b""
    text = prelude.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text.replace("\n", "\r\n").encode("utf-8")


def _inject_prelude(sock, prelude, ready_timeout=3.0):
    """Wait for the device CLI to be ready, then send prelude commands into the session.

    The CLI drops input received before its prompt appears, so we first elicit a prompt
    (send CR) and read until it shows up (echoing the banner), then inject the commands.
    """
    pre = _prelude_bytes(prelude)
    if not pre:
        return
    try:
        sock.sendall(b"\r")
        sock.settimeout(ready_timeout)
        buf = b""
        while CLI_PROMPT not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            buf += chunk
    except (OSError, socket.timeout):
        pass
    finally:
        sock.settimeout(None)
    sock.sendall(pre)


def _run_session_posix(host: str, port: int, tcp_timeout: int, prelude=None) -> None:
    fd = sys.stdin.fileno()
    orig_attrs = termios.tcgetattr(fd)

    try:
        attrs = termios.tcgetattr(fd)
        lflag = attrs[3]
        lflag &= ~termios.ICANON
        lflag &= ~termios.ECHO
        lflag &= ~termios.ISIG
        attrs[3] = lflag
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)

        # Connect TCP
        sock = socket.create_connection((host, port), timeout=tcp_timeout)

        # Inject prelude commands into the same session before going interactive.
        _inject_prelude(sock, prelude)

        # Main loop
        while True:
            rlist, _, _ = select.select([sys.stdin, sock], [], [])

            # Data from stdin
            if sys.stdin in rlist:
                # Read all available data to avoid breaking escape sequences
                data = sys.stdin.buffer.read1(4096)
                if not data:
                    # EOF on stdin
                    break

                # Check for local escape character
                if ESCAPE_BYTE in data:
                    # Local escape: close connection and exit
                    break
                sock.sendall(data.replace(b"\n", b"\r\n"))

            # Data from socket
            if sock in rlist:
                data = sock.recv(4096)
                if not data:
                    # Connection closed
                    break
                # Just write to stdout as-is
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()

        sock.close()

    finally:
        # Restore terminal attributes
        termios.tcsetattr(fd, termios.TCSADRAIN, orig_attrs)


def _enable_windows_vt_mode() -> bool:
    # Make the Windows console interpret ANSI escape sequences instead of
    # printing them as literal characters. Available since Windows 10 1511.
    import ctypes
    from ctypes import wintypes

    STD_OUTPUT_HANDLE = -11
    ENABLE_PROCESSED_OUTPUT = 0x0001
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        if handle in (0, INVALID_HANDLE_VALUE):
            return False
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        new_mode = mode.value | ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, new_mode))
    except Exception:
        return False


def _run_session_windows(host: str, port: int, tcp_timeout: int, prelude=None) -> None:
    # Map Windows extended key scan codes to ANSI escape sequences
    _EXT_KEY_MAP = {
        "\x48": b"\x1b[A",   # Up arrow
        "\x50": b"\x1b[B",   # Down arrow
        "\x4d": b"\x1b[C",   # Right arrow
        "\x4b": b"\x1b[D",   # Left arrow
        "\x47": b"\x1b[H",   # Home
        "\x4f": b"\x1b[F",   # End
        "\x49": b"\x1b[5~",  # Page Up
        "\x51": b"\x1b[6~",  # Page Down
        "\x53": b"\x1b[3~",  # Delete
    }

    sock = socket.create_connection((host, port), timeout=tcp_timeout)
    _inject_prelude(sock, prelude)
    stop_event = threading.Event()
    try:
        def _listener():
            while not stop_event.is_set():
                try:
                    readable, _, _ = select.select([sock], [], [], 0.05)
                    if readable:
                        data = sock.recv(4096)
                        if not data:
                            print("*** Connection closed by remote host ***")
                            stop_event.set()
                            return
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                except OSError:
                    stop_event.set()
                    return

        listener = threading.Thread(target=_listener, daemon=True)
        listener.start()

        while not stop_event.is_set():
            if not msvcrt.kbhit():
                time.sleep(0.02)
                continue

            ch = msvcrt.getwch()

            if ch == "\x1d":   # Ctrl+] — exit
                break

            if ch in ("\x00", "\xe0"):
                # Windows extended key: second byte always follows immediately
                code = msvcrt.getwch()
                ansi = _EXT_KEY_MAP.get(code)
                if ansi:
                    sock.sendall(ansi)
                continue

            if ch == "\r":
                sock.sendall(b"\r\n")
                continue

            sock.sendall(ch.encode("utf-8"))
    finally:
        stop_event.set()
        sock.close()

def run_session(host: str, port: int, tcp_timeout: int, prelude=None) -> None:
    if platform.system() == "Windows":
        _run_session_windows(host, port, tcp_timeout, prelude=prelude)
    else:
        _run_session_posix(host, port, tcp_timeout, prelude=prelude)


# if __name__ == "__main__":
#     run_session("10.0.4.20", 23)
