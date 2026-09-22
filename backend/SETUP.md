# AI Cloud Orchestrator — Setup Guide

This covers everything needed to stand this project up on a fresh machine,
from prerequisites to daily run commands. Written from real setup
experience (including the issues that came up), so treat the
troubleshooting section as load-bearing, not optional reading.

---

## 1. Prerequisites — what to install

Install these in order. Each command below confirms it worked.

| Tool | Why it's needed | Install from | Verify with |
|---|---|---|---|
| **Docker Desktop** | Runs Kind clusters + Postgres as containers | https://www.docker.com/products/docker-desktop/ | `docker --version` |
| **kind** | Creates local Kubernetes clusters inside Docker | https://kind.sigs.k8s.io/docs/user/quick-start/#installation | `kind --version` |
| **kubectl** | Talks to the Kubernetes clusters | https://kubernetes.io/docs/tasks/tools/ | `kubectl version --client` |
| **Helm** | Installs the Prometheus + kube-state-metrics monitoring stack | https://helm.sh/docs/intro/install/ | `helm version` |
| **Python 3.12+** | Runs the FastAPI backend | https://www.python.org/downloads/ | `python --version` |
| **Node.js 18+** | Runs the React frontend (Vite) | https://nodejs.org/ | `node --version` |

Once Docker Desktop is installed, **open it and make sure it's actually
running** before doing anything else — every other tool depends on it.

### Recommended Docker Desktop resource settings

Go to **Docker Desktop → Settings → Resources** and give it as much
CPU/RAM as your machine can spare. This project runs 2–3 full Kubernetes
control planes plus their monitoring stacks plus Postgres, all at once —
it is genuinely resource-hungry. As a rough guide:

- **Minimum to avoid constant issues:** 4 CPU cores, 8GB RAM allocated to Docker
- **Comfortable:** 6+ CPU cores, 12GB+ RAM allocated to Docker

If your machine only has 2 physical cores, expect intermittent slowness
under load even with plenty of RAM — see the Troubleshooting section.

---

## 2. First-time project setup

Run these once, in order, from the project root.

### Step 1 — Start Postgres
```bash
cd backend
docker compose up -d
```
This starts a Postgres container and automatically runs `db/schema.sql`
then `db/seed.sql` on first startup (creates the `clusters`, `metrics`,
`decisions`, and `predictions` tables, and seeds `cluster-a`,
`cluster-b`, `cluster-c` rows).

Verify it's healthy:
```bash
docker ps
```
You should see `orchestrator-postgres` with a `healthy` status.

### Step 2 — Create the Kind clusters
```bash
bash scripts/create-clusters.sh
```
This creates `cluster-a`, `cluster-b`, `cluster-c` and deploys a small
nginx demo workload into each (so there's something for Prometheus to
scrape). Cluster names must match `db/seed.sql` exactly — don't rename
them unless you also update the seed data.

This step can take several minutes, especially for the first cluster
(Kind has to pull its node image).

### Step 3 — Install monitoring (Prometheus + kube-state-metrics)
```bash
bash scripts/install-monitoring.sh
```
Installs a lightweight Prometheus + kube-state-metrics + node-exporter
into each cluster via Helm (no Alertmanager, no persistent storage —
kept deliberately light since you're running this 2–3x over on one
machine).

### Step 4 — Install backend dependencies
```bash
cd backend
pip install -r requirements.txt --break-system-packages
```
(Drop `--break-system-packages` if you're using a virtual environment,
which is recommended if you plan to keep developing this.)

Copy the example env file if `.env` doesn't already exist:
```bash
# .env should already exist in this repo, but if not:
# DATABASE_URL=postgresql+psycopg://orchestrator:orchestrator_dev_password@localhost:5434/orchestrator
# PROMETHEUS_CLUSTER_A_URL=http://localhost:9090
# PROMETHEUS_CLUSTER_B_URL=http://localhost:9091
# PROMETHEUS_CLUSTER_C_URL=http://localhost:9092
# PROMETHEUS_TIMEOUT_SECONDS=15
```

### Step 5 — Install frontend dependencies
```bash
cd frontend
npm install
```

That's the one-time setup done. From here on, use the daily run sequence
below.

---

## 3. Daily run sequence

This project needs **up to 9 things running at once, in separate
terminal windows**, depending on whether you want live traffic
(req/s, latency) and database persistence, or just cluster health.
Order doesn't strictly matter — the backend reconnects to Prometheus
fresh on every request rather than holding a connection open — but
whichever terminals you do use need to be alive simultaneously.

**Minimum for the dashboard to show cluster health (CPU/mem/pods/nodes):**

**Terminal 1 — Prometheus port-forward, cluster-a:**
```bash
cd backend
kubectl --context kind-cluster-a -n monitoring port-forward svc/prometheus-server 9090:80
```

**Terminal 2 — Prometheus port-forward, cluster-b:**
```bash
cd backend
kubectl --context kind-cluster-b -n monitoring port-forward svc/prometheus-server 9091:80
```

**Terminal 3 — Backend:**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Terminal 4 — Frontend:**
```bash
cd frontend
npm run dev
```

Then open **http://localhost:5173** in your browser.

Verify before assuming it's working — don't just eyeball the frontend:
```bash
netstat -ano | findstr "9090 9091 8081 8082"   # Windows; use `lsof -i` on Mac/Linux
curl http://localhost:9090/api/v1/query?query=up
curl http://localhost:9091/api/v1/query?query=up
curl http://localhost:8000/clusters
```
`GET /clusters` should return `cluster-a` and `cluster-b` as `"status":"healthy"`
with real numbers, and `cluster-c` as `"status":"unreachable"` with `null`
fields (this is correct — cluster-c is intentionally not implemented yet,
not a bug).

**Additional terminals — only needed for live req/s + latency numbers:**

**Terminal 5 — workload port-forward, cluster-a:**
```bash
kubectl --context kind-cluster-a -n default port-forward svc/demo-workload 8082:80
```

**Terminal 6 — workload port-forward, cluster-b:**
```bash
kubectl --context kind-cluster-b -n default port-forward svc/demo-workload 8081:80
```

**Terminal 7 — k6 traffic, whichever cluster you're testing:**
```bash
cd backend
$env:CLUSTER="cluster-b"
$env:PROFILE="smoke"
$env:TARGET_URL="http://localhost:8081"
$env:K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9091/api/v1/write"
$env:K6_PROMETHEUS_RW_FLUSH_PERIOD="15s"
$env:K6_PROMETHEUS_RW_TREND_STATS="p(95),p(99)"
k6 run -o experimental-prometheus-rw load-tests/traffic.js
```
Swap `CLUSTER`, `TARGET_URL` (8082 for cluster-a, 8081 for cluster-b),
and `K6_PROMETHEUS_RW_SERVER_URL` (9090 for cluster-a, 9091 for
cluster-b) to target the other cluster. `req/s` and `latency` on the
dashboard only populate while (or shortly after) k6 is actively
running — `—` on those fields the rest of the time is expected, not
broken.

**Optional — Terminal 8, poller (writes metrics to the database):**
```bash
cd backend
python -m app.poller
```
Not required for the live dashboard (which queries Prometheus directly,
not the database) — only needed if you're persisting history for later
analysis or feeding the prediction/orchestration layer once that's built.

Leave whichever terminals you're using open and running — closing any
one of them will break that piece. If you close everything and come
back later, just repeat the relevant steps above; nothing needs to be
reinstalled, only restarted. **Port-forwards do not survive closing
their terminal** — if you get a `connection refused` on any of
9090/9091/8081/8082, that port-forward simply isn't running anymore
and needs to be started fresh (`docker update --cpus` settings and the
Kind clusters themselves persist fine; only the `kubectl port-forward`
processes die with their terminal).

### Shutting down for the day
Ctrl+C in terminals 1–4 to stop the port-forwards, backend, and
frontend. Postgres and the Kind clusters keep running in the background
(as Docker containers) unless you stop them explicitly:
```bash
docker compose -f backend/docker-compose.yml down    # stops Postgres (keeps data)
kind delete cluster --name cluster-a                  # deletes a cluster entirely
```
Usually there's no need to tear these down between sessions — just leave
Docker Desktop running and pick up again with the 4-terminal sequence
above.

---

## 4. Troubleshooting

These are real issues encountered during development, kept here so they
don't have to be re-diagnosed from scratch.

### Dashboard stuck on "Loading clusters…" / requests show `(canceled)` in DevTools Network tab
Almost always means one of the 4 required terminals isn't actually
running, or the backend is responding slower than the frontend's
timeout allows. Check, in order:
1. Are all 4 terminals from section 3 still alive and error-free?
2. In the backend terminal, does reloading the page produce a new
   `GET /clusters` log line? If not, the request isn't reaching the
   backend at all (check terminal 3 and 4 are really running).
3. If it does log a request but it's slow, this is very likely CPU/RAM
   pressure on your machine — see "Everything is slow / hangs
   intermittently" below.

### `Prometheus` port-forward drops with "connection refused" repeatedly
Usually means the Prometheus pod itself is restarting due to resource
pressure. Check pod health:
```bash
kubectl --context kind-cluster-a -n monitoring get pods
```
If `RESTARTS` is climbing, see "Everything is slow" below.

### `kubectl` fails with a TLS "certificate signed by unknown authority" error
This can happen after Docker Desktop restarts, even though the
certificate itself isn't expired or broken — the running API server
process and what's on disk can drift out of sync. Fix:
```bash
docker restart cluster-a-control-plane
# wait ~30-60 seconds
kubectl --context kind-cluster-a get nodes
```
If it still errors (e.g. `Forbidden: unknown`), the API server was
mid-restart — repeat the same two commands once more. It should come
back clean on the second pass. Do the same for `cluster-b-control-plane`
/ `kind-cluster-b` if needed.

### The workload Service is called `demo-workload`, not `nginx`
Easy to assume it's named `nginx` since that's the image/welcome page
you see when you curl it — it isn't. Confirm the real name before
port-forwarding:
```bash
kubectl --context kind-cluster-a get svc -A
```
It's `demo-workload` in the `default` namespace (not `monitoring`) on
both clusters.

### k6's `TARGET_URL` env var appears to do nothing
`load-tests/traffic.js` originally hardcoded a `TARGETS` lookup table
keyed by `CLUSTER` (`cluster-a` → `:8080`, `cluster-b` → `:8081`,
`cluster-c` → `:8082`) and never actually read `__ENV.TARGET_URL` at
all — setting the env var silently had no effect, and whichever port
you'd actually forwarded could easily not match the hardcoded value.
Fixed in the script:
```js
// was:
const TARGET_URL = TARGETS[CLUSTER];
// now:
const TARGET_URL = __ENV.TARGET_URL || TARGETS[CLUSTER];
```
`$env:TARGET_URL` now genuinely overrides the per-cluster default; if
you don't set it, the old hardcoded ports still apply as a fallback.
If you see every single k6 request refused against a port you're sure
you forwarded, check this hasn't regressed and that you're using the
port you actually forwarded, not whatever's hardcoded in `TARGETS`.

### `GET /clusters` returns 500, or the dashboard is blank with console errors
Check `app/routers/clusters.py` for a `KeyError` on `live["latency_ms"]`.
`cluster_metrics()` in `app/prometheus.py` returns the key as
`p99_latency_ms`, not `latency_ms` — the live-dashboard endpoint must
read `live["p99_latency_ms"]`. (The separate `/clusters/{id}/metrics`
history endpoint reading from the database is unaffected — the DB
column really is named `latency_ms`, so don't "fix" that one.)

### Backend crashes with `ValueError: Out of range float values are not JSON compliant: nan`
Prometheus can occasionally return `NaN` (e.g. a query briefly divides
by zero right after a cluster restart). Already patched in
`backend/app/prometheus.py` — the `query()` function checks for `NaN`
and returns `None` instead. If you see this again, confirm that fix is
still in place.

### Everything is slow / hangs intermittently / clusters flip to "unreachable" randomly
This is very likely **CPU or RAM contention on the host machine**, not
a bug in the code. Symptoms seen during development: control-plane
containers spiking to 100%+ CPU each, Prometheus alternating between
instant responses and full hangs, pods restarting dozens of times.

Check current load:
```bash
docker stats --no-stream
```
If `cluster-a-control-plane` / `cluster-b-control-plane` are individually
near or over 100% CPU, the host doesn't have enough spare compute for
everything running at once (2-3 Kubernetes control planes + Prometheus
stacks + Postgres + your dev tools, all competing for the same cores).

Mitigations, roughly in order of effort:
- Close unused apps/browser tabs, especially DevTools, while doing
  heavy cluster work
- Only run one cluster's monitoring stack at a time if you don't need
  both simultaneously
- Raise `PROMETHEUS_TIMEOUT_SECONDS` in `.env` (currently `15`) if
  Prometheus is just slow rather than fully hung
- Give Docker Desktop more CPU/RAM in its settings, if your machine has
  more to give
- On a 2-physical-core machine, expect this to keep happening under
  heavy load regardless of RAM — CPU cores are the harder ceiling. More
  RAM helps (fewer OOM-driven restarts) but doesn't remove CPU
  contention. A machine with more cores resolves this class of issue
  much more completely than RAM alone.

### Docker Desktop shows a "backend" container with 0% CPU and no ports
This is not the FastAPI backend (which runs directly on the host via
`uvicorn`, not in Docker). It's a leftover/unrelated Compose project
grouping in the Docker Desktop UI and can be ignored. Run `docker ps`
directly for the accurate, unambiguous container list.

### Port-forwards die with `wsarecv: An existing connection was forcibly closed by the remote host` (Windows)
Seen on Prometheus and workload port-forwards alike, on both clusters.
Usually self-recovers (`Handling connection for ####` resumes right
after) and doesn't corrupt the k6/poller run in progress — but it's a
real symptom of CPU/WSL2 memory contention, not just network noise.
Check `docker stats --no-stream` and `wsl -d Ubuntu -- free -h` when it
happens repeatedly. See "Everything is slow" below for the underlying
fix. Treat isolated blips as background noise; treat a port-forward
that stops recovering (no more `Handling connection` lines, ever) as a
real failure requiring a restart of that specific `kubectl port-forward`.

### Running cluster-a and cluster-b simultaneously — CPU caps required
Two full Kind control planes with **no CPU limit** will fight each
other for cores and both lose, even on a reasonably specced machine.
Symptom: `docker stats --no-stream` shows both control-plane containers
pinned at 100%+ CPU simultaneously, kube-state-metrics pods restarting
dozens of times, port-forwards dying mid-session on both clusters at once.

Fix — cap each Kind node container's CPU so they share fairly instead
of fighting:
```bash
docker update --cpus 1.5 cluster-a-control-plane
docker update --cpus 1.5 cluster-b-control-plane
```
Adjust the number based on your `docker info --format "{{.NCPU}}"` —
leave at least ~1 core free for Docker Desktop/WSL2 overhead and your
own dev tools. This survives container restarts but **does not survive
`kind delete cluster` + recreate** — reapply after recreating clusters.

Verify it took:
```bash
docker inspect cluster-a-control-plane --format "{{.HostConfig.NanoCpus}}"
docker inspect cluster-b-control-plane --format "{{.HostConfig.NanoCpus}}"
```

Additionally, cap the Prometheus-stack deployments themselves inside
each cluster so no single pod can still monopolize its share of the
capped host CPU (apply to `prometheus-server`, `kube-state-metrics`,
and `prometheus-kube-state-metrics`, in both clusters — 6 patches total).
On Windows PowerShell, inline `-p '{"...":...}'` JSON reliably fails to
parse even with correct quoting — write a patch file instead:
```powershell
@'
[{"op":"add","path":"/spec/template/spec/containers/0/resources","value":{"requests":{"cpu":"200m","memory":"256Mi"},"limits":{"cpu":"500m","memory":"512Mi"}}}]
'@ | Out-File -FilePath patch.json -Encoding utf8 -NoNewline

kubectl --context kind-cluster-a -n monitoring patch deployment prometheus-server --type=json --patch-file=patch.json
```
Use smaller values (`100m`/`128Mi` requests, `300m`/`256Mi` limits) for
`kube-state-metrics` and `prometheus-kube-state-metrics`, which are
lighter workloads.

### `kube-controller-manager` / `kube-scheduler` stuck in `CrashLoopBackOff` with a high, climbing restart count
**This is the single most impactful fix found during development** — it
was silently running for 35+ hours before being caught, degrading
reliability across everything (Prometheus, k6, the dashboard) without
an obvious root cause pointing to it directly.

Diagnose:
```bash
kubectl --context kind-cluster-a -n kube-system get pods
kubectl --context kind-cluster-a -n kube-system logs kube-controller-manager-cluster-a-control-plane --previous --tail=50
```
Look for `"Error retrieving lease lock" err="client rate limiter Wait
returned an error: context deadline exceeded"` and `"Failed to renew
lease"` / `"leaderelection lost/stopped"`. This means the apiserver
took too long to answer a leader-election lease renewal within the
default ~10s window — by design, the controller/scheduler immediately
exits rather than risk running as a duplicate leader. Root cause is the
same CPU contention as above: two control planes sharing limited cores
makes the apiserver occasionally too slow to answer in time, even
though nothing is "broken" per se.

Fix — loosen the leader-election timeouts on both `kube-controller-manager`
and `kube-scheduler`, on **both clusters**, so brief apiserver slowness
doesn't immediately kill them:
```bash
docker exec cluster-a-control-plane sh -c "sed -i '/- kube-controller-manager/a\    - --leader-elect-lease-duration=60s\n    - --leader-elect-renew-deadline=45s\n    - --leader-elect-retry-period=10s' /etc/kubernetes/manifests/kube-controller-manager.yaml"
docker exec cluster-a-control-plane sh -c "sed -i '/- kube-scheduler/a\    - --leader-elect-lease-duration=60s\n    - --leader-elect-renew-deadline=45s\n    - --leader-elect-retry-period=10s' /etc/kubernetes/manifests/kube-scheduler.yaml"
```
Repeat for `cluster-b-control-plane`. The kubelet watches
`/etc/kubernetes/manifests/` and auto-restarts these static pods when
the files change — no manual restart needed, though it can take
20–30 seconds to pick up the change. Verify:
```bash
kubectl --context kind-cluster-a -n kube-system get pods
```
Both pods should show `1/1 Running` with `RESTARTS: 0` on the new pod
instance. Watch it hold under real load (`-w` to tail live):
```bash
kubectl --context kind-cluster-a -n kube-system get pods -w
```

This fix is written directly to each container's filesystem and
**survives container restarts**, but like the CPU caps above, does
**not survive `kind delete cluster` + recreate** — a fresh cluster
starts from kubeadm's default manifests without these flags, so
reapply after recreating.

### Everything is slow / hangs intermittently / clusters flip to "unreachable" randomly

## 5. Project structure reference

```
ai cloud/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, CORS config
│   │   ├── database.py      # SQLAlchemy session setup
│   │   ├── models.py        # ORM models (Cluster, Metric, ...)
│   │   ├── prometheus.py    # Prometheus query client
│   │   └── routers/
│   │       └── clusters.py  # GET /clusters, GET /clusters/{id}/metrics
│   ├── db/
│   │   ├── schema.sql       # Table definitions (auto-run by Postgres on first start)
│   │   └── seed.sql         # Initial cluster rows (auto-run after schema.sql)
│   ├── scripts/
│   │   ├── create-clusters.sh
│   │   ├── install-monitoring.sh
│   │   └── delete-clusters.sh
│   ├── docker-compose.yml   # Postgres container definition
│   ├── requirements.txt
│   └── .env                 # DB connection + Prometheus URLs (not committed if using .gitignore)
└── frontend/
    ├── src/
    │   ├── App.jsx           # Polling logic + layout
    │   ├── api.js             # All backend calls + response shapes live here
    │   └── components/
    │       ├── ClusterCard.jsx
    │       └── MetricsChart.jsx
    └── package.json
```