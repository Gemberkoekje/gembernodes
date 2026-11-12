# Zeef

Download Station's replacement: films and series via Radarr and Sonarr, torrents via qBittorrent,
indexers via Prowlarr, malware and stalled-download cleanup via Cleanuparr, English subtitles via
Bazarr, and the TRaSH Guides' quality rules via a nightly Recyclarr job. Audiobooks are requested
in AudioBookRequest, found and imported by Chaptarr (indexers from Prowlarr, downloads through
qBittorrent, checked by Cleanuparr), and played from Audiobookshelf.
Downloads land on the QNAP **Multimedia** share (`/data` in every pod; audiobooks in
`/data/Audiobooks`). Design and runbook: Gemberkoekje/projects `Zeef/DESIGN.md` and
`Zeef/DEPLOY.md`. The Zeef app itself (one Dutch search box in front of all this) follows in phase 1.

## Where it is reachable

**LAN and Tailscale only, like Grafana.** Friendly names: `https://<app>.lan.gemberkoekje.nl` (start page `https://lan.gemberkoekje.nl`, see `infrastructure/lan-proxy`). All web UIs share `192.168.1.234`, and the router
forwards nothing to it. Away from home, the Tailscale subnet router already routes `.224/28`.

| Port | App |
|---|---|
| `:8989` | Sonarr |
| `:7878` | Radarr |
| `:9696` | Prowlarr |
| `:8080` | qBittorrent |
| `:11011` | Cleanuparr |
| `:8096` | Jellyfin |
| `:5055` | Seerr (request films and series) |
| `:6767` | Bazarr (English subtitles) |
| `:13378` | Audiobookshelf (audiobook library and player) |
| `:8000` | AudioBookRequest (request audiobooks) |
| `:8789` | Chaptarr (audiobooks, like Sonarr) |
| `:80` | (Zeef, phase 1) |

Maintainerr (cleanup of watched media) has no port there: it has no login of its own, so it is
reachable only as `https://maintainerr.lan.gemberkoekje.nl`, where Caddy asks for one (the
1Password item `lan-proxy`, see `infrastructure/lan-proxy/maintainerr-login.yaml`).

The only thing the internet reaches is qBittorrent's peer port, `192.168.1.235:49160` (TCP and
UDP, forwarded by the router). It speaks BitTorrent and has no web UI behind it.

## Rules for these manifests

- **No `fsGroup` on any pod that mounts `/data`.** The kubelet would chown every file in the media
  library on each mount. The images drop to `PUID`/`PGID` themselves.
- **The `multimedia-nfs` PV stays `Retain`, with Flux pruning disabled** (`infrastructure/pvcs/zeef.yaml`).
  With `Delete`, removing the claim could make the CSI driver delete the whole share.
- **Nothing goes into `ingress/`.** No public route, ever.
- **Jellyfin's `/config` is on `local-path`, not NFS** (SQLite; Jellyfin 12 supports nothing else).
  The pod is tied to the node that first ran it. Its weekly backups (CronJob `jellyfin-backup`,
  database + subtitles, newest four kept) land on the `jellyfin-backup` claim on the QNAP once
  `JELLYFIN__APIKEY` is in the `zeef-stack` item.
- **Audiobookshelf's `/config` is on `local-path` too** (SQLite only), and it mounts the library
  read-only: Chaptarr owns the files in `Audiobooks/` (hardlinks of what qBittorrent seeds). Its
  own scheduled backups land in `/metadata/backups` on the QNAP (`audiobookshelf-metadata`), once
  switched on in its settings.
- **Chaptarr's `/config` is on `local-path` as well**, with its SQLite databases (`chaptarr.db`,
  `logs.db`, `cache.db`, `staging.db`). Not in the shared PostgreSQL: that runs in FIPS mode, where
  `md5()` fails, and one of Chaptarr's PostgreSQL migrations needs it (NOTES.md, 2026-11-09).
- **Image tags stay pinned.** Bump them deliberately. The Servarr apps migrate their databases on
  start, so read the release notes before a major version (Sonarr 5 is in development). Dependabot
  proposes the bumps weekly (`.github/dependabot.yml`). It leaves qBittorrent out, since that stays
  at 5.2.4 until MyAnonamouse allows 5.3.

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

-- Seerr (added with the Seerr manifest; create it before that merges).
CREATE ROLE seerr LOGIN;
\password seerr
CREATE DATABASE seerr OWNER seerr;
REVOKE CONNECT, TEMPORARY ON DATABASE seerr FROM PUBLIC;

-- Bazarr (added with the Bazarr manifest; create it before that merges).
CREATE ROLE bazarr LOGIN;
\password bazarr
CREATE DATABASE bazarr OWNER bazarr;
REVOKE CONNECT, TEMPORARY ON DATABASE bazarr FROM PUBLIC;

-- AudioBookRequest (added with its manifest; create it before that merges).
-- Hex password only: AudioBookRequest puts it into a connection URL as-is.
CREATE ROLE audiobookrequest LOGIN;
\password audiobookrequest
CREATE DATABASE audiobookrequest OWNER audiobookrequest;
REVOKE CONNECT, TEMPORARY ON DATABASE audiobookrequest FROM PUBLIC;

-- Every login may connect to a new database; only its owner may connect to these.
REVOKE CONNECT, TEMPORARY ON DATABASE "sonarr-main", "sonarr-log", "radarr-main", "radarr-log",
  "prowlarr-main", "prowlarr-log", cleanuparr FROM PUBLIC;
```

Make each password with `openssl rand -hex 24`. The apps create their own tables on first start.
`\password` is a psql command. In DBeaver or another GUI, write `CREATE ROLE seerr LOGIN PASSWORD
'<hex>';` instead, and run the script with auto-commit on (`CREATE DATABASE` refuses to run inside a
transaction).

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
| `SEERR__DB_PASS` | seerr's password (Seerr) |
| `BAZARR__POSTGRES__PASSWORD` | bazarr's password (Bazarr) |
| `AUDIOBOOKREQUEST__POSTGRES__PASSWORD` | audiobookrequest's password (AudioBookRequest; hex only) |
| `CHAPTARR__AUTH__APIKEY` | `openssl rand -hex 16` |
| `QBITTORRENT__PASSWORD` | the qBittorrent WebUI password (for later use) |
| `JELLYFIN__APIKEY` | a Jellyfin API key (weekly backup job and Bazarr's post-processing; optional) |

A missing field keeps that pod in `CreateContainerConfigError`. The API keys are set from here, so
Prowlarr, Recyclarr, Cleanuparr and (later) Zeef use them without anyone copying keys out of a UI.

## After the first deploy

Follow projects `Zeef/DEPLOY.md`, part B. It covers the router forward, qBittorrent's paths and
limits, Sonarr/Radarr root folders and naming, the Prowlarr sync, Cleanuparr, the first Recyclarr
run, Kodi, and the checks.
