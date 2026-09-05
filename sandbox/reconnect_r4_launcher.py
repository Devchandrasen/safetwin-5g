"""Owned subprocess launcher: never create a child before job containment ACK."""
import subprocess
import sys
import os


def main():
    if sys.stdin.buffer.readline(4) != b"GO\n" or len(sys.argv) < 2:
        return 125
    # Pipes are inherited, not buffered in launcher memory. No shell or network API.
    return subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
