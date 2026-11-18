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
| Secrets | 1Password items `homeassistant-secrets` and `homeassistant-monitoring` (the second shared with `monitoring`) |
| Monitoring: Prometheus reads every entity; Grafana's alerts arrive here and on the phone | [configuration.yaml](configuration.yaml) (`prometheus:`, `automation git:`) and `infrastructure/monitoring`. [Below](#monitoring) |
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

## Monitoring

Two links with `infrastructure/monitoring`, both through Home Assistant's Service:

- **Home Assistant → Prometheus → Grafana.** Home Assistant's Prometheus integration (`prometheus:`
  in [configuration.yaml](configuration.yaml)) publishes every entity's current state at
  `/api/prometheus`. Prometheus reads it every minute (job `homeassistant` in
  `prometheus-release.yaml`) with the token of a Home Assistant user of its own, and keeps it 31
  days. Grafana's **Home Assistant** dashboard draws one graph per metric. Home Assistant names a
  sensor's metric after its device class and unit (`homeassistant_sensor_data_rate_kib_per_s` for
  the router's speeds), so a new device appears by itself. The alert **Prometheus can't read Home
  Assistant** fires after 15 minutes without a scrape.
- **Grafana → Home Assistant.** Every Grafana alert goes by email as before, and also to a Home
  Assistant webhook (contact point Email, in `grafana-alerting-provisioning.yaml`). The automation
  **Grafana alerts** (`automation git:` in [configuration.yaml](configuration.yaml), read-only in
  the UI) shows each one as a notification under the bell and pushes it to every phone with the
  Companion app; when the alert resolves, it clears the notification and replaces the push with
  "Resolved: …". Tapping the push opens Grafana (LAN and Tailscale only).

### Setting it up

Everything starts without these steps; until they're done Prometheus can't read Home Assistant
(that alert emails after 15 minutes) and the alerts only go by email.

1. **A user for Prometheus.** Settings → People → Add person (Dutch UI: Instellingen → Personen →
   Persoon toevoegen): name `Prometheus`, allowed to log in, username `prometheus`, a long random
   password, **not** an administrator. The Prometheus endpoint needs no admin rights.
2. **Its token.** In a private browser window, log in as `prometheus`. Open the profile (bottom
   left) → Security → Long-lived access tokens → Create token, named `Prometheus`, and copy it: it is
   shown once. Log out.
3. **A webhook ID:** `openssl rand -hex 32`.
4. **The 1Password item** `homeassistant-monitoring` in the Gembercluster vault, with exactly these
   field labels (a new field's label defaults to `text`: rename it):
   - `HOMEASSISTANT_TOKEN`: the token from step 2;
   - `GRAFANA_WEBHOOK_ID`: the ID from step 3.
5. **Restart** Home Assistant and Grafana once the operator has made the Secrets (a minute or so),
   so both read the webhook ID:
   ```bash
   kubectl -n home-automation get secret homeassistant-monitoring    # exists in both namespaces
   kubectl -n monitoring get secret homeassistant-monitoring
   kubectl -n home-automation rollout restart deployment homeassistant
   kubectl -n monitoring rollout restart deployment grafana
   ```
   Prometheus reads the token from its file at every scrape. If the dashboard's "Prometheus reads
   Home Assistant" still says No after a few minutes, restart it too
   (`kubectl -n monitoring rollout restart deployment prometheus-server`).

**To check:** the dashboard's top-left panel says Yes. In Grafana, Alerting → Contact points →
Email → Test sends a test alert to both the email address and Home Assistant: a notification
"TestAlert" appears under the bell and on the phone. A test alert never resolves, so dismiss that
one yourself.

### Gotchas

- **A wrong token counts as a failed login.** Five in a row ban the address Prometheus scrapes from
  (a pod address, or a node's when Prometheus runs on another node) in `ip_bans.yaml` on the volume;
  the log says "Login attempt or request with invalid authentication". Fix the token, delete that
  line, restart Home Assistant.
- **Pushes go to every phone** with the Companion app logged in to this Home Assistant
  (`notify.notify` without a target). For one phone, use its own action instead,
  `notify.mobile_app_<phone>` (Developer tools → Actions lists it). A wrong name there fails the
  whole loop, which is why it isn't used.
- **The bell's notifications don't survive a restart** of Home Assistant (they're kept in memory).
  The pushes on the phone stay.
- **Without the 1Password item** the webhook has the placeholder ID `not-configured`, reachable from
  the LAN and Tailscale only, and Grafana posts to an empty ID, which reaches nothing.
- **What is exported:** everything. To leave entities out, add a `filter:` (include or exclude by
  domain, entity or glob) under `prometheus:` in [configuration.yaml](configuration.yaml).

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
