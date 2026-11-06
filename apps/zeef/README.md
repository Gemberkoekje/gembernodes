# Zeef

Download Station's replacement: films and series via Radarr and Sonarr, torrents via qBittorrent,
indexers via Prowlarr, malware and stalled-download cleanup via Cleanuparr, and the TRaSH Guides'
quality rules via a nightly Recyclarr job. Downloads land on the QNAP **Multimedia** share
(`/data` in every pod). Design and runbook: Gemberkoekje/projects `Zeef/DESIGN.md` and
`Zeef/DEPLOY.md`. The Zeef app itself (one Dutch search box in front of all this) follows in phase 1.

## Where it is reachable

**LAN and Tailscale only, like Grafana.** All web UIs share `192.168.1.234`, and the router
forwards nothing to it. Away from home, the Tailscale subnet router already routes `.224/28`.

| Port | App |
|---|---|
| `:8989` | Sonarr |
| `:7878` | Radarr |
| `:9696` | Prowlarr |
| `:8080` | qBittorrent |
| `:11011` | Cleanuparr |
| `:80` | (Zeef, phase 1) |

The only thing the internet reaches is qBittorrent's peer port, `192.168.1.235:49160` (TCP and
UDP, forwarded by the router). It speaks BitTorrent and has no web UI behind it.

## Rules for these manifests

- **No `fsGroup` on any pod that mounts `/data`.** The kubelet would chown every file in the media
  library on each mount. The images drop to `PUID`/`PGID` themselves.
- **The `multimedia-nfs` PV stays `Retain`, with Flux pruning disabled** (`infrastructure/pvcs/zeef.yaml`).
  With `Delete`, removing the claim could make the CSI driver delete the whole share.
- **Nothing goes into `ingress/`.** No public route, ever.
- **Image tags stay pinned.** Bump them deliberately. The Servarr apps migrate their databases on
  start, so read the release notes before a major version (Sonarr 5 is in development).

## Before the first deploy

### 1. The NFS export (QNAP)

Control Panel → Privilege → Shared Folders → `Multimedia` → Edit Shared Folder Permission →
NFS host access:

- access on;
- hosts `192.168.1.201`, `192.168.1.202`, `192.168.1.203`;
- read/write;
- squash root user only.

Without it the pods sit in `ContainerCreating` (mount failure).

### 2. Databases and logins on the shared PostgreSQL

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
-- One login per app: not a superuser, can't create databases or roles (the defaults).
CREATE ROLE sonarr LOGIN;
\password sonarr
CREATE DATABASE "sonarr-main" OWNER sonarr;
CREATE DATABASE "sonarr-log" OWNER sonarr;

CREATE ROLE radarr LOGIN;
\password radarr
CREATE DATABASE "radarr-main" OWNER radarr;
CREATE DATABASE "radarr-log" OWNER radarr;

CREATE ROLE prowlarr LOGIN;
\password prowlarr
CREATE DATABASE "prowlarr-main" OWNER prowlarr;
CREATE DATABASE "prowlarr-log" OWNER prowlarr;

CREATE ROLE cleanuparr LOGIN;
\password cleanuparr
CREATE DATABASE cleanuparr OWNER cleanuparr;

-- Every login may connect to a new database; only its owner may connect to these.
REVOKE CONNECT, TEMPORARY ON DATABASE "sonarr-main", "sonarr-log", "radarr-main", "radarr-log",
  "prowlarr-main", "prowlarr-log", cleanuparr FROM PUBLIC;
```

Make each password with `openssl rand -hex 24`. The apps create their own tables on first start.

### 3. The 1Password item

Item **`zeef-stack`** in the Gembercluster vault, with exactly these field labels:

| Field | Value |
|---|---|
| `SONARR__AUTH__APIKEY` | `openssl rand -hex 16` |
| `SONARR__POSTGRES__PASSWORD` | sonarr's password from step 2 |
| `RADARR__AUTH__APIKEY` | `openssl rand -hex 16` |
| `RADARR__POSTGRES__PASSWORD` | radarr's password |
| `PROWLARR__AUTH__APIKEY` | `openssl rand -hex 16` |
| `PROWLARR__POSTGRES__PASSWORD` | prowlarr's password |
| `CLEANUPARR__POSTGRES__PASSWORD` | cleanuparr's password |

A missing field keeps that pod in `CreateContainerConfigError`. The API keys are set from here, so
Prowlarr, Recyclarr, Cleanuparr and (later) Zeef use them without anyone copying keys out of a UI.

## After the first deploy

Follow projects `Zeef/DEPLOY.md`, part B. It covers the router forward, qBittorrent's paths and
limits, Sonarr/Radarr root folders and naming, the Prowlarr sync, Cleanuparr, the first Recyclarr
run, Kodi, and the checks.
