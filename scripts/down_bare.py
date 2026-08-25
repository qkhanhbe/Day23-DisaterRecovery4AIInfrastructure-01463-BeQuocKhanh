import os
import signal

for r in ["region-a", "region-b", "edge"]:
    try:
        pid = int(open(f"run/{r}.pid").read())
        os.kill(pid, signal.SIGTERM)
        print(f"Killed {r} (pid {pid})")
    except Exception as e:
        pass
