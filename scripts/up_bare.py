import subprocess
import time
import os

os.makedirs("run", exist_ok=True)
os.makedirs("reports", exist_ok=True)
for f in ["run/region-a.pid", "run/region-b.pid", "run/edge.pid"]:
    open(f, "w").close()

def start_region(region, port):
    env = os.environ.copy()
    env["REGION"] = region
    env["STATE_DIR"] = f"state/region-{region}"
    env["WARMUP_SECONDS"] = "6"
    p = subprocess.Popen(["python", "-m", "uvicorn", "serving.app:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"], env=env, stdout=open(f"run/region-{region}.log", "w"), stderr=subprocess.STDOUT)
    with open(f"run/region-{region}.pid", "w") as f:
        f.write(str(p.pid))
    print(f"region-{region} pid={p.pid} port={port}")

start_region("a", 8001)
start_region("b", 8002)

env = os.environ.copy()
env["EDGE_TTL_SECONDS"] = "5"
p_edge = subprocess.Popen(["python", "-m", "uvicorn", "edge.proxy:app", "--host", "127.0.0.1", "--port", "8080", "--log-level", "warning"], env=env, stdout=open("run/edge.log", "w"), stderr=subprocess.STDOUT)
with open("run/edge.pid", "w") as f:
    f.write(str(p_edge.pid))
print(f"edge pid={p_edge.pid} port=8080")

import urllib.request
print("cho service len (toi da 10s)...")
for name, port in [("region-a", 8001), ("region-b", 8002), ("edge", 8080)]:
    up = False
    for _ in range(10):
        try:
            if name == "edge":
                urllib.request.urlopen(f"http://127.0.0.1:{port}/edge/state").read()
            else:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz").read()
            up = True
            break
        except:
            time.sleep(1)
    if up:
        print(f"  {name} (port {port}): UP")
    else:
        print(f"  {name} (port {port}): KHONG PHAN HOI")
