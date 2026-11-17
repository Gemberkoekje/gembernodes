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
| Everything set up in the UI (`.storage`), and what the Marketplace installs (`custom_components`) | PVC `homeassistant-config` (local-path on gembernode-01) |
| HTTP server settings: trusted proxies for Caddy, IP bans | The UI (Settings → System → Network), so `.storage` on that PVC. Values [below](#http-server-settings) |
| Automations, scripts and scenes made in the UI | `automations.yaml`, `scripts.yaml`, `scenes.yaml` on the same PVC |
| History, logbook, statistics (the recorder) | Database `homeassistant` on the shared PostgreSQL |
| Backups | `/config/backups`: PVC `homeassistant-backups` on the NAS |
| Secrets | 1Password item `homeassistant-secrets` |
| Our own Tuya Local device definitions | [tuya-local/](tuya-local/) in Git, copied into Tuya Local on every start (below) |

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
curl -sI https://homeassistant.lan.gemberkoekje.nl     # 302 to /onboarding.html before onboarding
```

Then open https://homeassistant.lan.gemberkoekje.nl and onboard (plan, phase 2).

If every page through Caddy answers **400: Bad Request**, Home Assistant doesn't trust the address
Caddy's requests arrive from, or isn't set up for a proxy at all (a fresh install isn't). Its log
says which:

```bash
kubectl -n home-automation logs deploy/homeassistant | grep -i "proxy"
```

Fix it in the [HTTP server settings](#http-server-settings), from http://192.168.1.201:8123 (no
proxy in the way).

## HTTP server settings

Since 2026.11 these are set in the UI, under **Settings → System → Network** (Dutch UI:
Instellingen → Systeem → Netwerk), and kept in `.storage` on the config volume, so they are in Home
Assistant's backups. They used to be the `http:` block in `configuration.yaml`; the first start
imported that block, after which Home Assistant ignores it (and 2027.2 refuses it), so it is gone
from Git (NOTES.md, 2026-11-17). They should read:

| Setting | Value | Why |
|---|---|---|
| Use X-Forwarded-For | on | Caddy passes the client's address in that header |
| Trusted proxies | `10.42.0.0/16`, `192.168.1.201`, `192.168.1.202`, `192.168.1.203` | Caddy reaches the pod through the Service, which points at gembernode-01's own address (hostNetwork). So a request arrives from Caddy's pod address (the pod network, k3s's default cluster CIDR) when Caddy runs on gembernode-01, and otherwise from the node Caddy runs on: flannel masquerades pod traffic to node addresses. Home Assistant answers 400 to a proxied request from any other address |
| IP ban | on | Bans an address after the failed logins below (`ip_bans.yaml` on the volume; delete its line to lift a ban). With the header above that is the client's address, never Caddy's |
| Login attempts threshold | 5 | Off by default |

**Saving restarts Home Assistant on the new settings as a trial.** An admin then has to confirm
them within 5 minutes; otherwise Home Assistant restarts on the previous settings. Make changes from
http://192.168.1.201:8123, which works whatever the proxy settings say, so you can still reach the
confirmation if Caddy breaks.

**A fresh install** (not restored from a backup) starts with the defaults, which trust no proxy:
every page through Caddy answers 400. Onboard at http://192.168.1.201:8123 and enter these first.

## Updating

- **Home Assistant:** bump the tag in both places in [deployment.yaml](deployment.yaml). Read the
  release notes' breaking changes first; a new release may migrate the recorder's tables, which
  takes a few minutes on the first start.
- **Community integrations** (tuya-local, the Itho integration) update from the **Marketplace**
  (Settings → Marktplaats): HACS, built into Home Assistant since 2026.11. It needs no install.
  Connecting it to GitHub (Settings → Devices & services → Marktplaats → Reconfigure) is only
  needed for custom repositories.
- **`configuration.yaml`:** edit it here; the content-hashed ConfigMap restarts Home Assistant.

## Our own Tuya Local device definitions

Tuya Local recognises a device by a definition file in `custom_components/tuya_local/devices`.
For a device it doesn't know, we keep our own in [tuya-local/](tuya-local/):

| File | Device |
|---|---|
| [joula_diamond_dishwasher.yaml](tuya-local/joula_diamond_dishwasher.yaml) | Joula "Diamond" mini dishwasher, 192.168.1.60 (mapped 2026-11-15; NOTES.md) |

A Tuya Local update from the Marketplace replaces that folder wholesale, so the `prepare-config`
init container copies these files back in on every start. Updates need a restart anyway, so the
files are back before Tuya Local loads. Its log says `installed Tuya Local definition <file>` or
`... is up to date`.

**To add one:** put the file in `tuya-local/`, with a name Tuya Local's own folder doesn't use,
and list it under `homeassistant-tuya-local-devices` in [kustomization.yaml](kustomization.yaml).
Tuya Local can't switch an existing device to another type: after the deploy, remove the device and
add it again, choosing the new type (the top suggestion). A change to an existing file needs
nothing more: the content-hashed ConfigMap restarts Home Assistant, which copies it in first. If
Tuya Local ever ships its own definition for one of these devices, delete ours.

## Restoring onto a fresh volume

The PVC lives on gembernode-01's disk. If that disk is lost, or Home Assistant has to move, restore
from the NAS: on a fresh install, onboarding offers **Restore from backup**; upload the newest
`.tar` from the QNAP share `gembernodes-pvcs/home-automation/homeassistant-backups/`. Onboard at
http://192.168.1.201:8123: until the backup brings back the [HTTP server settings](#http-server-settings),
Caddy's address answers 400. History is in
PostgreSQL and isn't in these backups; the nightly database dump covers it. To move to another node,
change the `nodeSelector` and delete the PVC `homeassistant-config` (Flux doesn't prune it) so it is
made again there.
