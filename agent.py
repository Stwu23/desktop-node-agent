"""Node agent for the desktop: /status, /run, /jobs/{id}
Run:  AGENT_TOKEN=xxx uvicorn agent:app --host <tailscale-ip> --port 8765
Deps: pip install fastapi uvicorn psutil
"""
import os, shutil, subprocess, threading, uuid
from collections import deque

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

TOKEN = os.environ["AGENT_TOKEN"]

# Whitelist: the model can only pick a job name; the command lives here, locally.
JOBS = {
    "train":  ["bash", os.path.expanduser("~/scripts/train.sh")],
    "backup": ["bash", os.path.expanduser("~/scripts/backup.sh")],
}

app = FastAPI()
jobs: dict[str, dict] = {}


def auth(authorization: str = Header(default="")):
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "bad token")


def gpu_info():
    if not shutil.which("nvidia-smi"):
        return None
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip()
    gpus = []
    for line in out.splitlines():
        name, util, used, total = [x.strip() for x in line.split(",")]
        gpus.append({"name": name, "util_pct": int(util),
                     "mem_used_mb": int(used), "mem_total_mb": int(total)})
    return gpus


@app.get("/status", dependencies=[Depends(auth)])
def status():
    return {
        "cpu_pct": psutil.cpu_percent(interval=0.5),
        "mem_pct": psutil.virtual_memory().percent,
        "disk_pct": psutil.disk_usage(os.path.expanduser("~")).percent,
        "gpu": gpu_info(),
        "running_jobs": [j for j, v in jobs.items() if v["state"] == "running"],
    }


class RunReq(BaseModel):
    job: str


def _worker(job_id: str, cmd: list[str]):
    rec = jobs[job_id]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        rec["log"].append(line.rstrip())
    rec["exit_code"] = proc.wait()
    rec["state"] = "done" if rec["exit_code"] == 0 else "failed"


@app.post("/run", dependencies=[Depends(auth)])
def run(req: RunReq):
    if req.job not in JOBS:
        raise HTTPException(400, f"job not allowed: {req.job}")
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"job": req.job, "state": "running", "exit_code": None,
                    "log": deque(maxlen=50)}
    threading.Thread(target=_worker, args=(job_id, JOBS[req.job]), daemon=True).start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}", dependencies=[Depends(auth)])
def job(job_id: str):
    rec = jobs.get(job_id) or {}
    if not rec:
        raise HTTPException(404, "no such job")
    return {"job": rec["job"], "state": rec["state"], "exit_code": rec["exit_code"],
            "log_tail": list(rec["log"])[-20:]}
