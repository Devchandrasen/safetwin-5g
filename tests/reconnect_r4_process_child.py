"""Local deterministic output/sleep child. No sockets, Docker or user-file access."""
import os
import subprocess
import sys
import time

mode = sys.argv[1]
if mode == "streams":
    os.write(1, b"stdout\n")
    os.write(2, b"stderr\n")
elif mode == "flood":
    while True:
        os.write(1, b"x" * 4096)
        os.write(2, b"y" * 4096)
elif mode == "sleep":
    os.write(1, b"partial-before-timeout\n")
    time.sleep(20)
elif mode == "descendant":
    child = subprocess.Popen([sys.executable, "-I", "-S", __file__, "sleep"], stdout=sys.stdout, stderr=sys.stderr,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    print(child.pid, flush=True)
    # Exit while descendant still holds both inherited output pipes.
elif mode == "invalid-utf8":
    os.write(1, b"valid\xffpartial")
elif mode == "exit-failure":
    print("retained failure", flush=True)
    raise SystemExit(7)
else:
    raise SystemExit(2)
