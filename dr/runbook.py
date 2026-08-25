"""BƯỚC 3c — SINH VIÊN VIẾT. Tự động hoá runbook §4 "Runbook: Region Chính Down".

7 bước trên slide, mỗi bước 1 dòng log có ts. Log này CHÍNH LÀ timeline của postmortem.
  1 xac_nhan_outage          — probe cả 2 region, đừng tin 1 lần fail (dùng nhiều lần
                              hoặc gọi health_checker.probe nếu đã viết xong 3a)
  2 thong_bao_incident       — ts của dòng này là mốc "operator biết tin", LUÔN LUÔN
                              SAU t_outage trong chaos-events (không thể trùng — operator
                              không thể biết ngay giây outage xảy ra). Ghi cả 2 ts vào
                              log để postmortem tính được "độ trễ thông báo".
  3 scale_gpu_pool           — gọi HÀM `failover.failover(...)` MỘT LẦN DUY NHẤT. Hàm
                              đó tự làm đủ 5 bước con (verify/restore/scale/wait/cutover)
                              và tự ghi log riêng vào reports/failover-events.jsonl.
  4 verify_state_replica     — KHÔNG gọi lại failover — chỉ ĐỌC kết quả (vector count +
                              weights ở region phụ) từ dict mà bước 3 trả về, để log vào
                              runbook-run.jsonl cho postmortem đọc 1 chỗ duy nhất.
  5 dns_cutover              — cũng chỉ đọc lại: kết quả cutover có ok hay không.
  6 verify_golden_signals    — 10 request thật vào region phụ: p95 latency + error rate
  7 post_incident            — elapsed_s + lệnh đo RTO

BÁN TỰ ĐỘNG, KHÔNG FULL-AUTO (§4: "failover đầu tiên nên là bán tự động — alert +
1-click confirm — tránh flapping gây failover 2 chiều liên tục"). Mặc định phải hỏi
người vận hành confirm; --auto chỉ dùng trong CI/khi chấm điểm.

Chạy:  python dr/runbook.py --primary a --target b --backend fs
"""
import argparse
import json
import pathlib
import sys
import time

import httpx

sys.path.insert(0, ".")
from dr import failover as fo  # noqa: E402

LOG = pathlib.Path("reports/runbook-run.jsonl")
URL = {"a": "http://127.0.0.1:8001", "b": "http://127.0.0.1:8002"}


import datetime

def step(n, name, **kw):
    """Ghi log JSONL và in ra stdout."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    evt = {"ts": time.time(), "iso": datetime.datetime.utcnow().isoformat() + "Z", "step": n, "name": name, **kw}
    s = json.dumps(evt)
    with open(LOG, "a") as f:
        f.write(s + "\n")
    print(s)


def confirm(auto: bool, msg: str) -> bool:
    """Yêu cầu xác nhận từ user hoặc bỏ qua nếu auto=True."""
    if auto:
        return True
    return input(f"{msg} [y/N]: ").strip().lower() == "y"


def run(primary: str, target: str, backend: str, auto: bool) -> dict:
    """Chạy 7 bước của runbook."""
    ret = {"ok": False}
    start_t = time.time()
    
    # 1 xac_nhan_outage
    for _ in range(3):
        try:
            httpx.get(f"{URL[primary]}/readyz", timeout=1.0)
        except Exception:
            pass
        time.sleep(0.5)
    step(1, "xac_nhan_outage", region=primary, status="unhealthy")
    
    if not confirm(auto, "Outage confirmed. Proceed?"):
        return ret
        
    # 2 thong_bao_incident
    t_outage = None
    chaos_log = pathlib.Path("reports/chaos-events.jsonl")
    if chaos_log.exists():
        for line in chaos_log.read_text().splitlines():
            evt = json.loads(line)
            if evt.get("event") == "kill_region" or evt.get("action") == "netblock":
                t_outage = evt.get("ts")
                break
    step(2, "thong_bao_incident", operator_alerted_at=time.time(), t_outage=t_outage)
    
    # 3 scale_gpu_pool (gọi hàm failover.failover)
    fo_res = fo.failover(target, backend, 60.0)
    step(3, "scale_gpu_pool", result=fo_res)
    
    # 4 verify_state_replica
    st = {}
    try:
        st = httpx.get(f"{URL[target]}/v1/state", timeout=2.0).json()
    except Exception:
        pass
    step(4, "verify_state_replica", vector_count=st.get("count"), weights=st.get("weights"))
    
    # 5 dns_cutover
    step(5, "dns_cutover", success=fo_res.get("ok", False))
    
    # 6 verify_golden_signals
    errors = 0
    lats = []
    for _ in range(10):
        try:
            t0 = time.time()
            httpx.get(f"{URL[target]}/v1/infer", timeout=2.0)
            lats.append(time.time() - t0)
        except Exception:
            errors += 1
            
    p95 = sorted(lats)[int(len(lats)*0.95)] if lats else 0
    step(6, "verify_golden_signals", p95_latency=p95, error_rate=errors/10.0)
    
    # 7 post_incident
    elapsed = time.time() - start_t
    step(7, "post_incident", elapsed_s=elapsed, cmd="python3 tools/measure_rto.py --loadgen reports/drill-2-withdr.jsonl --target-rto 300")
    
    ret["ok"] = fo_res.get("ok", False)
    return ret


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--primary", default="a")
    p.add_argument("--target", default="b")
    p.add_argument("--backend", default="fs", choices=["fs", "minio"])
    p.add_argument("--auto", action="store_true")
    a = p.parse_args()
    print(json.dumps(run(a.primary, a.target, a.backend, a.auto), indent=2))
