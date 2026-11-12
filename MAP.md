# Map

What this repository holds and how the pieces connect. It describes the current state only. Why
things are the way they are lives in [NOTES.md](NOTES.md) (a dated log) and in the comments of the
manifests themselves. [CLAUDE.md](CLAUDE.md) says when to update this file.

## How it gets deployed

Flux watches `main`. [clusters/home/flux-system/gotk-sync.yaml](clusters/home/flux-system/gotk-sync.yaml)
points it at `clusters/home/`, which has one Flux Kustomization per folder. Each waits for the ones
before it:

```
namespaces ─► repos ─► infrastructure ─┬─► configuration
           │                           ├─► apps ─► ingress
           │                           └─► system-upgrade-plans
           └─► tailscale
```

| Folder | What's in it | Flux Kustomization |
|---|---|---|
| [namespaces/](namespaces/) | One Namespace per app or component | `namespaces` |
| [repos/](repos/) | The Helm repositories (and PostgreSQL's OCI repository) that the HelmReleases install from | `repos` |
| [infrastructure/](infrastructure/) | Shared services, one folder each (see below) | `infrastructure` |
| [infrastructure/tailscale/](infrastructure/tailscale/) | The Tailscale subnet router, applied on its own | `tailscale` |
| [infrastructure/system-upgrade-plans/](infrastructure/system-upgrade-plans/) | k3s upgrade Plans | `system-upgrade-plans` |
| [configuration/](configuration/) | Resources that need infrastructure's CRDs: the MetalLB address pool, cert-manager ClusterIssuers, Traefik's HSTS middleware | `configuration` |
| [apps/](apps/) | One folder per app | `apps` |
| [ingress/](ingress/) | The public routes, one file per app: HTTPRoutes (`<app>-route.yaml`, Gateway API, the way for new routes) and the older Ingress objects (`<app>-ingress.yaml`) | `ingress` |
| [archive/](archive/) | Manifests taken out of the cluster, kept just in case | none: not applied |

Every folder has a `kustomization.yaml` listing its files: a new file only deploys once it's listed
there. A new app usually touches four places: its Namespace in `namespaces/`, its folder in `apps/`,
its Ingress in `ingress/` (if public), and its NFS volumes in `infrastructure/pvcs/`.

## Network

The three k3s nodes are `gembernode-01` to `-03` (192.168.1.201–.203). All three are servers with
embedded etcd. MetalLB hands out 192.168.1.230–.239 in L2 mode
([configuration/ipaddresspool.yaml](configuration/ipaddresspool.yaml)).

| Address | What answers |
|---|---|
| 192.168.1.211 | The QNAP NAS (NFS). It keeps a local backup and copies offsite nightly (Hybrid Backup Sync), which covers everything the cluster stores there |
| 192.168.1.231 | Traefik: the router forwards public 80/443 here. Also serves Grafana at `/grafana` and the SpaceTraders dashboard (LAN only) |
| 192.168.1.232 | PostgreSQL, for LAN clients (in the cluster: `postgresql.flux-system.svc.cluster.local`) |
| 192.168.1.233 | print-manager-test (80, 631, 8100, 8101) |
| 192.168.1.234 | The Zeef web UIs, one port per app ([apps/zeef/README.md](apps/zeef/README.md)) |
| 192.168.1.235 | qBittorrent's peer port (49160) |
| 192.168.1.236 | Caddy, the LAN proxy for `*.lan.gemberkoekje.nl` |

There are three ways in:

- **From the internet:** `*.gemberkoekje.nl` → public IP → router (80/443) → Traefik (.231) → a
  route in `ingress/` → the app's Service. Routes come in two kinds:
  - **Gateway API (the way for new routes; so far kluskat):** HTTPRoutes attached to the Gateway
    `traefik/public` (`infrastructure/traefik/gateway.yaml`). Its `http` listener carries every
    host's redirect to HTTPS. It has one `https-<app>` listener per hostname, whose certificate
    cert-manager issues through `letsencrypt-gateway` (HTTP-01 via a temporary HTTPRoute).
  - **Ingress (the rest, moving over):** class `nginx-public` (defined in
    `infrastructure/traefik/ingressclass.yaml`), which Traefik reads through its Ingress NGINX
    provider. Most of these apps answer on their own subdomain and on a path of `gemberkoekje.nl`.
    Their certificates come from cert-manager's `letsencrypt-prod` (HTTP-01).
- **On the LAN, by name:** `<app>.lan.gemberkoekje.nl` → Caddy (.236) →
  the in-cluster Service. The routes are in
  [infrastructure/lan-proxy/Caddyfile](infrastructure/lan-proxy/Caddyfile). Caddy serves a wildcard
  certificate from `letsencrypt-lan` (DNS-01 via acme-dns) and puts Maintainerr behind a login. The
  router forwards nothing to these names.
- **Over Tailscale:** the subnet router (`gembercluster`) routes 192.168.1.200/29 (the nodes) and
  192.168.1.224/28 (the MetalLB addresses) to the tailnet. Away from home, LAN names and IPs work the
  same as at home. At home with Tailscale on, these narrower routes beat the home /24, so that
  traffic goes through the router pod too.

Reachable on the LAN by IP only, with an allowlist of 192.168.0.0/16 and 10.0.0.0/8: the
SpaceTraders dashboard (`http://192.168.1.231/spacetraders/dashboard/`) and Grafana
(`http://192.168.1.231/grafana`). Dockhand listens on NodePort 30080 on every node.

## Shared services the apps lean on

| Service | Where | Used by |
|---|---|---|
| **PostgreSQL**: one server, one database per app | [infrastructure/postgresql/](infrastructure/postgresql/), data on `qnap-nfs` | Every app with a `ConnectionStrings__*` value in its 1Password item: adventureengine, armabotcs, bot-on-the-clocktower, charactercreator, curatool, datumprikker, dungeontable, ebi-cs-api, kluskat, plotboek-generator and spacetraders. Also Zeef's Sonarr, Radarr, Prowlarr, Seerr, Bazarr, Cleanuparr and AudioBookRequest. Several wait for it in a `postgres:17-alpine` init container |
| PostgreSQL backup | [infrastructure/postgresql-backup/](infrastructure/postgresql-backup/) | Nightly at 02:00 UTC, written to a `qnap-nfs` volume |
| **Secrets**: 1Password Connect and operator | [infrastructure/externalsecrets/](infrastructure/externalsecrets/) | Each `OnePasswordItem` (`vaults/Gembercluster/items/<name>`) becomes a Secret of the same name in its namespace. The items sit next to the app that uses them |
| Image pull secret `ghcr-login` | [infrastructure/reflector/](infrastructure/reflector/) | Reflector copies it into every namespace (a few apps also have their own copy as a `OnePasswordItem`) |
| **NFS volumes**: StorageClass `qnap-nfs` | [infrastructure/nfs-provisioner/](infrastructure/nfs-provisioner/) | Most PVCs, kept in [infrastructure/pvcs/](infrastructure/pvcs/) (one file per namespace). On the NAS at `/gembernodes-pvcs/<namespace>/<pvc>` |
| **Node disk**: StorageClass `local-path` | built into k3s | SQLite, which must stay off NFS: Jellyfin, Maintainerr, Audiobookshelf's config, Chaptarr. Each pins its pod to one node. These volumes aren't on the NAS, so its backups don't cover them; Jellyfin's weekly backup puts its database there |
| The Multimedia share | `infrastructure/pvcs/zeef.yaml` (static PV `multimedia-nfs`, PVC `zeef/multimedia`) | Zeef's media apps, mounted at `/data` (Jellyfin: `/media`, read-only) |
| **Certificates**: cert-manager | [infrastructure/certmanager/](infrastructure/certmanager/), issuers in [configuration/](configuration/) | The public Gateway's listeners (`letsencrypt-gateway`, Secrets in `traefik`), the public Ingresses (`letsencrypt-prod`) and Caddy's wildcard certificate (`letsencrypt-lan`) |

## Apps

| App | Folder → namespace | Reached at | Depends on |
|---|---|---|---|
| adventureengine | `apps/adventureengine` | `adventureengine.gemberkoekje.nl` | PostgreSQL, NFS volume (data protection keys) |
| armabotcs | `apps/armabotcs` | Discord bot, no web | PostgreSQL |
| bot-on-the-clocktower | `apps/bot-on-the-clocktower` | Bot, no web | PostgreSQL |
| bygalacticaccord | `apps/bygalacticaccord` | `bygalacticaccord.gemberkoekje.nl` | |
| charactercreator | `apps/charactercreator` | `charactercreator.gemberkoekje.nl` | PostgreSQL |
| cov-website | `apps/cov-website` | `cov-website.gemberkoekje.nl` | Mail (SMTP) |
| curatool | `apps/curatool` | `curatool.gemberkoekje.nl` | PostgreSQL |
| datumprikker | `apps/datumprikker` | `datumprikker.gemberkoekje.nl` | PostgreSQL |
| dockhand | `apps/dockhand` | NodePort 30080 | |
| dungeontable | `apps/dungeontable` | `dungeontable.gemberkoekje.nl` | PostgreSQL, NFS volumes (uploads, data protection keys) |
| ebi-cs-api, ebi-cs-frontend | `apps/ebi-cs-api`, `apps/ebi-cs-frontend` → both in `ebi-cs-api` | `ebi-cs-api.`, `ebi-frontend.gemberkoekje.nl` | PostgreSQL |
| fileserver (File Browser) | `apps/fileserver` → `file-server` | `fileserver.gemberkoekje.nl` | NFS volume |
| hackerminigames | `apps/hackerminigames` | `hackerminigames.gemberkoekje.nl` | |
| healthcheck | `apps/healthcheck` → `cluster-healthcheck` | `healthcheck.gemberkoekje.nl` | A static page served by Caddy |
| kluskat | `apps/kluskat` | `kluskat.gemberkoekje.nl` (Gateway API: `ingress/kluskat-route.yaml`) | PostgreSQL |
| plotboek-generator | `apps/plotboek-generator` | `plotboek.gemberkoekje.nl` | PostgreSQL. A CronJob resets the demo at 04:00 (Amsterdam) |
| print-manager-test | `apps/print-manager-test` | 192.168.1.233 | NFS volume |
| spacetraders (API and web UI) | `apps/spacetraders` | LAN only (above) | PostgreSQL. Grafana reads its API (`infrastructure/monitoring`) |
| vortexplotboek | `apps/vortexplotboek` | `vortexplotboek.gemberkoekje.nl`, `gemberkoekje.nl/vortexplotboek` | Redirect only, to `plotboek.the-vortex.nl` (the app runs on the-vortex cluster). The Service has no pods: it only gives the Ingress a backend to name. The old app manifests are in `archive/vortexplotboek/` |
| **Zeef** (media stack) | `apps/zeef` ([README](apps/zeef/README.md)) | `<app>.lan.gemberkoekje.nl`, 192.168.1.234:`<port>` | PostgreSQL, the Multimedia share, `local-path`, the `zeef-stack` 1Password item |

Inside Zeef: Seerr sends requests to Sonarr and Radarr. They search through Prowlarr, download
through qBittorrent and tell Jellyfin about new files. Recyclarr sets their quality rules nightly,
Bazarr adds subtitles, Cleanuparr clears bad or stalled downloads and Maintainerr removes what's
been watched. For audiobooks, AudioBookRequest feeds Chaptarr, which uses Prowlarr and qBittorrent,
and Audiobookshelf plays them. Most of these links are set in the apps' own settings, not in the
manifests: see the README.

App images mostly come from `ghcr.io/gemberkoekje/<app>`, built by each app's own repository.
Designs and runbooks live in Gemberkoekje/projects.

## Infrastructure

| Component | Folder | Role |
|---|---|---|
| MetalLB | `infrastructure/metallb` | LoadBalancer IPs (pool in `configuration/`) |
| Traefik | `infrastructure/traefik` | Public entry point on .231. Also holds the public Gateway (`gateway.yaml`) and the `nginx-public` IngressClass |
| cert-manager | `infrastructure/certmanager` | Certificates |
| 1Password Connect | `infrastructure/externalsecrets` | Secrets from the `Gembercluster` vault |
| Reflector | `infrastructure/reflector` | Copies `ghcr-login` into namespaces |
| PostgreSQL, backup | `infrastructure/postgresql`, `infrastructure/postgresql-backup` | Shared database |
| NFS CSI driver | `infrastructure/nfs-provisioner` | The `qnap-nfs` StorageClass |
| PVCs | `infrastructure/pvcs` | NFS volumes for the apps |
| Monitoring | `infrastructure/monitoring` | Prometheus, Grafana, Loki and Promtail. Dashboards are `dashboards/*.json`, loaded through `configMapGenerator`; alert rules are in `grafana-alerting-provisioning.yaml` |
| Caddy LAN proxy | `infrastructure/lan-proxy` | `*.lan.gemberkoekje.nl` on .236. Restarts weekly to load the renewed certificate |
| Tailscale subnet router | `infrastructure/tailscale` | Tailnet access to the nodes and MetalLB IPs |
| kured | `infrastructure/kured` | Reboots nodes after updates, between 02:00 and 05:00 UTC |
| system-upgrade-controller | `infrastructure/system-upgrade`, `infrastructure/system-upgrade-plans` | k3s upgrades |

## Checks

- [scripts/validate.py](scripts/validate.py) builds every Flux Kustomization the way Flux does,
  checks the result against the schemas and renders the HelmReleases.
- [scripts/check_images.py](scripts/check_images.py) checks that the images a pull request adds or
  changes exist in their registries.
- [.github/workflows/validate.yaml](.github/workflows/validate.yaml) runs both on every pull request,
  and runs `validate.py` on pushes to `main`.

## Other documents

- [NOTES.md](NOTES.md): one dated entry per change (why, gotchas, what was tested), newest at the
  bottom.
- [docs/ingress-nginx-migration-plan.md](docs/ingress-nginx-migration-plan.md): the move to Traefik.
- [apps/zeef/README.md](apps/zeef/README.md): Zeef's ports, apps and setup.
