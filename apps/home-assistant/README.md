# Home Assistant

Local control of the Calex (Tuya) lamps and monitoring of the Itho Daalderop boiler. The phases,
decisions and open steps are in [docs/home-assistant-plan.md](../../docs/home-assistant-plan.md).

- **Reached at:** https://homeassistant.lan.gemberkoekje.nl (Caddy, LAN and Tailscale only), or
  directly at http://192.168.1.201:8123. Other cluster apps:
  `http://homeassistant.home-automation.svc.cluster.local:8123`.
- **Image:** `ghcr.io/home-assistant/home-assistant:<release>`, pinned in
  [deployment.yaml](deployment.yaml) (twice: the app and its `prepare-config` init container).
- **Runs on gembernode-01**, on the node's own network (`hostNetwork`), so discovery works. Its
  namespace's pod security level is therefore `privileged`.

| What | Where |
|---|---|
| `configuration.yaml` | [configuration.yaml](configuration.yaml) in Git, mounted read-only. Change it here, never in the pod |
| Everything set up in the UI (`.storage`), HACS and what it installs | PVC `homeassistant-config` (local-path on gembernode-01) |
| Automations, scripts and scenes made in the UI | `automations.yaml`, `scripts.yaml`, `scenes.yaml` on the same PVC |
| History, logbook, statistics (the recorder) | Database `homeassistant` on the shared PostgreSQL |
| Backups | `/config/backups`: PVC `homeassistant-backups` on the NAS |
| Secrets | 1Password item `homeassistant-secrets` |

## Before the first deploy

Do both before the PR merges. A missing 1Password item keeps the pod in
`CreateContainerConfigError`, and the cluster's "pod stuck" alerts start emailing after 15
minutes.

### 1. Database and login on the shared PostgreSQL

In DBeaver: open [create-database.sql](create-database.sql) on a connection to the database
`postgres` as `postgres`, with auto-commit on, and follow its steps (it makes the password too).
Or in psql:

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
CREATE ROLE homeassistant LOGIN;
\password homeassistant
CREATE DATABASE homeassistant OWNER homeassistant;
REVOKE CONNECT, TEMPORARY ON DATABASE homeassistant FROM PUBLIC;
```

Make the password with `openssl rand -hex 32` (hex keeps the URL below valid). Home Assistant
creates its own tables at its first start.

### 2. The 1Password item

Item `homeassistant-secrets` in the Gembercluster vault, with exactly this field label:

- `RECORDER_DB_URL`:
  `postgresql://homeassistant:<password from step 1>@postgresql.flux-system.svc.cluster.local:5432/homeassistant`

A new field's label defaults to `text`: rename it, or the Secret gets the key `text` and the pod
waits in `CreateContainerConfigError`.

## Deploying

```bash
flux reconcile kustomization flux-system --with-source
kubectl -n home-automation get pods,pvc -o wide        # 1/1 Running on gembernode-01, both PVCs Bound
kubectl -n home-automation logs deploy/homeassistant -c prepare-config   # "HACS 2.0.5 installed"
curl -sI https://homeassistant.lan.gemberkoekje.nl     # 302 to /onboarding.html before onboarding
```

Then open https://homeassistant.lan.gemberkoekje.nl and onboard (plan, phase 2).

If every page through Caddy answers **400: Bad Request**, Home Assistant doesn't trust the address
Caddy's requests arrive from. Its log names it:

```bash
kubectl -n home-automation logs deploy/homeassistant | grep "untrusted proxy"
```

Add that address to `trusted_proxies` in [configuration.yaml](configuration.yaml).

## Updating

- **Home Assistant:** bump the tag in both places in [deployment.yaml](deployment.yaml). Read the
  release notes' breaking changes first; a new release may migrate the recorder's tables, which
  takes a few minutes on the first start.
- **HACS** updates itself from its own page once installed. The version and checksum in
  `deployment.yaml` only matter for a fresh volume. To change them, download the release's
  `hacs.zip` and use its `sha256sum`.
- **`configuration.yaml`:** edit it here; the content-hashed ConfigMap restarts Home Assistant.

## Restoring onto a fresh volume

The PVC lives on gembernode-01's disk. If that disk is lost, or Home Assistant has to move, restore
from the NAS: on a fresh install, onboarding offers **Restore from backup**; upload the newest
`.tar` from the QNAP share `gembernodes-pvcs/home-automation/homeassistant-backups/`. History is in
PostgreSQL and isn't in these backups; the nightly database dump covers it. To move to another node,
change the `nodeSelector` and delete the PVC `homeassistant-config` (Flux doesn't prune it) so it is
made again there.
