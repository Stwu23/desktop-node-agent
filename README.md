# desktop-node-agent

A small authenticated HTTP agent for a desktop/GPU node, meant to be reached over Tailscale.

- `GET /status`: CPU, memory, disk, and GPU usage, plus running jobs
- `POST /run` with `{"job": "train"}`: start a whitelisted job (the commands are defined locally in `JOBS`)
- `GET /jobs/{id}`: job state, exit code, and the last 20 log lines

## Run

```bash
pip install -r requirements.txt
AGENT_TOKEN=change-me uvicorn agent:app --host <tailscale-ip> --port 8765
```

Every request needs the header `Authorization: Bearer $AGENT_TOKEN`.
