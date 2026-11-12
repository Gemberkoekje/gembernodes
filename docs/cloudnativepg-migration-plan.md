# Bitnami PostgreSQL → CloudNativePG

**Status: carried out on 2026-11-12** (NOTES.md has the log). PostgreSQL now runs on CloudNativePG;
what remains is under "Left to do". The rest of this document is the plan as decided, kept for
the reasoning. Where the build differs from it, "Changed while building" says so.

## Why

- **The Bitnami chart is a dead end.** Bitnami's free catalog only publishes `latest`, so the
  image is pinned by digest and every bump is manual guesswork.
- **CloudNativePG (CNPG) is maintained.** It's an operator, and its images have real version tags.
  It handles shutdown, crash recovery, failover and upgrades itself, where this repo now hand-tunes
  probes and a `preStop` hook.

## Decided

All on 2026-11-12:

- **One instance on the NAS (`qnap-nfs`), like today.** No local-disk replicas: the nodes' disks
  are small, and Longhorn once filled them.
- **Downtime is accepted:** every PostgreSQL app down for an estimated 15–30 minutes. The moment
  is agreed when the plan is carried out.
- **The superuser secret:** you create a 1Password item (e.g. `postgresql-superuser` in vault
  Gembercluster) with fields `username` = `postgres` and `password` = today's postgres password,
  before the plan is carried out. You make it, not Claude, because it holds the password.
- **Databases:** VortexPlotboek is kept, just in case. VortexPlotboekLocal, VortexLnv,
  VortexLnvLocal, LanderijenVolken and werkplaats are left out of the import. They stay in the old
  volume until it's deleted, and in the nightly dumps until those rotate out.
- **Namespace:** `postgresql`. The database moves out of `flux-system`.

## Today (checked 2026-11-12)

| What | Value |
|---|---|
| Server | Bitnami chart 18.5.14 (OCIRepository `repos/postgresql-repo.yaml`), PostgreSQL 18.4, in namespace `flux-system`, data on the PVC `postgresql-data-qnap` |
| Reached at | `postgresql.flux-system.svc.cluster.local` by every app in the cluster; `192.168.1.232` (MetalLB) for psql/DBeaver on the LAN, as the app READMEs say |
| Data | 31 databases, about 1.2 GB. spacetraders is 566 MB; most are around 8 MB |
| Roles | the `postgres` superuser, plus 12 app roles (the Zeef apps, spacetraders, `spacetraders_ro`, charactercreator, datumprikker) |
| Connects as `postgres` | adventureengine, armabotcs, bot-on-the-clocktower, curatool, dungeontable, ebi-cs-api, kluskat, plotboek-generator (their databases are owned by `postgres`), and the backup CronJob |
| Extensions | none besides `plpgsql`. Bitnami preloads `pgaudit`, but nothing uses it |
| FIPS | the Bitnami image runs PostgreSQL in FIPS mode, where `md5()` fails (why Chaptarr isn't on it; see `apps/zeef/chaptarr.yaml`). CNPG's images don't, which changes nothing for the import |
| Load | 38 of 100 connections |
| Backup | `infrastructure/postgresql-backup/`: nightly `pg_dumpall` to NFS, 7 kept |

Unused:

- VortexPlotboek, VortexPlotboekLocal, VortexLnv, VortexLnvLocal, LanderijenVolken, werkplaats.
  Only VortexPlotboek is kept (see "Decided").
- chaptarr-main, chaptarr-log, chaptarr-cache, with no connections. Chaptarr runs on SQLite, and
  these are left over from trying PostgreSQL first. Not decided yet: see "Before building".

## Target

- **Operator:** chart `cloudnative-pg` 0.29.x (CNPG 1.30) from
  `https://cloudnative-pg.github.io/charts`. A new HelmRepository goes in `repos/` and the
  HelmRelease in namespace `cnpg-system`.
- **Cluster `postgres` in a new namespace `postgresql`,** which gets the database out of
  `flux-system`:
  - `instances: 1`, storage `qnap-nfs`.
  - `imageName` pinned to an exact `ghcr.io/cloudnative-pg/postgresql:18.x-system-trixie` tag.
  - `postgresql.parameters` carries over today's settings: shared_buffers 256MB, work_mem 4MB,
    maintenance_work_mem 64MB, effective_cache_size 768MB, max_wal_size 2GB, min_wal_size 256MB,
    checkpoint_timeout 10min, checkpoint_completion_target 0.9, wal_compression on,
    max_connections 100. No pgaudit.
  - Resources as today: requests 250m CPU / 512Mi, memory limit 1Gi.
  - `enableSuperuserAccess: true` with `superuserSecret`, holding **the same password** as
    today, because eight apps and the backup connect as `postgres`. CNPG wants a secret with
    `username` and `password` keys, which a new `OnePasswordItem` in `postgresql` can provide.
  - CNPG's own Services (`postgres-rw`, `-ro`, `-r`), plus
    `managed.services.additional`: a `rw` Service of type LoadBalancer with
    `metallb.io/loadBalancerIPs: 192.168.1.232`. LAN clients keep their address.
  - Prometheus metrics: CNPG serves them on port 9187. Pod annotations through
    `inheritedMetadata` let the existing `kubernetes-pods` job scrape them.
- **The old DNS name stays.** Once Bitnami is gone, an `ExternalName` Service `postgresql` in
  `flux-system` points at `postgres-rw.postgresql.svc.cluster.local`. No app changes at the
  switch-over. The apps can move to the new name later, one at a time, and the ExternalName goes
  last.
- **Data:** `bootstrap.initdb.import`, type `monolith`, from an `externalClusters` entry for the
  Bitnami server (as `postgres`), with all the app roles. CNPG runs `pg_dump`/`pg_restore` itself,
  and only reads from the source. The databases it lists:
  - **Apps:** adventure, ArmaBotCs, BotOnTheClocktower, charactercreator, curatool, datumprikker,
    dungeontable, ebi_cs_api, KlusKat, plotboek_generator, spacetraders.
  - **Zeef:** audiobookrequest, bazarr, cleanuparr, prowlarr-main, prowlarr-log, radarr-main,
    radarr-log, seerr, sonarr-main, sonarr-log.
  - **Kept just in case:** VortexPlotboek.
  - **Open:** chaptarr-main, chaptarr-log, chaptarr-cache (see "Before building").
  - **Not imported:** the five dropped databases above, and `postgres` itself, which CNPG
    creates.
- **Backup:** the nightly `pg_dumpall` CronJob stays, through the same DNS name. CNPG's own
  backups (Barman) need object storage, which could come from the QNAP's S3 service later. That's
  out of scope here.

## Steps

1. **Rehearsal, with no downtime.** A throwaway Cluster in its own namespace imports everything
   from the running Bitnami server while the apps keep running. Then compare, and delete it:
   - the databases and their owners;
   - the roles and their memberships;
   - row counts for the biggest tables (spacetraders, prowlarr, sonarr).

   This shows whether `monolith` keeps the `postgres`-owned databases and the app roles' grants
   exactly as they are, before anything depends on it.
2. **PR A, with no downtime:** the operator, its HelmRepository, the `postgresql` namespace and
   the superuser `OnePasswordItem`. Then check that the operator and its webhook are Ready.
3. **The downtime window.** Every app that uses PostgreSQL is down, for an estimated 15–30
   minutes.
   1. Take a fresh `pg_dumpall` and a QNAP snapshot of the postgres share.
   2. Suspend the Flux `apps` Kustomization, so it doesn't scale the apps back up, then scale
      every PostgreSQL user to 0: the 11 apps in MAP.md plus Sonarr, Radarr, Prowlarr, Seerr,
      Bazarr, Cleanuparr and AudioBookRequest.
   3. **PR B:** the Cluster with the import. Wait for it to be healthy, then repeat the
      rehearsal's checks.
   4. **PR C:**
      - Remove the Bitnami HelmRelease and the OCIRepository, and add the ExternalName Service.
      - Keep `postgresql-data-qnap`, with Flux pruning off, for rollback.
      - The old Service has the stale ServiceLB finalizer, so its deletion needs it removed by
        hand (as with ingress-nginx).
      - MetalLB then hands .232 to CNPG's LoadBalancer.
   5. Resume `apps`. Flux restores the replica counts, and the apps reconnect through the
      ExternalName.
4. **Verify:**
   - every app's logs and pages;
   - psql on 192.168.1.232 from the LAN;
   - a manual run of the backup CronJob;
   - the Grafana alerts.
5. **Later:**
   - delete the old volume after a few weeks;
   - move the apps to `postgres-rw.postgresql.svc.cluster.local` and drop the ExternalName;
   - update MAP.md and the app READMEs.

## Rollback

- **Before PR C:** delete the CNPG Cluster. Bitnami hasn't been touched.
- **After PR C:** put the Bitnami HelmRelease and OCIRepository back. The data volume is still
  there. Anything written to CNPG since the switch would need a dump and restore back.

## Changed while building

- **Image flavour:** `standard-trixie`, not `system-trixie`. `system` is deprecated, and `standard`
  has the `en_US.UTF-8` locale every database uses.
- **The superuser secret:** no new 1Password item; the existing `postgresql-admin-secret` item got
  `username` and `password` fields.
- **Chaptarr's databases and role:** left out.
- **`fsGroupChangePolicy: OnRootMismatch`** in `spec.podSecurityContext`: without it each pod start
  spent minutes re-applying the group to every file over NFS.
- **PR C became two:** C1 removed Bitnami, C2 added the ExternalName and .232. In one PR, Helm's
  uninstall would have deleted the new Service of the same name.
- **Metrics:** not done. Annotating the pods through `inheritedMetadata` would annotate the
  Services too, and Prometheus would scrape the same metrics several times over.

## Left to do

1. **After a few weeks:** delete `infrastructure/postgresql/postgresql-data-pvc.yaml` (the old data;
   Flux then deletes it). The last dump taken from the Bitnami server, `postgres-2026-11-12.sql.gz`
   on the backup volume, rotates out by itself after a week.
2. **Metrics:** a Prometheus scrape job for pods with the `cnpg.io/cluster` label, port 9187.
3. **Move the apps** to `postgres-rw.postgresql.svc.cluster.local` one at a time, then remove the
   ExternalName (`infrastructure/postgresql/postgresql-service.yaml`) and update the app READMEs.
