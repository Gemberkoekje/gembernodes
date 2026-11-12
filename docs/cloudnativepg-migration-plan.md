# Bitnami PostgreSQL → CloudNativePG

**Status: plan, waiting on the decisions at the bottom.** Nothing in this document has been applied.

## Why

- **The Bitnami chart is a dead end.** Bitnami's free catalog only publishes `latest`, so the
  image is pinned by digest and every bump is manual guesswork.
- **CloudNativePG (CNPG) is maintained.** It's an operator, and its images have real version tags.
  It handles shutdown, crash recovery, failover and upgrades itself, where this repo now hand-tunes
  probes and a `preStop` hook.

## Decided

- **One instance on the NAS (`qnap-nfs`), like today** (2026-11-12). No local-disk replicas: the
  nodes' disks are small, and Longhorn once filled them.

## Today (checked 2026-11-12)

| What | Value |
|---|---|
| Server | Bitnami chart 18.5.14 (OCIRepository `repos/postgresql-repo.yaml`), PostgreSQL 18.4, in namespace `flux-system`, data on the PVC `postgresql-data-qnap` |
| Reached at | `postgresql.flux-system.svc.cluster.local` by every app in the cluster; `192.168.1.232` (MetalLB) for psql/DBeaver on the LAN, as the app READMEs say |
| Data | 31 databases, about 1.2 GB. spacetraders is 566 MB; most are around 8 MB |
| Roles | the `postgres` superuser, plus 12 app roles (the Zeef apps, spacetraders, `spacetraders_ro`, charactercreator, datumprikker) |
| Connects as `postgres` | adventureengine, armabotcs, bot-on-the-clocktower, curatool, dungeontable, ebi-cs-api, kluskat, plotboek-generator (their databases are owned by `postgres`), and the backup CronJob |
| Extensions | none besides `plpgsql`. Bitnami preloads `pgaudit`, but nothing uses it |
| Load | 38 of 100 connections |
| Backup | `infrastructure/postgresql-backup/`: nightly `pg_dumpall` to NFS, 7 kept |

Probably unused, and already on the clean-up list: VortexPlotboek, VortexPlotboekLocal, VortexLnv,
VortexLnvLocal, LanderijenVolken, werkplaats.

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
  Bitnami server (as `postgres`). It lists the 25 databases in use and all the app roles. CNPG
  runs `pg_dump`/`pg_restore` itself, and only reads from the source.
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

## Decisions needed

1. **When:** the downtime window (all PostgreSQL apps, est. 15–30 min).
2. **The superuser secret:** a new 1Password item (e.g. `postgresql-superuser` in vault
   Gembercluster) with fields `username` = `postgres` and `password` = today's postgres password.
   You create it, because it holds the password.
3. **The six unused databases:** leave them out of the import? They stay in the old volume and in
   the last nightly dumps.
4. **The namespace:** `postgresql` (recommended), or keep the database in `flux-system`.
