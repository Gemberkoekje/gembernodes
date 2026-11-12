# Home Assistant on gembernodes

**Status: phases 1–3 done (2026-11-12).** HA runs on gembernode-01 at
https://homeassistant.lan.gemberkoekje.nl, with all ten lamps under local control. The manifests are
in [apps/home-assistant/](../apps/home-assistant/), with a [README](../apps/home-assistant/README.md).
Phase 4 (the boiler) is next; phases 5 and 6 follow. This plan started as
`home-assistant-plan.md` in Gemberkoekje/projects; where building phase 1 changed it, "Changed
while building" says so.

Goal: run Home Assistant (HA) on the k3s cluster, get **local control** of the Calex lamps, and
**monitoring + auto-recovery** for the Itho Daalderop Smartboiler Mono Plus 50L. Cloud connectivity
for the devices is fine; the vendor apps keep working alongside.

## Scope at a glance

| Device | Integration | Control path | Notes |
|---|---|---|---|
| Calex smart lamps (Tuya-based) | `tuya-local` (Marketplace) | **Local** (LAN, Tuya protocol) | Lamps stay cloud-connected; Calex app keeps working |
| Itho Smartboiler Mono Plus | Climate Connect community integration (Marketplace, custom repository) | **Cloud only** | No local API exists; reverse-engineered, unofficial |

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
- **D5. The boiler's normal mode is Klokprogramma** (the integration calls it Schedule), not
  SmartControl: 65 °C from 10:00 to 10:30 (dishes) and from 21:00 to 21:30 (showers), 10 °C the rest
  of the day. Phase 5 recovers to this mode.

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
- **No HACS install: it's built in.** Since 2026.11.0, HACS is part of Home Assistant as the
  **Marketplace** (Dutch UI: Marktplaats), set up by itself on the first start. HA blocks the old
  custom integration (`hacs` in `BLOCKED_CUSTOM_INTEGRATIONS`, logged only at info level) and deletes
  its `custom_components/hacs` folder itself. So the init container's HACS install, which phase 1
  first shipped with, was removed after the deploy (#215): HA would have deleted the folder, and
  every start would have reinstalled it.
- **A `wait-for-postgres` init container**, as the other PostgreSQL apps have. After a node reboot
  PostgreSQL can be back later than HA, and HA gives up on its recorder after a few tries.
- **Tested locally** (Docker, 2026-11-12): HA 2026.11.1 with this `configuration.yaml` read-only
  started in 6 seconds, and the recorder created its tables in PostgreSQL 18. The init script
  created the included files (it also installed HACS then, since removed). An
  `X-Forwarded-For` header from an untrusted address got the expected 400.

---

## Phase 0 — Prerequisites

- [x] **DHCP reservations** for every Calex lamp: 192.168.1.50–.59 (D4).
- [x] **Pick the HA node:** gembernode-01 (D2).
- [x] **Decide exposure:** LAN and Tailscale only (D1).
- [x] Have the Calex app account and the Climate Connect account credentials at hand.

---

## Phase 1 — Deploy HA via Flux (done)

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
survives a restart with config intact, and the recorder writes to PostgreSQL. All three were checked
on 2026-11-12 (NOTES.md).

---

## Phase 2 — Onboarding & base config (done)

- [x] Complete onboarding (user, location, units, timezone).
- [x] **Settings → System → Network:** set both Home Assistant URLs to
  `https://homeassistant.lan.gemberkoekje.nl`. It works at home and over Tailscale alike.
- [x] **Look at the Marketplace** (Settings → Marktplaats): HACS, built in. Browsing and installing
  from its catalog needs no GitHub account. Connecting GitHub (Settings → Devices & services →
  Marktplaats → Reconfigure) is only needed for custom repositories, which phases 3 and 4 both need.
- [x] Enable HA's **automatic backups**: daily, keeping 3 (the user's choice; ~7 was suggested). They
  land in `/config/backups`, on the NAS: the first, 18 MB, at 15:27 on 2026-11-12. HA encrypts
  them: **store the encryption key in 1Password**, or the backups can't be restored.
- [x] Install the **HA Companion app** on the phone ("Mobiel"). It's the notification target for Phase 5.
- [x] Turn off any auto-discovered junk you don't want.

**Done when:** a manual backup lands on the QNAP and a test notification reaches the phone.

---

## Phase 3 — Calex lamps (local) (done)

1. **Quick win (optional, ~5 min):** add the built-in **Tuya** integration. Enter the User Code from the Calex app (Account → Settings → Account and Security) and scan the QR code with the Calex app. This confirms the lamps are reachable and gives temporary cloud control.
2. **Install `tuya-local`** (`make-all/tuya-local`, shown as "Tuya Local"), then restart HA. It is **not in the Marketplace's own catalog** (checked 2026-11-12; its README says to add it as a custom repository). So: connect the Marketplace to GitHub (phase 2), then in Settings → Marktplaats use ⋮ → Custom repositories to add `https://github.com/make-all/tuya-local` (category: Integration), and download it. Don't confuse it with **LocalTuya** ("Local Tuya", `rospogrigio/localtuya`), which *is* in the catalog: a different project that needs Tuya developer-platform credentials (Client ID, Secret, User ID) instead of the Calex app's User Code.
3. Add each lamp through tuya-local's **cloud-assisted setup**. It logs in to Tuya once to fetch each device's ID and **local key**, then finds the lamp on the LAN (192.168.1.50–.59). Do lamps **one at a time** and label them physically.
4. Once all lamps work through tuya-local, **remove the cloud Tuya integration** to avoid duplicate entities.
5. Group lamps into Areas.

**Caveats**
- Many Tuya devices accept **only one local connection**. Nothing else (e.g. another local tool) should hold one.
- If a lamp gets re-paired in the Calex app, its local key changes. Re-run setup for that lamp.

**Done when:** every lamp turns on/off and dims from HA with the internet uplink unplugged. Brief test; expect them to grumble if left offline long.

**Result (2026-11-12, done by the user):** all ten lamps run on Tuya Local, one config entry each, in
the areas Woonkamer (7), Slaapkamer, Toilet and Gang. The cloud Tuya quick win (step 1) was skipped,
so step 4 had nothing to remove. LocalTuya, installed by mistake first, was removed. Each lamp, as
Tuya Local stores it:

| Lamp | Address | Tuya protocol | Tuya Local device type |
|---|---|---|---|
| Voorkamer | 192.168.1.50 | 3.3 | `rgbcw_lightbulb` (RGBCW lightbulb) |
| Woonkamer Linksvoor | 192.168.1.51 | 3.3 | `calex_s45cleare27_light` (CCT lightbulb) |
| Woonkamer Rechtsvoor | 192.168.1.52 | 3.3 | `calex_s45cleare27_light` |
| Woonkamer linksmidden | 192.168.1.53 | 3.3 | `calex_s45cleare27_light` |
| Woonkamer rechtsmidden | 192.168.1.54 | 3.3 | `calex_s45cleare27_light` |
| Woonkamer linksachter | 192.168.1.55 | 3.3 | `calex_s45cleare27_light` |
| Woonkamer Rechtsachter | 192.168.1.56 | 3.3 | `calex_s45cleare27_light` |
| Slaapkamer | 192.168.1.57 | 3.3 | `rgbcw_lightbulb` |
| Ganglicht | 192.168.1.58 | 3.5 | `calex_s45cleare27_light` |
| WC licht | 192.168.1.59 | 3.5 | `calex_s45cleare27_light` |

The white lamps (A60 Clear, P45 Softline "milky" 5101003300) are CCT: dimmable, warm to cool. The two
G125 RGB CCT lamps are RGBCW: colour plus warm to cool white.

---

## Phase 4 — Itho Smartboiler (cloud)

**Progress (2026-11-12):** `mjhagen/Itho-Daalderop-GES-HA` 1.5.0 (commit `8e4658b`) is installed and
logged in. The boiler shows up as `…_vpr260220080_…` in the area Keuken. Its values match the app and
the boiler's own display: mode Schedule = Klokprogramma, boiler content 0% = the app's
"Energieniveau" 0%, legionella timer 165 h. Not yet tested: that a change in the app reaches HA within
a minute.

**What the integration gets wrong or leaves out** (checked in its code and in the recorder):
- **Boiler content % is always 0**, in the app as much as in HA. The user: it has never worked, in
  any mode (Smart control, a clock program at 65 °C nearly all day, the current one), while the
  display showed 60.1 °C. HA reads the same `boilerContent` the app shows, so the 0 comes from the
  boiler or Itho's cloud; a fault for Itho or the installer to look at. Useless as a signal here.
- **The schedule sensors all say "No schedule", but the schedule is there.** Their raw attribute
  holds `{'36000': 65, '37800': 10, '75600': 65, '77400': 10}`: seconds after midnight, which is
  10:00 and 21:00 at 65 °C, then 10:30 and 21:30 at 10 °C. `sensor.py` only parses HHMM keys
  (`1000`) and drops the rest. The write path (`api.py`) passes keys above 2359 through unchanged,
  so setting the mode to Schedule from HA sends this schedule back intact. Keys below 2359 seconds
  (before 00:39) would be misread, but there are none here.
- **No water temperature in HA.** `water_heater.py` reads the measured temperature
  (`deviceTemperatureMeasured`), but `__init__.py` never loads the `water_heater` platform, so the
  entity doesn't exist.

**Integration choice** (both unofficial, reverse-engineered, zero-star repos, so expect breakage when Itho changes their API):
- **Primary:** `Rien-R/Itho-Daalderop-GES-HA` lineage (also `mjhagen/Itho-Daalderop-GES-HA` fork). Richest feature set: device mode select (SmartControl / Schedule / Continuous / Holiday), device state, boiler content %, power (kW), legionella timer, energy, connection status sensor. Polls status every 30 s.
  **Checked 2026-11-12: use [`mjhagen/Itho-Daalderop-GES-HA`](https://github.com/mjhagen/Itho-Daalderop-GES-HA).** It is 14 commits ahead of Rien-R's original and none behind, last pushed 2026-10-07 (Rien-R: 2026-02-27; the other fork, JobDoesburg: 2026-08-11). Two of those commits matter for phase 5: "Fix device mode API payload" (setting the mode back) and "Add boiler connection health and reauthentication" (a warning after repeated API errors, 5 minutes without polling, or 24 hours of unchanged telemetry). None of the candidates is in the Marketplace catalog.
  **Gotcha:** its README's custom-repository URL is `marinuz/Itho-Daalderop-GES-HA`, which GitHub redirects to Rien-R's original, without these fixes. Add `https://github.com/mjhagen/Itho-Daalderop-GES-HA` instead.
- **Fallback:** `vleerie/climateconnect-homeassistant`. Names the Smartboiler explicitly but is thinner (mode, temperature, boost, diagnostics; first device only).

**Steps**
1. Connect the Marketplace to GitHub first (Settings → Devices & services → Marktplaats → Reconfigure; a code to enter at github.com/login/device). Then add the chosen repo in the Marketplace as a custom repository (category: Integration), install, restart.
2. Auth (Rien-R lineage, mjhagen included): log in through the browser flow. The page shows an error after login, **which is expected**. Copy the `climateconnect://login?token=...` URL from the browser console (F12) into HA. The token lasts about a year.
3. Confirm entities appear and the values match the Climate Connect app.

**Done when:** mode, power and connection status update in HA within a minute of changes in the app
(boiler content % is dropped: it is always 0).

---

## Phase 5 — Standby: observe, then automate

**5a. Observe (don't automate yet).** We don't know how "standby" surfaces through the API.
- Leave it running until the next standby happens. Then check the **History/Logbook** for: device state, device mode, connection status, power, boiler content %.
- Diagnose the cause from the pattern:
  - **Connection went offline at the same moment** → boiler likely lost power or rebooted (power blip, breaker, earth leakage).
  - **Stayed online, only state/mode changed** → something else is putting it in standby. Check Climate Connect for schedule entries set to "standby" and look at what the device state value says.
- Write down the exact entity/value that flags it.

**5b. Automate** (once the signal is known):
- **Trigger:** the identified state/mode value. The fallback heuristic first planned here (boiler
  content % low AND power 0 kW) can't work: content % is always 0, and 0 kW is normal outside the
  two half-hour slots (D5) and inside them when the tank is already at 65 °C. A better fallback needs
  the water temperature (missing, see phase 4): below ~40 °C after a slot has passed means it didn't
  heat.
- **Guard:** `input_boolean.boiler_holiday`. When on, don't auto-recover. Holiday mode set on purpose must not be overridden.
- **Actions:** set device mode back to **Schedule** (Klokprogramma, D5), then send a Companion app notification ("Boiler was in standby, switched back").
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
| Itho changes the Climate Connect API | Boiler entities die | Pin the integration version; the connection-health warning flags it; watch the repo |
| Lamp re-paired / firmware update changes local key | One lamp drops out | Re-run tuya-local setup for that lamp |
| Lamp IP changes | Lamp drops out | DHCP reservations (D4) |
| gembernode-01 goes down | HA down (local-path is node-bound) | Accept for a home setup; restore from the NAS backup on another node (README, "Restoring") |
| PostgreSQL down | No history while it's down; HA itself keeps running | The `wait-for-postgres` init container covers reboots; the nightly dump covers the data |
| Recorder data grows | Database size | `recorder: purge_keep_days: 14` |
| Caddy's address not in `trusted_proxies` | Every page through Caddy answers 400 | The log names the address (README, "Deploying"); add it to `configuration.yaml` |
