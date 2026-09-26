# Cluster notes

## 2026-09-26 — health check and cleanup

To understand this phase, start by reading this file top to bottom, then
[infrastructure/monitoring/loki-release.yaml](infrastructure/monitoring/loki-release.yaml),
[infrastructure/postgresql/postgresql-release.yaml](infrastructure/postgresql/postgresql-release.yaml) and
[docs/ingress-nginx-migration-plan.md](docs/ingress-nginx-migration-plan.md).

### What was wrong

| Finding | Since | Fix in this phase |
|---|---|---|
| Loki never ran; Promtail dropped every log line; the "Error logs detected" alert could not evaluate | 2026-06-18 (install) | Loki storage class set explicitly (chart has no `existingClaim`); reset runbook step 2 |
| `longhorn` StorageClass still marked default (next to `local-path`) although Longhorn was gone — this is what caught Loki | 2026-05-29 | Runbook step 3 removes Longhorn completely |
| `longhorn-system` stuck Terminating: 18 `longhorn.io` objects with finalizers nothing will clear, 22 CRDs, CSIDriver, PriorityClass, RBAC, two Released PVs | 2026-05-29 | Runbook step 3 |
| k3s ServiceLB and MetalLB both handling the LoadBalancer Services; ServiceLB overwrote their status with node IPs every ~6h and bound 80/443/5432 on every node | since MetalLB | Runbook step 4 (disable ServiceLB) |
| sts2viewer failing (`database "sts2" does not exist`), spacetraders ingress/cert without an app, empty aiusagemonitor namespace | — | Removed from the repo (see file map) |
| PostgreSQL on `bitnami/postgresql:latest` (already drifted 18.3 → 18.4); a major bump would not start on the 18 data dir | — | Digest pinned |
| `postgresql` Service owned by both Helm (ClusterIP) and `postgresql-loadbalancer.yaml` (LoadBalancer) | — | Both now say LoadBalancer; step 2 in "Follow-ups" removes the Flux copy |
| PostgreSQL killed instead of shut down during node drains (crash recovery on every start) | — | preStop `pg_ctl stop -m fast` + 60s grace |
| Rolling reboot took all 3 nodes in ~8 minutes, pods moved twice, Postgres down ~7 min, armabotcs/curatool crash-looped, adventureengine restarted by its liveness probe | every kured run | kured lock delay + taint, wait-for-postgres init containers, tcpSocket liveness, 2 ingress replicas, CoreDNS ×2 (runbook step 5) |
| grafana-internal's LAN-only allowlist matched everyone: with `externalTrafficPolicy: Cluster` nginx only saw node/pod IPs | — | ingress-nginx Service now `externalTrafficPolicy: Local` |
| Every app's TLS secret named `ebi-cs-api-tls` (copy-paste) | — | Per-app `<app>-tls` names; runbook step 6 removes the old secrets |
| AdventureEngine regenerated its DataProtection keys on every restart (everyone logged out) | — | Keys on an NFS volume |
| Grafana: repo dashboards never provisioned, Flux dashboard queried metrics that don't exist, Promtail's `extraScrapeConfigs` silently ignored (not a chart value), Angular piechart plugin | — | Dashboards provisioned from `infrastructure/monitoring/dashboards/`, Flux state exported via kube-state-metrics, dead Promtail config dropped |
| Deprecated Flux APIs (`helm.toolkit.fluxcd.io/v2beta1`, `source.toolkit.fluxcd.io/v1beta2` HelmRepositories); system-upgrade-controller applied from `releases/latest` | — | Bumped to v2/v1; SUC pinned to v0.20.2 |
| ingress-nginx retired upstream (no security fixes since March 2026) | — | Plan in `docs/ingress-nginx-migration-plan.md` |

### Key decisions

- **Loki on NFS via the chart's volumeClaimTemplate.** The chart cannot use a pre-made claim, so `loki-qnap` is unused (remove it, see "Deletions left to do"). Retention is 31 days; without compactor retention Loki keeps logs forever.
- **Promtail kept for now.** It is deprecated in favour of Grafana Alloy, but switching agents while also fixing Loki doubles the unknowns. Moving to Alloy is in the version-update list.
- **Postgres image pinned by digest, not tag.** Bitnami's free catalog only publishes `latest`, so a digest is the only stable reference. Bump it deliberately. Long-term: move off the Bitnami chart (CloudNativePG).
- **Postgres Service moves to Helm in two commits.** Removing `postgresql-loadbalancer.yaml` in the same commit would let Flux prune the Service Helm also owns. The Flux copy now carries `kustomize.toolkit.fluxcd.io/prune: disabled`; delete the file only after this phase has reconciled. `upgrade.force` was dropped from the Postgres HelmRelease because a forced (replace) upgrade strips that annotation.
- **`spec.loadBalancerIP`, not the `metallb.io/loadBalancerIPs` annotation, for Postgres.** MetalLB refuses a Service that has both, and the Flux copy still sets the field. Switch to the annotation once Helm is the only owner.
- **Liveness ≠ readiness.** Liveness/startup probes must not include dependency checks (a DB outage then restarts healthy pods). adventureengine now uses tcpSocket for both; readiness keeps `/healthz`. The proper app-side fix is separate `/healthz/live` and `/healthz/ready` endpoints.
- **CoreDNS is scaled with kubectl, not Git.** It is k3s-managed. Its k3s manifest doesn't set `replicas` (checked from the `objectset.rio.cattle.io/applied` annotation), so a one-time scale sticks; having Flux own a partial k3s object is riskier than that.
- **Flux dashboard/alerts use kube-state-metrics custom resource state** (`gotk_resource_info`), the approach from fluxcd/flux2-monitoring-example. Its GVK list must match the API versions Flux serves (OCIRepository is `v1beta2` on Flux 2.5).

### Gotchas

- **Helm chart values that don't exist are silently ignored.** That is how Loki (`existingClaim`) and Promtail (`extraScrapeConfigs`) broke without any error. Check new keys against the chart's `values.yaml` for the installed version.
- **Grafana only reads alert provisioning at startup.** After editing `grafana-alerting-provisioning.yaml` alone, run `kubectl -n monitoring rollout restart deployment grafana`. Dashboards reload by themselves.
- **mcp-k8s is read-only** and `list-k8s-resources` returns only names (Deployments aside): use `get-k8s-resource` with a `go_template` per object.
- **Renaming a TLS secret re-issues the certificate.** For a minute or two nginx serves its default certificate for that host.
- **kured `period` is the check interval**, not a delay between nodes. `lockReleaseDelay` is the delay.

### What happens when this lands

- PostgreSQL restarts once (new image reference + shutdown hook): about a minute of database downtime. armabotcs and curatool now wait for it instead of crash-looping.
- The 8 renamed sites briefly serve nginx's default certificate while their new certificates are issued.
- ingress-nginx goes to 2 replicas and `externalTrafficPolicy: Local`; MetalLB moves the .230 announcement to a node running a controller pod (a blip of seconds).
- Grafana restarts and loads the new dashboards (folder "Gembercluster") and alerts. Expect a "Pod stuck Pending" / "Flux resource not ready" email about Loki if runbook step 2 isn't done within 15 minutes.
- The sts2viewer, spacetraders and aiusagemonitor namespaces are deleted with everything in them. Their 1Password items and any spacetraders database in Postgres are not touched.

### Runbook (cluster-side steps, in order)

Commands are bash (Git Bash works). kubectl uses the `default` context.

**0. Before disabling ServiceLB (step 4), check:**
- The router's port-forward for 80/443 points at **192.168.1.230** (MetalLB), not a node IP (192.168.1.201–203). Node IPs stop answering on 80/443 once ServiceLB is off.
- Nothing on the LAN talks to Postgres via a node IP on 5432; use 192.168.1.232.
- Grafana is at `http://192.168.1.230/grafana`.

**1. Merge/push the changes** and wait until Flux has applied them:
```bash
kubectl -n flux-system get kustomizations      # all Ready at the new revision
kubectl get helmrelease -A
```

**2. Reinstall Loki.** Its first install failed and the StatefulSet's volume template can't be changed in place, so start over. Flux recreates the HelmRelease from Git within a minute; deleting the StatefulSet also deletes the stuck `storage-grafana-loki-0` claim (owner reference).
```bash
kubectl -n monitoring get helmrelease grafana-loki -o jsonpath='{.spec.values.singleBinary.persistence.storageClass}'; echo   # must print qnap-nfs
kubectl -n monitoring delete helmrelease grafana-loki
kubectl -n monitoring get pvc,pods -l app.kubernetes.io/name=loki -w   # claim Bound on qnap-nfs, pod Running
```

**3. Remove Longhorn completely.**
```bash
# Strip the finalizers nothing will ever clear (no Longhorn controller left); the namespace then finishes deleting
for crd in $(kubectl get crd -o name | grep 'longhorn.io' | cut -d/ -f2); do
  for obj in $(kubectl -n longhorn-system get "$crd" -o name 2>/dev/null); do
    kubectl -n longhorn-system patch "$obj" --type merge -p '{"metadata":{"finalizers":null}}'
  done
done
kubectl get namespace longhorn-system            # gone after a minute

# Cluster-wide leftovers
kubectl get crd -o name | grep 'longhorn.io' | xargs kubectl delete
kubectl delete storageclass longhorn longhorn-static
kubectl delete csidriver driver.longhorn.io
kubectl delete priorityclass longhorn-critical
kubectl delete clusterrolebinding longhorn-bind longhorn-support-bundle
kubectl delete clusterrole longhorn-role

# The two Released PVs: old data-postgresql-0 (24Gi) and postgresql-backup-pvc (5Gi) from before the NFS move
for pv in pvc-f9d51161-e669-49ff-a007-2c377c70a523 pvc-413849e0-1100-4d60-917c-8a59a4f348ff; do
  kubectl delete pv "$pv" --wait=false
  kubectl patch pv "$pv" --type merge -p '{"metadata":{"finalizers":null}}'
done

# Replica data still on each node's disk (irreversible: this is the only copy of the pre-May Postgres data)
ssh <user>@192.168.1.201 'sudo du -sh /var/lib/longhorn; sudo rm -rf /var/lib/longhorn'   # repeat for .202 and .203
```

**4. Disable k3s ServiceLB** so MetalLB is the only load balancer. One server at a time:
```bash
ssh <user>@192.168.1.201
sudo cat /etc/rancher/k3s/config.yaml   # add `servicelb` to the `disable:` list (traefik is probably already there)
                                        # (if k3s flags live in the systemd unit instead, add --disable servicelb there and daemon-reload)
sudo systemctl restart k3s
exit
kubectl get nodes                       # wait for Ready, then do .202 and .203
```
Afterwards:
```bash
kubectl -n kube-system get ds -l svccontroller.k3s.cattle.io/svcnamespace    # svclb-* should be gone; if not:
kubectl -n kube-system delete ds -l svccontroller.k3s.cattle.io/svcnamespace
kubectl get svc -A | grep LoadBalancer                                       # EXTERNAL-IP only 192.168.1.230 / .232
```

**5. Two CoreDNS replicas** (the spread constraint puts them on different nodes):
```bash
kubectl -n kube-system scale deployment coredns --replicas=2
```

**6. Remove the old TLS secrets** once the new certificates are Ready (not in `ebi-cs-api`, which still uses its `ebi-cs-api-tls`):
```bash
kubectl get certificate -A
for ns in adventureengine cluster-healthcheck cov-website curatool dungeontable file-server hackerminigames vortexplotboek; do
  kubectl -n "$ns" delete secret ebi-cs-api-tls
done
```

**7. Point the apps at Postgres by DNS name.** In 1Password (vault Gembercluster), change the host in the connection strings from `192.168.1.232` to `postgresql.flux-system.svc.cluster.local`. The logs showed armabotcs, curatool and adventureengine use `.232`; bot-on-the-clocktower, ebi-cs-api, dungeontable and vortexplotboek also read `ConnectionStrings__Postgres` from a secret, so check those too. Then restart each deployment:
```bash
kubectl -n armabotcs rollout restart deployment armabotcs   # etc. for each changed app
```

### Follow-ups

- **Postgres Service step 2** (after this phase has reconciled): check the annotation is on the live Service, then delete `infrastructure/postgresql/postgresql-loadbalancer.yaml` and its line in `infrastructure/postgresql/kustomization.yaml`, and push.
  ```bash
  kubectl -n flux-system get svc postgresql -o jsonpath='{.metadata.annotations.kustomize\.toolkit\.fluxcd\.io/prune}'; echo   # must print disabled
  ```
  After that, Postgres' IP can move from `loadBalancerIP` to the `metallb.io/loadBalancerIPs` annotation.
- **Deletions left to do** (the session wasn't allowed to delete these):
  - `infrastructure/pvcs/loki.yaml` and its line in `infrastructure/pvcs/kustomization.yaml` (unused `loki-qnap` claim; Flux then deletes the empty NFS volume)
  - `infrastructure/monitoring/kube-state-metrics-release.yaml` (never referenced; the prometheus chart bundles kube-state-metrics)
  - `ingress/grafana-ingress.yaml` (never referenced; was a public Grafana ingress)
  - `dashboards/` (superseded by `infrastructure/monitoring/dashboards/`)
- **DataProtection keys** for vortexplotboek and dungeontable: same warning as adventureengine (keys in `/root/.aspnet/DataProtection-Keys`). vortexplotboek has Google/OIDC login, so restarts log users out. Same fix, or persist keys in-app.
- **Version updates** (through this repo; mcp-k8s can't change anything and Flux would revert out-of-band changes):
  1. Flux 2.5 → current: regenerate `clusters/home/flux-system/gotk-components.yaml` with the flux CLI (not installed on this machine), then move OCIRepository to `v1`.
  2. ingress-nginx → Traefik: `docs/ingress-nginx-migration-plan.md`.
  3. Promtail → Grafana Alloy.
  4. prometheus chart 25.x → current (Prometheus 3), grafana chart 8.x → current, MetalLB 0.14 → 0.15, system-upgrade-controller past v0.20.2, cert-manager `installCRDs` → `crds.enabled`.
  5. Bitnami PostgreSQL → CloudNativePG.

### File map

- Removed: `apps/{sts2viewer,spacetraders,aiusagemonitor}/`, `ingress/{sts2viewer,spacetraders,spacetraders-assets}-ingress.yaml`, `namespaces/{sts2viewer,spacetraders,aiusagemonitor}-namespace.yaml`; references dropped from `apps/`, `ingress/` and `namespaces/kustomization.yaml`.
- Monitoring: `infrastructure/monitoring/{loki,grafana,promtail,prometheus}-release.yaml`, `grafana-alerting-provisioning.yaml` (5 new cluster-health alerts), `kustomization.yaml` (dashboards ConfigMap), `dashboards/*.json` (new).
- PostgreSQL: `infrastructure/postgresql/postgresql-release.yaml`, `postgresql-loadbalancer.yaml`.
- Reboots: `infrastructure/kured/kured-release.yaml`, `infrastructure/nginx/nginx-release.yaml`, `apps/adventureengine/deployment.yaml`, `apps/armabotcs/deployment.yaml`, `apps/curatool/web-deployment.yaml`.
- AdventureEngine keys: `infrastructure/pvcs/adventureengine.yaml` (+ kustomization), `apps/adventureengine/deployment.yaml`.
- TLS: `ingress/*-ingress.yaml` (8 secret names).
- APIs/pins: `repos/*.yaml`, `infrastructure/certmanager/certmanager-helmrelease.yaml`, `infrastructure/system-upgrade/kustomization.yaml`.
- Docs: `NOTES.md`, `docs/ingress-nginx-migration-plan.md`.
