# Home Assistant on gembernodes

**Status: phase 1 deployed (2026-11-12).** HA runs on gembernode-01 and answers at
https://homeassistant.lan.gemberkoekje.nl, waiting for onboarding. The manifests are in
[apps/home-assistant/](../apps/home-assistant/), with a [README](../apps/home-assistant/README.md).
Phases 2–6 are still to do; phase 2 is next. This plan started as
`home-assistant-plan.md` in Gemberkoekje/projects; where building phase 1 changed it, "Changed
while building" says so.

Goal: run Home Assistant (HA) on the k3s cluster, get **local control** of the Calex lamps, and
**monitoring + auto-recovery** for the Itho Daalderop Smartboiler Mono Plus 50L. Cloud connectivity
for the devices is fine; the vendor apps keep working alongside.

## Scope at a glance

| Device | Integration | Control path | Notes |
|---|---|---|---|
| Calex smart lamps (Tuya-based) | `tuya-local` (HACS) | **Local** (LAN, Tuya protocol) | Lamps stay cloud-connected; Calex app keeps working |
| Itho Smartboiler Mono Plus | Climate Connect community integration (HACS) | **Cloud only** | No local API exists; reverse-engineered, unofficial |

## Decided

All on 2026-11-12, by the user:

- **D1. Exposure: LAN and Tailscale only.** No public route. HA is reached at
  `https://homeassistant.lan.gemberkoekje.nl` through Caddy, the LAN proxy that already serves the
  other `*.lan` names; it works at home and over Tailscale, and the router forwards nothing to it.
- **D2. Node: gembernode-01.** Over the 7 days before, it kept the most free memory (never below
  ~2.3 GiB; gembernode-03 ~2.1 GiB, gembernode-02 ~1.5 GiB) and had the least CPU load (~8%;
  gembernode-03 ~13%). No pod on any node used port 8123 or 5353.
- **D3. Recorder: the shared PostgreSQL** (the CloudNativePG Cluster), not SQLite on the volume.
- **D4. DHCP reservations are done:** the lamps are on 192.168.1.50–192.168.1.59.

## Changed while building

- **No Ingress, no ingress-nginx.** The cluster has moved to Traefik and the Gateway API, and
  LAN-only names belong to Caddy (`infrastructure/lan-proxy/`). The route is one Caddyfile block;
  Caddy passes WebSockets through without extra timeouts.
- **`trusted_proxies` has the nodes as well as the pod network.** Caddy reaches HA through its
  Service, whose endpoint is gembernode-01's own address (hostNetwork). From a Caddy pod on another
  node, flannel masquerades that traffic to the node's address. So the list is `10.42.0.0/16`
  plus 192.168.1.201–.203.
- **Pod security level `privileged`** for the `home-automation` namespace. The cluster's namespaces
  enforce `baseline`, which forbids hostNetwork.
- **`configuration.yaml` is a read-only mount of a ConfigMap** (content-hashed, so a change restarts
  HA). The UI can't overwrite it, and Git never touches `.storage`. The init container creates the
  three files it includes (`automations.yaml`, `scripts.yaml`, `scenes.yaml`), which HA only creates
  itself when it also writes `configuration.yaml`.
- **No `secrets.yaml`.** The recorder URL is an environment variable from the 1Password item
  `homeassistant-secrets`, read with `!env_var RECORDER_DB_URL`.
- **Backups at `/config/backups`, not `/backups`.** HA Container always writes its local backups
  to `/config/backups`, so the NAS volume is mounted there.
- **HACS is pinned by version and sha256.** The init container installs it only when it's absent,
  and never unpacks a zip that doesn't match. A failed download doesn't stop HA from starting.
- **A `wait-for-postgres` init container**, as the other PostgreSQL apps have. After a node reboot
  PostgreSQL can be back later than HA, and HA gives up on its recorder after a few tries.
- **Tested locally** (Docker, 2026-11-12): HA 2026.11.1 with this `configuration.yaml` read-only
  started in 6 seconds, and the recorder created its tables in PostgreSQL 18. The init script
  skipped a bad checksum, installed HACS 2.0.5, and left it alone on the next run. An
  `X-Forwarded-For` header from an untrusted address got the expected 400.

---

## Phase 0 — Prerequisites

- [x] **DHCP reservations** for every Calex lamp: 192.168.1.50–.59 (D4).
- [x] **Pick the HA node:** gembernode-01 (D2).
- [x] **Decide exposure:** LAN and Tailscale only (D1).
- [ ] Have the Calex app account and the Climate Connect account credentials at hand.

---

## Phase 1 — Deploy HA via Flux (built)

In [apps/home-assistant/](../apps/home-assistant/), namespace `home-automation`.

**Workload**
- `Deployment`, `replicas: 1`, `strategy: Recreate`.
- Image `ghcr.io/home-assistant/home-assistant:2026.11.1`, a release tag, bumped through Git.
- `hostNetwork: true` + `dnsPolicy: ClusterFirstWithHostNet`, so mDNS/SSDP and Tuya's UDP broadcasts
  reach HA.
- `nodeSelector` → gembernode-01. `TZ=Europe/Amsterdam`.
- Startup, liveness and readiness probes on `/manifest.json` (200 before and after onboarding; `/`
  redirects to onboarding at first). The startup probe allows 10 minutes.

**Storage** ([infrastructure/pvcs/home-automation.yaml](../infrastructure/pvcs/home-automation.yaml))
- `/config` → PVC `homeassistant-config` on `local-path`, 5 Gi.
- `/config/backups` → PVC `homeassistant-backups` on `qnap-nfs`, 5 Gi: in the QNAP's local and
  offsite backups.
- Flux never prunes either: both StorageClasses delete the data with the claim.

**Networking**
- `Service` `homeassistant` (ClusterIP, 8123); its endpoint is 192.168.1.201:8123.
- Caddy: `https://homeassistant.lan.gemberkoekje.nl`, plus a link on the LAN start page.

**Done when:** the onboarding page loads at `https://homeassistant.lan.gemberkoekje.nl`, the pod
survives a restart with config intact, and `custom_components/hacs` is on the volume. HACS 2 only
appears in the sidebar after it is added as an integration (Settings → Devices & services → Add
integration → HACS, which asks for a GitHub login), so that is checked in phase 2.

---

## Phase 2 — Onboarding & base config

- [ ] Complete onboarding (user, location, units, timezone).
- [ ] **Settings → System → Network:** set both Home Assistant URLs to
  `https://homeassistant.lan.gemberkoekje.nl`. It works at home and over Tailscale alike.
- [ ] **Add HACS** as an integration (GitHub device login).
- [ ] Enable HA's **automatic backups** (daily, keep ~7). They land in `/config/backups`, on the NAS.
  HA encrypts them: **store the encryption key in 1Password**, or the backups can't be restored.
- [ ] Install the **HA Companion app** on the phone. It's the notification target for Phase 5.
- [ ] Turn off any auto-discovered junk you don't want.

**Done when:** a manual backup lands on the QNAP and a test notification reaches the phone.

---

## Phase 3 — Calex lamps (local)

1. **Quick win (optional, ~5 min):** add the built-in **Tuya** integration. Enter the User Code from the Calex app (Account → Settings → Account and Security) and scan the QR code with the Calex app. This confirms the lamps are reachable and gives temporary cloud control.
2. **Install `tuya-local`** via HACS (`make-all/tuya-local`), then restart HA.
3. Add each lamp through tuya-local's **cloud-assisted setup**. It logs in to Tuya once to fetch each device's ID and **local key**, then finds the lamp on the LAN (192.168.1.50–.59). Do lamps **one at a time** and label them physically.
4. Once all lamps work through tuya-local, **remove the cloud Tuya integration** to avoid duplicate entities.
5. Group lamps into Areas.

**Caveats**
- Many Tuya devices accept **only one local connection**. Nothing else (e.g. another local tool) should hold one.
- If a lamp gets re-paired in the Calex app, its local key changes. Re-run setup for that lamp.

**Done when:** every lamp turns on/off and dims from HA with the internet uplink unplugged. Brief test; expect them to grumble if left offline long.

---

## Phase 4 — Itho Smartboiler (cloud)

**Integration choice** (both unofficial, reverse-engineered, zero-star repos, so expect breakage when Itho changes their API):
- **Primary:** `Rien-R/Itho-Daalderop-GES-HA` lineage (also `mjhagen/Itho-Daalderop-GES-HA` fork). Richest feature set: device mode select (SmartControl / Schedule / Continuous / Holiday), device state, boiler content %, power (kW), legionella timer, energy, connection status sensor. Polls status every 30 s. **Check which repo in the lineage is most recently maintained before installing.**
- **Fallback:** `vleerie/climateconnect-homeassistant`. Names the Smartboiler explicitly but is thinner (mode, temperature, boost, diagnostics; first device only).

**Steps**
1. Add the chosen repo to HACS as a custom repository (category: Integration), install, restart.
2. Auth (Rien-R lineage): log in through the browser flow. The page shows an error after login, **which is expected**. Copy the `climateconnect://login?token=...` URL from the browser console (F12) into HA. The token lasts about a year.
3. Confirm entities appear and the values match the Climate Connect app.

**Done when:** mode, boiler content %, power and connection status update in HA within a minute of changes in the app.

---

## Phase 5 — Standby: observe, then automate

**5a. Observe (don't automate yet).** We don't know how "standby" surfaces through the API.
- Leave it running until the next standby happens. Then check the **History/Logbook** for: device state, device mode, connection status, power, boiler content %.
- Diagnose the cause from the pattern:
  - **Connection went offline at the same moment** → boiler likely lost power or rebooted (power blip, breaker, earth leakage).
  - **Stayed online, only state/mode changed** → something else is putting it in standby. Check Climate Connect for schedule entries set to "standby" and look at what the device state value says.
- Write down the exact entity/value that flags it.

**5b. Automate** (once the signal is known):
- **Trigger:** the identified state/mode value, **plus** a fallback heuristic: boiler content % below a threshold AND power 0 kW for > N minutes during normal hours.
- **Guard:** `input_boolean.boiler_holiday`. When on, don't auto-recover. Holiday mode set on purpose must not be overridden.
- **Actions:** set device mode back to **SmartControl**, then send a Companion app notification ("Boiler was in standby, switched back").
- If 5a shows the mode can't be set back through the API (it may need the physical button), the automation becomes **notify-only**. Early warning is still the main win.

**Done when:** a simulated standby (put it in standby via the app) gets detected and handled within a couple of minutes, and the holiday guard blocks it.

---

## Phase 6 — Expose to other cluster services

- Internal address: `http://homeassistant.home-automation.svc.cluster.local:8123` (REST + WebSocket API).
- Create a **long-lived access token** for a dedicated HA user. Store it in 1Password and inject it via the operator into the consuming apps.
- Optional later: **Mosquitto** as its own Flux workload, with HA's MQTT integration, for event-driven consumers.

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Itho changes the Climate Connect API | Boiler entities die | Pin the integration version; standby notification still has the power/content heuristic if the sensors survive; watch the repo |
| Lamp re-paired / firmware update changes local key | One lamp drops out | Re-run tuya-local setup for that lamp |
| Lamp IP changes | Lamp drops out | DHCP reservations (D4) |
| gembernode-01 goes down | HA down (local-path is node-bound) | Accept for a home setup; restore from the NAS backup on another node (README, "Restoring") |
| PostgreSQL down | No history while it's down; HA itself keeps running | The `wait-for-postgres` init container covers reboots; the nightly dump covers the data |
| Recorder data grows | Database size | `recorder: purge_keep_days: 14` |
| Caddy's address not in `trusted_proxies` | Every page through Caddy answers 400 | The log names the address (README, "Deploying"); add it to `configuration.yaml` |
