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

- **Loki on NFS via the chart's volumeClaimTemplate.** The chart cannot use a pre-made claim, so the old `loki-qnap` claim was removed. Retention is 31 days; without compactor retention Loki keeps logs forever.
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
- **`fsGroup` on NFS volumes is slow with the default `fsGroupChangePolicy: Always`.** The kubelet re-applies group ownership to every file on each mount; for the PostgreSQL data directory that took about 4 minutes per pod start (it was also why Postgres took 4+ minutes to return after every reboot). Postgres, Grafana and Prometheus now use `OnRootMismatch`; Loki's chart sets it by default.
- **HelmRelease `timeout` defaults to 5m, and a timed-out upgrade is remediated by a rollback**, which restarts the pods again. Stateful releases with slow starts need a longer `spec.timeout` (Postgres: 15m).
- **Old container images pile up on the nodes.** Every deploy with a new tag leaves the previous image behind, and the kubelet only garbage-collects them above 85% disk use; by September they took ~27 GB on gembernode-01. `crictl rmi --prune` needs `--timeout 120s`: with the default 2s most deletions fail with `DeadlineExceeded` (harmless, but nothing gets freed).

### What happens when this lands

- PostgreSQL restarts (new image reference + shutdown hook). Planned as about a minute of downtime; it took ~20 minutes, see "Rollout log" below. armabotcs and curatool wait for it on start instead of crash-looping.
- The 8 renamed sites briefly serve nginx's default certificate while their new certificates are issued.
- ingress-nginx goes to 2 replicas and `externalTrafficPolicy: Local`; MetalLB moves the .230 announcement to a node running a controller pod (a blip of seconds).
- Grafana restarts and loads the new dashboards (folder "Gembercluster") and alerts. Expect a "Pod stuck Pending" / "Flux resource not ready" email about Loki if runbook step 2 isn't done within 15 minutes.
- The sts2viewer, spacetraders and aiusagemonitor namespaces are deleted with everything in them. Their 1Password items and any spacetraders database in Postgres are not touched.

### Rollout log (2026-09-26)

- ~10:05Z pushed `0814511`; all eight Kustomizations applied it within 73 seconds.
- The PostgreSQL upgrade hit the 5m Helm timeout: the new pod spent ~4.5 minutes on the NFS ownership walk (see Gotchas), Flux rolled back, and the rollback pod did the walk again. That repeated once more before `d159e12` (`fsGroupChangePolicy: OnRootMismatch`, `timeout: 15m`) was picked up. The database was unavailable from about 10:07 to 10:27Z, apart from two short windows; the final upgrade (10:26–10:27Z) took about a minute. No data was affected: each stop was a crash-style stop recovered from WAL.
- armabotcs and curatool passed their wait-for-postgres init step during one of those short windows, then crash-looped until the kubelet's backoff retried at 10:29Z. The init step only covers the first start.
- Everything else rolled out cleanly: the removed namespaces are gone, all 10 certificates were re-issued under the new names, ingress-nginx runs 2 replicas with `externalTrafficPolicy: Local` on .230, kured has its new settings, kube-state-metrics exports `gotk_resource_info`, and Grafana loaded the dashboards and alert rules.
- Loki still needs runbook step 2. Until then Grafana sends alert emails for it (DatasourceError from the error-log rule, then "Pod stuck Pending" and "Flux resource not ready").

### Runbook (cluster-side steps, in order)

Status 2026-09-26: all steps are done (Loki runs on `qnap-nfs`, Longhorn is gone from the cluster
and the node disks, ServiceLB is disabled on all three servers, CoreDNS runs 2 replicas, the old
TLS secrets are deleted, every app reaches Postgres by its DNS name).

Node disks, same day: after removing `/var/lib/longhorn` (8.6 GB on gembernode-02, empty elsewhere)
and pruning unused container images (`sudo k3s crictl --timeout 120s rmi --prune` on each node,
~45 GB in total), root disk usage went from 74% / 66% / 65% to 34% / 22% / 33%.

How k3s is configured on these nodes (found while doing step 4): there is no `config.yaml`. Each
node's flags come from `/etc/systemd/system/k3s.service.d/override.conf`, identical on all three:
`ExecStart=/usr/local/bin/k3s server --disable traefik --disable servicelb`. That override replaces
the base unit's command line, which had `--cluster-init` (gembernode-01) or
`--server https://192.168.1.201:6443` (02 and 03). This is harmless while each node keeps its etcd
data, but a node whose data is wiped would start a new cluster instead of rejoining; restore the
`--server` flag on 02/03 (separately, it changes how the node starts) before ever doing that.
Disabling ServiceLB needed no special ordering: each server was restarted one at a time with no
critical-config error, and k3s deleted the `svclb-*` DaemonSets itself after the last one.

OS updates on the nodes (2026-09-26): Ubuntu's `unattended-upgrades` only installs security
updates by default, so ~60 regular updates had piled up on each node. Each node now has
`/etc/apt/apt.conf.d/51unattended-upgrades-updates`, which adds the
`"${distro_id}:${distro_codename}-updates"` origin, and all three were caught up (24.04.5).
Updates now install daily. When one needs a reboot, Ubuntu creates `/var/run/reboot-required`
(the login banner then says "System restart required") and kured reboots the node in its window.
kured only checks for that file between 02:00 and 05:00 UTC and logs nothing outside the
window, so its logs can't show whether a reboot is pending. Firmware: the OptiPlex 9020's BIOS
can't be updated through fwupd, but its Secure Boot `db` (Microsoft UEFI CA 2023) and `dbx`
updates can. Those were applied on gembernode-01 first. They take effect at the next boot, which
is done through kured with `sudo touch /var/run/reboot-required`; nodes 02 and 03 follow after
that works.

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

**4. Disable k3s ServiceLB** so MetalLB is the only load balancer (done 2026-09-26). On each server, one at a time:
```bash
sudo sed -i 's|^ExecStart=/usr/local/bin/k3s server --disable traefik$|ExecStart=/usr/local/bin/k3s server --disable traefik --disable servicelb|' /etc/systemd/system/k3s.service.d/override.conf
sudo systemctl daemon-reload
sudo systemctl restart k3s
sudo k3s kubectl get nodes              # wait for Ready before the next server
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
Status 2026-09-26: done. All seven apps connect to `postgresql.flux-system.svc.cluster.local`
and were restarted. The 1Password operator syncs every 10 minutes (`POLLING_INTERVAL=600`) and
doesn't restart pods (`AUTO_RESTART=false`), so after changing an item, wait for the next sync
(its log says `Updating kubernetes secret '<name>'`) and then restart the deployment.

### Follow-ups

- **Postgres Service step 2: done** (2026-09-26). `postgresql-loadbalancer.yaml` is removed; the live Service kept its `kustomize.toolkit.fluxcd.io/prune: disabled` annotation, so Flux left it in place and Helm is now its only owner. To move Postgres' IP to the `metallb.io/loadBalancerIPs` annotation later, drop `primary.service.loadBalancerIP` in the same change.
- **Done 2026-09-26:** unused manifests deleted (`infrastructure/pvcs/loki.yaml`, `infrastructure/monitoring/kube-state-metrics-release.yaml`, `ingress/grafana-ingress.yaml`, `dashboards/`); "Node disk filling up" alert (root filesystem over 85% for 30 minutes); `fsGroupChangePolicy: OnRootMismatch` for Grafana and Prometheus (Loki's chart already sets it); DataProtection keys persisted for vortexplotboek and dungeontable (`infrastructure/pvcs/{vortexplotboek,dungeontable}.yaml`), as for adventureengine.
- **Version updates** (through this repo; mcp-k8s can't change anything and Flux would revert out-of-band changes):
  1. Flux 2.5 → current: regenerate `clusters/home/flux-system/gotk-components.yaml` with the flux CLI (not installed on this machine), then move OCIRepository to `v1`.
  2. ingress-nginx → Traefik: `docs/ingress-nginx-migration-plan.md`.
  3. Promtail → Grafana Alloy.
  4. prometheus chart 25.x → current (Prometheus 3), grafana chart 8.x → current, MetalLB 0.14 → 0.15, system-upgrade-controller past v0.20.2, cert-manager `installCRDs` → `crds.enabled`.
  5. Bitnami PostgreSQL → CloudNativePG.

### File map

- Removed: `apps/{sts2viewer,spacetraders,aiusagemonitor}/`, `ingress/{sts2viewer,spacetraders,spacetraders-assets}-ingress.yaml`, `namespaces/{sts2viewer,spacetraders,aiusagemonitor}-namespace.yaml`; references dropped from `apps/`, `ingress/` and `namespaces/kustomization.yaml`.
- Monitoring: `infrastructure/monitoring/{loki,grafana,promtail,prometheus}-release.yaml`, `grafana-alerting-provisioning.yaml` (5 new cluster-health alerts), `kustomization.yaml` (dashboards ConfigMap), `dashboards/*.json` (new).
- PostgreSQL: `infrastructure/postgresql/postgresql-release.yaml`; `postgresql-loadbalancer.yaml` removed in the follow-up.
- Reboots: `infrastructure/kured/kured-release.yaml`, `infrastructure/nginx/nginx-release.yaml`, `apps/adventureengine/deployment.yaml`, `apps/armabotcs/deployment.yaml`, `apps/curatool/web-deployment.yaml`.
- AdventureEngine keys: `infrastructure/pvcs/adventureengine.yaml` (+ kustomization), `apps/adventureengine/deployment.yaml`.
- TLS: `ingress/*-ingress.yaml` (8 secret names).
- APIs/pins: `repos/*.yaml`, `infrastructure/certmanager/certmanager-helmrelease.yaml`, `infrastructure/system-upgrade/kustomization.yaml`.
- Docs: `NOTES.md`, `docs/ingress-nginx-migration-plan.md`.

## 2026-10-02 — error-log alert emails say what failed

The "Error logs detected" email only said `B0=1`: the rule added every matching line into one
number without labels (a classic condition), so it could not say which app or which line.

The rule (`loki-error-logs` in `infrastructure/monitoring/grafana-alerting-provisioning.yaml`) now:

- alerts per namespace, and the subject names it: `[FIRING:1] Error logs detected armabotcs (Alerts)`;
- says in the summary how many lines contained "error" in the last 5 minutes, and quotes the most
  frequent of those lines in the description (cut at 300 characters);
- adds View dashboard / View panel buttons that open the new "Error logs" dashboard
  (`dashboards/error-logs-dashboard.json`) from an hour before the alert started until the email
  was sent.

It still needs errors in two consecutive 5-minute evaluations to fire, now per namespace.
`loki-release.yaml` gained `min_sharding_lookback: 15m` (see Gotchas).

### Gotchas

- **A Grafana rule is NoData as soon as any of its queries returns nothing**, an error included,
  and NoData is OK (silent) for this rule. So the query that quotes the line must never fail where
  the count succeeds.
- **Loki applies `max_query_series` (500) to each shard's result, before `topk`.** The quote query
  groups by line, so once more than 500 different lines matched in 5 minutes it failed, which muted
  the alert while an app was flooding errors. With `min_sharding_lookback: 15m`, queries (and the
  15-minute splits of longer ones) that end in the last 15 minutes run unsharded, and only the
  final result (one line per namespace) counts.
- **`$values` also matches query series with more labels than the alert:** the quote query's
  `{namespace, line}` series attaches to the `{namespace}` alert without becoming an alert of its
  own. When several match, the last one wins, hence `topk by (namespace) (1, ...)`.
- **Loki's `trunc` cuts bytes**, which breaks accented characters (`�`); the rule cuts with
  `regexReplaceAll`, which counts characters.
- **Grafana's default email shows `summary` and `description` as text**, other annotations as a
  plain-text table, `runbook_url` as a button, and View dashboard / View panel buttons for
  `__dashboardUid__` / `__panelId__`.

### How it was tested

Locally, not on the cluster: Grafana 11.6.1 and Loki 3.6.7 (what the `8.x` / `6.x` chart ranges
resolve to), Loki running the config chart 6.55.0 renders from `loki-release.yaml`, Grafana
provisioned with this repo's alerting ConfigMap and dashboards, fake pod logs pushed into Loki, and
the emails caught by a local SMTP server and rendered in Chromium. The current rule's email came out
identical to the real one. Cases: two namespaces erroring, 1,200 different lines in 5 minutes (the
quote query failed on it before the Loki change), a 2,000-character line, an accented line, HTML in a
line (escaped), and errors in a namespace the rule doesn't watch (ignored). The upgrade was replayed
too: old rule firing, then Grafana restarted on the new provisioning.

### Rollout

1. Merge and let Flux apply it. Loki restarts by itself (its config changed); Grafana only reads
   alert provisioning at startup, so restart it:
   ```bash
   kubectl -n monitoring rollout restart deployment grafana
   ```
2. If the old alert is firing at that moment, a `[RESOLVED] Error logs detected (Alerts)` email
   follows: it has no namespace, and the per-namespace alerts replace it.

## 2026-10-02 — CI: the repository is checked the way Flux reads it

`.github/workflows/validate.yaml` runs `scripts/validate.py` on every pull request and every push to
`main` (and on demand from the Actions tab). Problems show up as annotations on the files in the pull
request. It checks:

- every YAML/JSON file parses, without duplicate keys (YAML otherwise keeps the last one silently);
- every Flux Kustomization builds with `flux build kustomization`, as kustomize-controller does;
- the result passes kubeconform in strict mode, so a misspelled field fails: Kubernetes 1.36
  schemas, Flux's schemas for the installed Flux version, and the CRD catalog for cert-manager,
  MetalLB, 1Password, Traefik and system-upgrade-controller;
- Flux references resolve: Kustomization `sourceRef`/`dependsOn`, HelmRelease chart sources,
  `dependsOn` and `valuesFrom` (a OnePasswordItem counts as the Secret of the same name);
- YAML/JSON inside ConfigMaps parses, and Grafana's alert rules use data sources, dashboards and
  panels that exist, and its policies use contact points that exist;
- every HelmRelease renders with its real chart and values (`helm template`) and the result passes
  kubeconform.

Three findings are warnings that don't fail the run: a file no Kustomization applies (commenting an
app out of a kustomization is allowed), a top-level HelmRelease value the chart doesn't have (the
first run found Grafana's `replicaCount`; the chart's value is `replicas`), and a chart registry
that stays busy after two retries. Shared CI runners hit Docker Hub's limit for anonymous pulls
(the Bitnami PostgreSQL chart) now and then; that chart just goes unchecked for that run.

To run it locally: `python3 scripts/validate.py` (needs PyYAML, and `flux`, `kubeconform` and `helm`
on PATH). Versions: the flux CLI follows the `# Flux Version` line in `gotk-components.yaml`; Helm
is pinned in the workflow to what helm-controller uses, so bump it with Flux; `KUBERNETES_VERSION`
and the CRD catalog commit are at the top of the script.

What it can't see: chart values below the top level that the chart ignores (charts document many
only as comments), the contents of secrets (`valuesFrom` gets placeholders), and anything that needs
the cluster: CRDs being installed, admission webhooks, resources already owned by something else.

## 2026-10-05 — CI: a pull request's images have to exist

Asked on 2026-10-05: "Is it possible to add the 'does this version exist upstream' check to the PR
validation checks of gembernodes?" A deploy PR (an image tag bumped to a commit of another repository)
can be opened, and merged, before that repository's CI has pushed the image: Flux then rolls out a tag
the registry doesn't have, and the pods sit in ImagePullBackOff. The SpaceTraders deployments are
`Recreate`, so the old pod is already gone by then.

- `scripts/check_images.py` (Python 3 and git only) reads the `image:` lines the pull request adds or
  changes (`git diff <base>...HEAD`) and asks each image's registry for the manifest, the way
  `docker pull` does: the token service its `WWW-Authenticate` challenge names, then a `HEAD` of
  `/v2/<repository>/manifests/<tag>`. Any OCI registry works this way: ghcr.io, Docker Hub, quay.io.
- A 404 is looked for again every 30 seconds for `IMAGE_WAIT_MINUTES` (20), so a deploy PR opened while
  the image builds turns green by itself once it is pushed; after that it is an error on the line.
- A registry that won't show the image is a warning, not an error: a private package. Anonymously, on
  2026-10-05, ghcr.io showed spacetraders-api/-webui, thecuratool, hackerminigames, adventureengine
  and bot-on-the-clocktower, and refused armabotcs, cov-website, dungeontable and
  eosfrontier/ebi-cs-api (a private package answers 401, never 404, so it can't pass for a missing
  tag). The workflow's `GITHUB_TOKEN` (`packages: read`) is tried on ghcr.io for those; it reads a
  private package only once the package gives this repository access (the package's settings,
  "Manage Actions access").
- `.github/workflows/validate.yaml` runs it as the `images` job, on pull requests only.

### How it was tested

- Locally against throwaway commits: spacetraders-api set to a tag of forty zeros was an error on its
  line, spacetraders-webui set to an older tag passed, and armabotcs set to another tag was a warning.
  Without image changes the script says so and passes.

### What it can't see

- An image a Helm chart builds from separate `repository` and `tag` values; a templated reference.
- That the image runs: only that the registry has the tag.
- It doesn't block a merge by itself: `main` has no branch protection. To make it block, require the
  `images` check (and `validate`) in a branch protection rule or ruleset for `main`.

### File map

- `scripts/check_images.py`: the check.
- `.github/workflows/validate.yaml`: the `images` job.

## 2026-10-02 — SpaceTraders errors by log level

The SpaceTraders bot came back on 2026-10-02 (PR #11), and five minutes later "Error logs detected
spacetraders" fired on a healthy start. The shared rule counts lines containing "error", and the
bot logs Serilog's compact JSON, whose ordinary lines contain the word: the startup settings dump
(`Health.Errors.MaxRepeatsIn10Minutes`), a library's note at Warning ("…this is an error",
Wolverine) and the bot's own `RepeatingError` anomaly. Gemberkoekje/projects `SpaceTraders/PLAN.md`
has it as B44.

- `spacetraders` left the shared rule (`loki-error-logs`) and the "Error logs" dashboard's
  namespace list.
- A rule of its own, `spacetraders-error-logs` ("SpaceTraders logged errors"), in the same group
  and with the same timing (errors in two consecutive 5-minute evaluations), counts the bot's JSON
  lines whose level (`"@l"`) is `Error` or `Fatal`, and the lines that aren't JSON (nginx, the
  init container) containing "error". Its email quotes the most frequent line, like the shared
  rule's, and opens the new Errors panel of the SpaceTraders dashboard.

### How it was tested

- Against the cluster's Loki, read-only: over the bot's first two hours the shared rule's filter
  matched 14 of its lines, all ordinary, and the new one none. Its plain-text branch matches in
  other namespaces, so Loki takes the filter.
- Against a throwaway Loki 3.4.2 holding nine lines shaped like the bot's: the rule's count (A) was
  3 (an Error line, a Fatal line, an nginx `[error]`) and its quote (B) one of them; the settings
  dump, the Wolverine note, the anomaly line, nginx's notice and access lines and the init
  container's line didn't count. The old filter counted 5 of the 9: three false alarms, and it
  missed the Fatal line. The Errors panel showed the JSON lines by their message, the nginx line as
  it is.
- `scripts/validate.py` without kubeconform and the HelmRelease rendering (not installed on that
  PC; CI runs them): syntax, Flux builds, references, and the Grafana checks, which find the rule's
  dashboard and panel.

### Rollout

1. Merge and let Flux apply it. Grafana only reads alert provisioning at startup, so restart it:
   ```bash
   kubectl -n monitoring rollout restart deployment grafana
   ```
2. If the shared rule's alert for spacetraders is firing then, a resolved email follows.

## 2026-10-02 — SpaceTraders fleet table: where, doing, cargo, mined

The SpaceTraders dashboard's fleet table showed each ship's role, state, goal and time in state;
the contract's drone was mining at its asteroid and nothing showed it. With the bot's new metrics
(Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.7, its PR #117) the table is full width and
also shows where each ship is (the waypoint and its type, or an arrow and where it goes), what it
does, when it arrives, its cargo and capacity, and the units it mined in the dashboard's time range.
A new row under it has "Holds" (units per ship and good) and "Mined and jettisoned per hour", next
to "Ships by role and state", which moved there; the panels below moved down by that row.

- The table merges six instant queries on `ship` (Grafana's Merge transformation). An empty hold has
  no series per good, so the cargo query adds 0 for every ship with a hold (`or 0 * ...`).
- Until the bot runs an image with PR #117, the new columns and panels stay empty.
- Tested with `promtool test rules` (`prom/prometheus` v2.55.1) against synthetic series: each query
  gives the expected value, an empty hold 0 included. `scripts/validate.py` without kubeconform and
  the HelmRelease rendering: no errors.

## 2026-10-02 — SpaceTraders markets dashboard

A second SpaceTraders dashboard, "SpaceTraders markets" (`dashboards/spacetraders-markets-dashboard.json`,
uid `spacetraders-markets`): pick a system, and see its markets and shipyards as the bot has
cached them, plus the game's production chains (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice
2.8, its PR #118, which adds the metrics).

- Variables: `system` (every system with a cached market or shipyard), `waypoint` (all by default)
  and `good` (for the price graph).
- Panels: counts and the age of the oldest market data; "Places" (each market and shipyard with
  its waypoint type, data age and goods priced); "Shipyards" (ship types with price and supply);
  "Trade goods" (each good at each market: buy and sell price, volume, supply and activity as
  words); "Prices of $good" over time; the market tree for the goods traded in the system, and in a
  collapsed row for all goods.
- Supply and activity arrive as numbers (1 SCARCE to 5 ABUNDANT; 0 RESTRICTED to 3 STRONG) and the
  tables map them back to words.
- An empty label is no label in Prometheus: a raw good has no `made_from`, an empty cell.
- Tested with `promtool test rules` against synthetic series in two systems (each query gives the
  expected rows, the other system left out) and `scripts/validate.py` without kubeconform and the
  HelmRelease rendering: no errors. Until the bot runs an image with PR #118 the dashboard is
  empty. Dashboards reload without a Grafana restart.

## 2026-10-02 — SpaceTraders survey section

The SpaceTraders dashboard gains a survey section under the mining panels, asked for to see whether
the bot surveys too much or too little (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 6.4, its
PR #122, which adds the metrics and journal lines). The panels below it moved down by its height.

- Stats over the last 24 hours: surveys taken; the share of ended surveys no extraction used (high:
  too many surveys); the share of extractions made with a survey (low while a surveyor works: too
  few); and the usable surveys now.
- Per hour: surveys taken and ended (expired, exhausted, not_verified; used or not); usable surveys
  per asteroid, used or not; extractions with and without a survey.
- "Survey journal": the bot's `Surveyed` and `SurveyEnded` lines from Loki, every survey with its
  deposits and expiry, and how it ended after how many extractions.
- Tested with `promtool test rules` (`prom/prometheus`) against synthetic series, every query taken
  verbatim from the JSON: each gives the expected value (1,440 taken, 25% ended unused, 75% of
  extractions surveyed, 7 usable). `scripts/validate.py`'s syntax check: no errors (no flux,
  kubeconform or helm on this PC; CI runs the rest). Until the bot runs an image with PR #122 the
  section is empty. Dashboards reload without a Grafana restart.

## 2026-10-02 — SpaceTraders settings table

The SpaceTraders dashboard gains a "Settings" table under the database size and the anomalies, asked
for to see which settings exist and which are on (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice
2.9, branch `ccr-212dac2b-p2ent0`, which adds the metric `spacetraders_setting_info`). The panels
below it moved down by its height.

- One row per setting: its value and what it does. The switches (values `true` or `false`) come
  first, on in green and off in plain text, then the other settings by name. The bot's `Runtime.*`
  status flags are left out; a value that may hold a secret shows `(hidden)`, an empty one `(empty)`.
- One instant query: `label_replace` gives each row a sort key (`1 <setting>` for a switch,
  `2 <setting>` for the rest), the table sorts on it and hides it. Grafana's sort transformation
  takes one field only.
- Until the bot runs an image with the metric, the table says "No data".
- Tested against a local Prometheus (`prom/prometheus` v2.53.0) scraping the metric as the bot writes
  it, with the seed's settings as test data, and Grafana 11.6.1 (what the chart's newest 8.x ships),
  in a browser: 34 rows, the 9 switches first, the empty webhook URL as `(empty)`, no `Runtime.*`.
  `scripts/validate.py` with flux, kubeconform and helm: no errors, no warnings.

## 2026-10-02 — SpaceTraders roles table

The SpaceTraders dashboard gains a "Roles" table under the fleet table, for the bot's new role board
(Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 6.9, branch `claude/ship-role-profitability-ghjzlb`,
which adds the metrics `spacetraders_ship_role_info` and `spacetraders_ship_role_credits_per_hour`).
The panels below it moved down by its height.

- One row per ship: its role (Survey, Mine, Siphon, Trade or None), why it has it (`only_role`,
  `survey_first`, `contract`, `most_profitable`, `no_work`, `no_role`), and what mining, siphoning and
  trading would earn it per hour by the board's estimate. An empty cell: the ship can't take that role,
  or its plan is off. Surveying has no estimate: it comes first.
- Four instant queries, merged on `ship` (Grafana's Merge transformation), as in the fleet table.
- The bot exports the roles only while the role board is on (`Automation.Plan.Roles.Enabled`, off by
  default), so until it is switched on, on an image with slice 6.9, the table says "No data".
- Tested with `promtool test rules` (`prom/prometheus` v2.55.1) against synthetic series, every query
  taken verbatim from the JSON: each gives the expected rows, another namespace's left out.
  `scripts/validate.py` with flux, kubeconform and helm: no errors, no warnings. Dashboards reload
  without a Grafana restart.

## 2026-10-03 — SpaceTraders log budget per ship, and the panels of slice 6.10a

After the bot's first day on the cluster (Gemberkoekje/projects `SpaceTraders/PLAN.md`: the health check's B53, and
slice 6.10a with decisions D46, D49 and D50), the log budget follows the fleet and the dashboards show what each ship can
do, what each kind of work earns, and what selling into a market does.

- **Log budget, alert `spacetraders-log-volume`:** the lines of the last 24 hours divided by the ships averaged over the
  same 24 hours (`count(count by (ship) (spacetraders_ship_info))`, at least 1), above 5,000 a ship. A working ship logs
  2,000 to 2,700 lines a day since B53; it was 50,000 lines a day whatever the fleet. Grafana reads alert rules only at
  startup, so the rule changes at its next restart; restart it once B53 has run a few hours (the rule read 4,619 a ship
  on the day of the change, on the old logging). The "Log lines per hour" panel draws the budget as a dashed line,
  ships × 5,000 / 24.
- **Markets, "Market tree: goods traded in $system":** where each good is cheapest to buy and where it sells best, with
  both prices and the difference per unit (green above 0), at the prices last seen.
- **Markets, row "What we sell into a market, and what it makes"** (variable `market`): the units we sell into it per
  hour (`spacetraders_goods_sold_units_total`), and the price, supply and trade volume of what it exports, side by side,
  to read off how many units of an input make one of output, and how fast (D50).
- **Fleet and Roles tables:** a "can do" column from `spacetraders_ship_capabilities_info` (Survey, Mine, Siphon,
  Trade): drones of both kinds report the registration role EXCAVATOR as their type. The Roles table still says "No
  data" while the role board is off.
- **"Profit per hour by activity"** (stacked bars, under "Total value"; the panels below moved down by its height): what
  trade, mining, siphoning, spare time and contracts earned per hour, booked when each trip ends (D46), from
  `spacetraders_trip_profit_credits_total` minus `spacetraders_trip_loss_credits_total`.
- **"Total value" no longer drops to 0 at a restart:** its ships and cargo queries turned "no data yet" into 0 for the
  first scrape of a new pod; now ships have no fallback and cargo falls back to 0 only while the bot reports its
  credits, so the panel's `spanNulls` bridges the restart.
- Until the bot runs an image with slice 6.10a, the new columns and panels say "No data".
- Tested: the alert's two queries against the live Loki and Prometheus; the seven new panel queries with `promtool test
  rules` (`prom/prometheus` v2.55.1) against synthetic series, an activity with only a profit or only a loss series
  included; the Total value queries replayed over the restart of 2026-10-03 08:17Z. `kubectl kustomize
  infrastructure/monitoring` renders; `scripts/validate.py` wasn't run locally (no kubeconform here), the PR's
  validate workflow runs it.

## 2026-10-03 — SpaceTraders purchase order and credit reserve (slice 6.10b)

For the bot's slice 6.10b (Gemberkoekje/projects `SpaceTraders/PLAN.md`, decisions D43, D47, D48 and D51, branch
`claude/spacetraders-purchase-order`): ships are bought in one order across the plans, and the credit reserve a ship
purchase keeps grows with what the trading ships can carry.

- **"Purchase order"** (a table under "Roles"; the panels below moved down by its height): what each plan that buys ships
  would buy now, from `spacetraders_purchase_need_credits{plan,tier,position,ship_type,shipyard}`, with its price and the
  credits needed, the price and the reserve. The lowest position is what the credits are saved up for.
- **"Credits"** draws the reserve a ship purchase leaves, `spacetraders_credit_reserve`, next to the credits.
- **"Roles"**: the description lists the new reason `coverage` (one drone per SCARCE or LIMITED mineral, D48).
- Until the bot runs an image with slice 6.10b, the new table and line say "No data".
- Tested: the panel queries with `promtool test rules` (`prom/prometheus` v2.55.1) against synthetic series, another
  namespace left out; `kubectl kustomize infrastructure/monitoring` renders. `scripts/validate.py` wasn't run locally;
  the PR's validate workflow runs it.

## 2026-10-03 — SpaceTraders API request rates, and legends as tables

Asked on 2026-10-03: a graph of the bot's request rates like a screenshot of another dashboard's (requests initiated,
executed and completed, and rate limited, per second, with each one's min, max, mean and last in a table), and table
legends "where appropriate" (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.10, branch `ccr-ff72b415-uqqj4q`, which
adds the metric `spacetraders_api_requests_initiated_total`).

- **"API request rates"** (full width, above "API requests per minute, by endpoint"; the panels below moved down):
  initiated (`spacetraders_api_requests_initiated_total`: each request once, as it starts, before the bot's budget and
  the pause after a 502), executed (each request that went out, retries of a 429 included: `spacetraders_api_requests_total`),
  completed (those that got an answer: `status!="error"`) and rate limited (`spacetraders_api_throttled_total`), per
  second over 5 minutes, in green, yellow, blue and orange as in the screenshot. A new pod has no 429 series until its
  first 429, so rate limited falls back to 0 while the bot makes requests (`or 0 * ...`). The graph joins gaps of up to
  10 minutes (a restart), not longer ones.
- **Table legends:** every graph with a list legend on both SpaceTraders dashboards. Mean, max and last for rates and
  counts per minute or hour; min, max and last for levels (credits, ships, usable surveys, the database size, prices,
  supply); total, mean and max for the hourly bars of "Units we sold into $market per hour". Graphs with many series
  sort by mean (levels by last), so the biggest come first. The graphs that had tables already ("Total value", "Profit
  per hour by activity", "Prices of $good") are unchanged.
- Grafana gives a legend under a graph at most 35% of the panel, so the graphs with more series grew from 8 to 10 rows
  (on the markets dashboard from 9 to 10): three or four table lines, the rest scrolls. On a phone, a table wider than
  the panel scrolls sideways too: long names, such as the endpoints, push the numbers off to the right.
- Until the bot runs an image with slice 2.10, "initiated" has no data; the other three lines work now.
- Tested: the graph's four queries with `promtool test rules` (`prom/prometheus` v2.55.1) against synthetic series: a
  run with retried 429s and a request that got no answer, a new pod without 429s (rate limited 0), an image without the
  new metric (no initiated line), the bot down (no data, not 0), another namespace left out. Both dashboards in Grafana
  11.6.1 against a local Prometheus holding a day of synthetic data, looked at in a browser at desktop and phone width.
  `scripts/validate.py` with flux, kubeconform and helm: no errors, no warnings. Dashboards reload without a Grafana
  restart.

## 2026-10-04 — SpaceTraders systems dashboard (slice 6.11)

Asked on 2026-10-04: "a systems grafana dashboard with a more wide view of which systems have been explored and what
kind of mining, trading and shipyard opportunities it gives" (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 6.11,
branch `ccr-c7061120-est7c1`, which adds the explore plan and the eleven `spacetraders_system_*` metrics).

- A third SpaceTraders dashboard, "SpaceTraders systems" (`dashboards/spacetraders-systems-dashboard.json`, uid
  `spacetraders-systems`), plus its `configMapGenerator` entry. The SpaceTraders and markets dashboards link to it, and
  it links to them.
- Variable: `system` (every system the bot knows, all by default). The tables keep to it; the counts at the top don't.
- Panels:
  - counts: systems known, explored (home counts once the explore plan runs), to explore, gates under construction, and
    what the jumps' antimatter cost over 24 hours (`spacetraders_credits_spent_total{category="AntimatterPurchase"}`);
    the command ship's location and activity next to them;
  - "Systems": per system its state (in words, coloured), its gate (built, under construction, no gate, not known),
    jumps from home, how long ago it was explored, markets, shipyards, asteroids, gas giants, uncharted waypoints and
    its best trade margin; by jumps from home;
  - "Mining and siphoning": per system and good, at how many waypoints it can be mined or siphoned, the best price a
    market there pays for it and which, and the lowest supply among the markets that buy it (in words);
  - "Trades": each system's five best trades within it, one per good: where to buy, where to sell, the margin per unit
    before fuel, and the units one trade moves;
  - "Shipyards": the ship types each shipyard sells, with price and supply as last seen (the existing shipyard metrics);
  - "Gates": which systems each gate connects to, and what is known of the system at the other end;
  - "Systems over time": explored, to explore and gates under construction, with a table legend (min, max, last);
  - "Exploring journal": jumps with what the antimatter cost, systems explored, the plan taking the command ship and
    bringing it home, its waits for credits, and refused jumps (Loki, parsed as the "Journal" panel is).
- Table columns may shrink to 60 px, so every column fits at desktop width; text columns keep room for a whole symbol
  (goods, waypoints, ship types). At 1280 px a few headers are cut short; on a phone the tables scroll sideways.
- A system the command ship has only explored has no per-good market series (the bot keeps those to the systems its
  ships work in), so the markets dashboard shows only its markets' refresh times; this dashboard's summary covers it.
- Until the bot runs an image with slice 6.11, the panels on the new metrics say "No data" (the explored, to explore,
  gates and antimatter counts read 0); the shipyards and the command ship show already. Until the explore plan is
  switched on, only home is there.
- Tested: the panel queries with `promtool test rules` (Prometheus 3.5.0) against synthetic series, 40 checks: five
  systems (home, explored, to explore, gate under construction, jump refused), one or two systems picked, another
  namespace left out, and an image without the metrics (the counts 0 or no data, the tables empty). The dashboard in
  Grafana 11.6.1 against a local Prometheus scraping synthetic metrics while exploring advanced, looked at in a browser
  at 1600 px, 1280 px and phone width; the journal panel had no Loki to read. `scripts/validate.py` with flux 2.5.1,
  kubeconform and helm: no errors, no warnings. Dashboards reload without a Grafana restart.

## 2026-10-04 — SpaceTraders shipyards: tank, hold, can do and equipment

Asked on 2026-10-04: "For spacetraders, can we add some more information to the shipyard ships? I'd like to know fuel
tank size, cargo size, and which special bits they have (e.g. mining laser)", in Grafana, and "Also which role they can
fulfill within my fleet" (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.11, branch `ccr-1e461fef-n6hydk`, which
adds the metrics `spacetraders_shipyard_ship_fuel_capacity_units`, `spacetraders_shipyard_ship_cargo_capacity_units`
and `spacetraders_shipyard_ship_info{can,equipment}`).

- **"Shipyards"** on the markets dashboard has four more columns: **can do** (what the ship could do in the fleet,
  judged as the fleet table's "can do" judges a ship, by its mounts, hold and tank: Survey, Mine, Siphon, Trade; `none`
  for a ship that can do none of them; `Probe` for a probe, which the probe plan buys and flies), **fuel** (what the
  tank holds), **cargo** (what the holds take together) and **equipment** (its mounts, then its modules, without the
  `MOUNT_` and `MODULE_` prefixes, the cargo holds and the crew quarters, such as `MINING_LASER_I, MINERAL_PROCESSOR_I`).
  Like price and supply, they show once a ship has been at the shipyard; a ship type listed without details keeps its
  row, with these columns empty.
- The table is full width now, under "Places", which is full width too; the panels below moved down by its 10 rows. The
  short columns have fixed widths, so equipment takes the rest: the command frigate's six items fit at 1920 pixels.
  On a narrower screen a long list is cut off; the eye icon that hovering over the cell shows opens all of it. On a
  phone the table scrolls sideways, as the other tables do.
- The same branch deploys the bot at projects main `851426a9` (slices 6.11, 2.11 and 6.6; the explore and construction
  plans stay off until switched on). The four columns fill once the new pod runs, for each shipyard a ship has been at.
- Tested: the panel's three new queries and the ship type query with `promtool test rules` (promtool v2.55.1) against
  synthetic series in two systems: each gives the expected rows, the other system left out, and a ship type listed
  without details only in the type query. The dashboard in Grafana 11.6.1 against a local Prometheus scraping the
  series as the bot writes them, looked at in a browser at desktop and phone width: one row per ship type, the
  type-only row empty, every column readable at desktop width. `scripts/validate.py`'s syntax check: no errors (no
  flux, kubeconform or helm here; CI runs the rest). Dashboards reload without a Grafana restart.

## 2026-10-04 — SpaceTraders jump gate progress (slice 6.6)

Asked on 2026-10-04: a "jump gate progress" on the Grafana dashboard, with the percentage and which materials are still
needed (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 6.6, decisions D64–D68, projects#155, which adds a
construction plan and role for the home system's jump gate, and the metrics `spacetraders_construction_units_required` and
`spacetraders_construction_units_fulfilled`, each `{site,trade_symbol}`).

- **Three panels under "Contracts"** (8 rows; the panels below moved down by that):
  - "Jump gate progress" (stat): all units supplied over all units the gate needs, by us or anyone, in percent, named
    by the gate's waypoint; green at 100%.
  - "Jump gate: materials still needed" (table): per material, what is left to supply, what the gate has and what it
    needs in all, the most needed first. A material the gate has all of drops off the table. No gate column: the bot
    considers only the home system's gate (D68), and the stat names it. "still needed" comes next to the material, so
    on a phone it shows without scrolling sideways; "supplied" and "required" scroll.
  - "Jump gate materials" (bar gauge): each material's share of what the gate needs.
  - Two pods exporting the same rows (a rollout) count once (`max by (site, trade_symbol)`).
- **Descriptions brought up to date:** the dashboard's mentions the jump gate. "Roles" lists the reasons `gathers_first`
  (D58, missing until now) and `construction` (D65). "Purchase order" lists the tiers as the bot numbers them now:
  4 SurveyorPerArea (D55, missing until now), 5 CargoShips, 6 Construction (the gate's next load, with the material in
  the ship column and its market in the shipyard column), 7 Probes, 8 Alternating. "Spent per hour" names the ledger
  category ConstructionBuy, and "Profit per hour by activity" the activity construction (always a loss: supplying
  pays nothing). On the markets dashboard, "Shipyards" lists Construct among what a ship for sale can do: a cargo ship
  or the command ship can build the gate (slice 2.11 judges it as the fleet table does).
- The cluster runs slice 6.6 since gembernodes#52 (projects main `851426a9`). The panels say "No data" until its
  construction plan (`Automation.Plan.Construction.Enabled`, off by default) has seen the home gate under construction.
  On 2026-10-04 the home gate, X1-DC53-I55, was already complete, so they stay empty until the server reset (13:00Z)
  gives a new home system, whose agent starts with the plan off.
- Tested: the five queries with `promtool test rules` (`prom/prometheus` v2.55.1) against synthetic series, every query
  taken verbatim from the JSON: a gate under construction exported by two pods (counted once), a complete gate (100%,
  nothing still needed), no gate (no data, not 0), another namespace left out. The panels in Grafana 11.6.1 against a
  local Prometheus scraping a gate under construction and then a complete one, looked at in a browser at desktop and
  phone width. `scripts/validate.py` with flux, kubeconform and helm: no errors, no warnings. Dashboards reload without
  a Grafana restart.

## 2026-10-04 — Tailscale subnet router: Grafana from outside the LAN

Asked on 2026-10-04, from away: reach Grafana remotely. Tailscale used to give access to the LAN and
stopped working. It was never in this repository (nothing in Git or its history), so it was set up by
hand, and with nobody on the LAN there was no way to look at it or restart it.

- **A Tailscale subnet router in the cluster** (`infrastructure/tailscale/`): one pod, tailnet device
  `gembercluster`, routing to `192.168.1.200/29` (the nodes, .201–.203) and `192.168.1.224/28`
  (MetalLB's pool, .230–.239). From a device on the tailnet Grafana is at
  `http://192.168.1.230/grafana`, the same URL (and `root_url`) as at home, so nothing in Grafana
  changes. Postgres (.232) and SSH to the nodes should work the same way (not tried).
- **Narrower routes than the LAN's /24 on purpose:** `192.168.1.0/24` is a common home network, and a
  phone or laptop on such a network elsewhere would send .230 to its own LAN. The more specific routes
  win there. Widen `TS_ROUTES` if more of the LAN is needed.
- **In the cluster, not on the nodes:** Flux can deploy and repair it from Git with nobody home, which
  is what was missing this time. The other side: it is down whenever the cluster is, where tailscaled
  on the nodes would not be.
- **Its own Flux Kustomization** (`clusters/home/tailscale-kustomization.yaml`), like
  `system-upgrade-plans`, depending only on `namespaces`: it doesn't wait for infrastructure to be
  Ready, and a mistake in it doesn't hold up the apps' deploys.
- **State in a Secret** (`subnet-router-state`, `TS_KUBE_SECRET`) plus `TS_AUTH_ONCE`: restarts and
  kured reschedules keep the same device, and the auth key is only used for the first login. The pod
  creates the Secret and Flux doesn't manage it; deleting it (or the namespace) means a new auth key
  and a new device.
- **Userspace networking:** no privileges (UID 1000, all capabilities dropped). Connections to the LAN
  leave from the pod IP, which grafana-internal's allowlist (`10.0.0.0/8`) accepts.
- Image pinned to `ghcr.io/tailscale/tailscale:v1.102.5`, the newest stable tag on 2026-10-04.

### Setup (before merging)

1. Tailscale admin console → Settings → Keys → **Generate auth key**: Reusable on (a failed first start
   can then simply retry), **Ephemeral off** (an ephemeral device is deleted when it's offline for a
   while, e.g. during a reschedule, and could not come back), Pre-approved on if device approval is
   enabled.
2. 1Password, vault Gembercluster: a new **Password** item named `tailscale-authkey` with the key as its
   password. The operator turns it into the Secret `tailscale-authkey`, key `password`.
3. Merge. Flux applies it within a couple of minutes and the pod logs in once the Secret exists.
4. Admin console → Machines → `gembercluster` → ⋯: **Edit route settings** and approve both routes, and
   **Disable key expiry**. Untagged devices otherwise need a new login after 180 days, which for this
   pod means a new auth key.
5. On the phone or laptop: Tailscale on, with subnet routes allowed (the default on iOS, Android, macOS
   and Windows; `--accept-routes` on Linux), then open `http://192.168.1.230/grafana`.

If something is wrong the alert emails say so after 15 minutes ("Container crash-looping or failing to
start"): `CreateContainerConfigError` means the Secret or its `password` key is missing (step 2),
`CrashLoopBackOff` usually a rejected auth key (step 1; replace the key in 1Password and wait for the
operator's 10-minute sync).

```bash
kubectl -n flux-system get kustomization tailscale
kubectl -n tailscale get pods,secrets
kubectl -n tailscale logs deploy/subnet-router
```

### The old setup

Look it up in the admin console (Machines): its name and "Last seen" tell where it ran and when it
stopped. An "Expired" badge means its key expired (180 days by default). Tailscale's docs say an admin
can then use "Temporarily extend key" (30 minutes) and, within that time, "Disable key expiry", without
touching the device, as long as it is still running. Remove the old device once `gembercluster` works.

## 2026-10-04 — SpaceTraders settings: what the next run starts with

Asked on 2026-10-04, after the server reset of 13:00Z left the new agent with most plans off: every plan on by default,
the settings you set carried over to the next agent, and "a separate set of endpoints to only affect future runs"
(Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.12 and decision D69, branch `ccr-856636cc-qj1te0`, which adds the
label `next_run` to `spacetraders_setting_info`).

- **"Settings"** on the SpaceTraders dashboard has a **next run** column after **value**: what the agent the next server
  reset registers starts with, the value chosen for it or else the default, with the same on and off as "value".
- "value" and "next run" are 180 pixels wide each ("value" was 300), so on a phone both fit beside each other once the
  table is scrolled sideways. A longer value (`Trade.ShipPurchases`) is cut off; the eye icon that hovering over the
  cell shows opens all of it.
- The description says how to set them: `PUT /settings/{key}` now and for the next runs, `PUT /settings/next-run/{key}`
  only for the next runs, `DELETE /settings/next-run/{key}` for the default again. It no longer says a setting can be
  changed on the bot's own dashboard: its Settings page only shows them.
- The same branch deploys the bot at projects main `52a73fd5` (slice 2.12, projects#156), in both deployments. Its first
  start adds `agent_settings."FollowsDefault"` and `next_run_settings` to the database, switches on the plans the current
  agent has had off since the reset of 13:00Z, and keeps any setting changed before it (D69). Each switch is a
  `SettingChanged` journal line, so a blue "Setting changes" annotation. Until the new pod runs, the column is empty.
- Tested: the panel in Grafana 11.6.1 against a local Prometheus (v2.55.1) scraping the series as the bot writes them,
  with the seed's settings as test data and three next-run values changed, looked at in a browser at desktop and phone
  width: the columns setting, value, next run and what it does, on and off in both. `scripts/validate.py` with flux
  2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings. Dashboards reload without a Grafana restart.

## 2026-10-04 — SpaceTraders dashboards per server reset

Asked on 2026-10-04, after the server reset: "Can we key all the Grafana data off the agent ID (or something else that's
different between resets) so data does not mix between different agents/different resets?", with the reset date as the
key, on all three dashboards (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.13 and decision D70, branch
`claude/spacetraders-run-label`, which puts the label `reset_date` on every `spacetraders_*` series and the property
`ResetDate` on every log line). The bot registers the same symbol after every reset, so only the reset date tells two
runs apart.

- **A "Reset" picker** is the first variable of the SpaceTraders, markets and systems dashboards: the `reset_date` values of
  `spacetraders_agent_credits` in the time range, newest first, so a dashboard opens on the run that runs now. It is
  multi-value without "All": tick several to compare runs.
- **Every Prometheus query** filters on it (`reset_date=~"$reset_date"` in each selector of a `spacetraders_*` metric),
  the markets and systems pickers too, so their lists hold only that run's systems, markets and goods. An `increase()`, an
  `offset 1h` or a table over the range no longer adds two runs up.
- **The Loki queries:** the journal, the survey journal, the exploring journal and the "Setting changes" markers keep the
  chosen run's lines (`| json …, ResetDate | ResetDate=~"$reset_date"`). "Errors" keeps them and the lines that carry no
  run: the web UI's, the init container's, and a start's first lines before the agent is known. "Log lines per hour"
  counts those too (`drop __error__`), as the log-volume alert does.
- **Left unfiltered:** the "Bot" stat (`up` is Prometheus's own series, without the label) and the "Server resets"
  markers, the line between two runs. The alert rules don't change: they look at what the bot reports now.
- **The links between the three dashboards pass the picker on** (`includeVars`), and the system with it.
- **Data from before the deploy has no reset date**, so the picker can't show it: the run of 2026-10-04 shows from the
  deploy of the bot's build with slice 2.13 on. Deploy that build with these dashboards. Until then the picker is empty.
- Tested against the cluster's Prometheus and Loki through port-forwards, read-only: every changed query, with the picker
  matching anything, against the query as it was. All 131 changed queries ran, the pickers' included: 119 answered
  identically, 11 differed only by the seconds between the two queries, and "Log lines per hour" answered 675 both ways
  once it kept the lines without a run. Not yet looked at in a browser: the picker has no values until the bot's build
  runs.

## 2026-10-04 — SpaceTraders ship names

Asked on 2026-10-04: "SHIPS are now named by the game in ascending order. Can we make custom names within the API which
should be type-number … Bonus points if there's a list of relevant names for each of the types, one of which is picked per
reset to call that type" (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.14 and decision D72, branch
`claude/dreamy-albattani-zo7njw`, which adds `spacetraders_ship_name_info{ship,name,type}` and the property `ShipName` on
every log line about a ship). The API can't rename a ship, so the name is the bot's own, shown beside the game's symbol:
one name per ship type each reset, from a list per type, numbered in the order the ships joined the fleet (MARINER-2 is the
second probe of the run of 2026-10-04).

- **Fleet** and **Roles** on the SpaceTraders dashboard have a **name** column after **ship**:
  `max by (ship, name) (spacetraders_ship_name_info{…})`, merged on `ship` as the other columns are; in Roles only for the
  ships on the board (`and on (ship)` the role series), as its "can do" column is.
- **The journals** (the journal and the survey journal on the SpaceTraders dashboard, the exploring journal on the systems
  dashboard) start a line about a ship with its name in brackets: `[PICKAXE-1] MiningStarted: ship SPECTER-3 mines …`
  (`| json …, ShipName, … | line_format "{{ if .ShipName }}[{{ .ShipName }}] {{ end }}{{ .message }}"`). A line about no
  ship reads as before.
- **The `ship` label and `ShipSymbol` stay the game's symbol,** so every other panel, the alert rules and the links between
  the dashboards work as they did.
- **Until the bot runs a build with slice 2.14,** the column is empty and no journal line has a name: deploy that build
  with these dashboards.
- Tested: `scripts/validate.py` with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings. The two
  PromQL queries with `promtool test rules` (v2.55.1) against made-up series: the picker leaves another run's names out,
  and Roles keeps only the ships on the board. The three LogQL queries with `logcli --stdin` (v3.5.5) against lines in the
  bot's JSON: `[PICKAXE-1] MiningStarted: …` for a line with `ShipName`, unchanged without one, another run's left out. Not
  looked at in a browser: the column has no data until the build runs.

## 2026-10-04 — SpaceTraders market tree: trade volumes

Asked on 2026-10-04, after asking why the bot doesn't trade SHIP_PARTS, which the market tree showed bought for 2,870 and
sold for 7,878, a difference of 5,008: "Oh right, not enough trade volume. Can you add the buyers trade volume to the
grafana market tree part?" The trading plan trades only a full hold, in one purchase and one sale (Gemberkoekje/projects
`SpaceTraders/PLAN.md` decision D56): a route counts only when both markets' trade volumes are at least the ship's free
hold. The market tree showed the prices without the volumes, so a large difference looked tradeable when it wasn't.

- **"Market tree: goods traded in $system"** on the markets dashboard has two more columns. **sell volume**, after
  "sell for", is the buyer's: the trade volume at the market that pays most for the good ("sell at"). **buy volume**,
  after "buy for", is the trade volume where the good is cheapest ("buy at"), as D56 needs both. Each is
  `spacetraders_market_trade_volume` at the market the column beside it names, chosen the way that column chooses it:
  `max by (good) (… and on (good, waypoint, reset_date) bottomk by (good) (1, …purchase_price… > 0))`, and `topk` of
  the sell price for sell volume. `reset_date` in the join keeps two ticked runs apart; two pods during a rollout count
  once.
- **The description** says what the volumes are, and that the pair shown is traded only when both volumes are at least
  the trader's free hold (D56); another pair, with a smaller difference, may be.
- **Fixed widths for the short columns**, as in "Shipyards": 120 pixels for "buy at" and "sell at", 100 for the prices,
  the volumes and the difference. At 1920 pixels every column fits, the longest "made from" lists included (before,
  "ELECTRONICS, MICROPROCESSORS" was cut off). At 1440 with Grafana's menu docked the table scrolls sideways, as it
  already did; on a phone it scrolls sideways, as the other tables do.
- Uses the metrics the bot exports now: no new build needed. Dashboards reload without a Grafana restart.
- Tested: the panel's six queries with `promtool test rules` (v2.55.1), taken verbatim from the JSON, against made-up
  series: SHIP_PARTS made at one market (15 at once) and bought at two (6 and 13 at once), FABRICS and FUEL, a second pod
  with a newer volume, an earlier run at the same waypoints, and another system and namespace, left out. With the join on
  `good, waypoint` alone, two ticked runs mixed their volumes and the test failed. The panel in Grafana 11.6.1 against a
  local Prometheus scraping the series from two pods, looked at in a browser at 1920, 1440 and 390 pixels wide: one row
  per good, each volume the one of the market beside it, a tie for the cheapest market included. `scripts/validate.py`
  with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings.

## 2026-10-04 — SpaceTraders snapshots in Grafana (slice 2.15)

Asked on 2026-10-04: "Can you expand the JSON export to include shipyard information, and can you make these jsons
available through Grafana? If we do that, is everything from the webUI covered in Grafana?", then "I'd like the snapshots
to be made whenever a new discovery is made. So a shipyard with a new ship type or a market with a new good type, in
addition to the times they are currently made." (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.15 and decision D73,
branch `ccr-a2ff9235-gidedj`, which puts every cached market and shipyard in the bot's snapshots and takes one at every
discovery.) Grafana read only Prometheus and Loki, which can't hold a JSON document; the choice was the Infinity data
source, reading the bot's internal API with its API key.

- **The Infinity data source** (`yesoreyeram-infinity-datasource` 3.11.1) comes from Grafana's own background preinstall
  (`grafana.ini` `[plugins] preinstall`), next to the plugins Grafana preinstalls itself. Pinned: 4.x needs Grafana
  11.6.11 or later, and the chart's newest 8.x ships 11.6.1. Not the chart's `plugins` value: that installs from the start
  script, which runs with `bash -e`, so a start that can't reach grafana.com stops Grafana (tried: the container exits
  with 1). The preinstall logs it and Grafana runs on, the snapshots dashboard failing until a start that reaches
  grafana.com. Once on Grafana's volume the pinned version isn't fetched again.
- **The SpaceTraders API data source** (uid `spacetraders-api`) calls
  `http://spacetraders-api-service.spacetraders.svc.cluster.local/spacetraders/api` with the header `X-Api-Key`, from
  `$__env{SPACETRADERS_INTERNAL_API_KEY}`. Infinity reads its base URL from `jsonData.url` and calls only the hosts in
  `allowedHosts`; Grafana's data source proxy reads `url`, which the dashboard's downloads go through.
- **The key:** `infrastructure/monitoring/spacetraders-secrets.yaml` copies the bot's 1Password item into the monitoring
  namespace (the operator copies every field), and the Grafana pod gets only `SPACETRADERS_INTERNAL_API_KEY`
  (`envValueFrom`, optional: without it Grafana starts, and only the snapshots dashboard fails, with the bot's 401). No
  step by hand: the item exists.
- **What the key allows:** what it allows the bot's own dashboard, which hands it to every browser that opens it
  (SpaceTraders B22). Through Grafana a logged-in user can also call the API's PUT and POST endpoints, switching
  automation off or changing a setting: the data source proxy forwards every method, and an Infinity query may POST. A key
  that only reads, for Grafana, would close that; it isn't built.
- **The "SpaceTraders snapshots" dashboard** (uid `spacetraders-snapshots`, linked from and to the three other SpaceTraders
  dashboards):
  - **Snapshots of the run under way:** when, why (`Startup`, `Discovery`; the run's first says so) and, for a discovery,
    what was new and where; **JSON** downloads the snapshot as the bot saved it (a new tab, so Grafana's router leaves
    the link alone; the browser needs no key), **show below** picks it. The bot keeps only its own agent's snapshots, the
    run's first and the 10 newest.
  - **The picked snapshot** (the "Snapshot" picker, newest first): a summary row, what it found, its ships, its shipyards
    (one row per ship type: price, supply, activity, tank, hold, mounts and modules where the listing is cached, and
    when it was seen) and its markets (one row per good; without prices, what the market imports, exports and
    exchanges). Each table is a JSONata expression over the snapshot's JSON (Infinity's backend parser), guarded so a
    snapshot without discoveries, shipyards or markets shows an empty table rather than an error.
  - **Discoveries:** the journal's `Discovered` lines for the picked resets (the "Reset" picker, as on the other three),
    which Loki keeps 31 days, after the snapshots themselves are pruned.
- **When this lands** Grafana restarts (its values change) and installs the plugin. Deploy the bot's build with slice 2.15
  with it: an older build lists its snapshots without why, and they hold only the market and shipyard where a ship was.
- Tested in Grafana 11.6.1 with Infinity 3.11.1 and the cluster's settings (served at `/grafana/`), against a stand-in for
  the bot's API that serves two snapshots the bot's own code wrote and checks the key, a local Prometheus for the Reset
  picker and a local Loki fed `Discovered` lines in the bot's JSON:
  - the data source sent the key from the environment, and every panel's query answered for a startup snapshot and a
    discovery snapshot, a market without prices and a ship in transit included;
  - in a browser at 1600 and 390 pixels wide: the pickers filled, no panel showed an error, "show below" picked the
    snapshot, and the JSON link, opened with only Grafana's login, downloaded `discovery-snapshot-2-…json`, the bot's
    file byte for byte;
  - the proxy forwarded POST, PUT and DELETE with the key, as described above;
  - with grafana.com unreachable: the preinstall logged a failure and Grafana served; the chart's `plugins` value
    stopped it; with the plugin already on the volume, it started either way.
  - `helm template` of chart 8.15.0 with these values: `[plugins] preinstall`, the data source with
    `$__env{SPACETRADERS_INTERNAL_API_KEY}` verbatim, and the optional key in the pod's environment.
    `scripts/validate.py` with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings.

## 2026-10-04 — SpaceTraders market tree: D74 in its description

Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 6.13 (decision D74, branch `ccr-f3fba810-ie3vm6`) lets a trader carry
less than a full hold where the seller's supply is ABUNDANT: the smaller of the two trade volumes, still in one purchase
and one sale. The market tree's description, merged an hour earlier (gembernodes#61), said a pair is traded only when both
volumes reach the trader's free hold (D56). It now says the ABUNDANT case too.

- Only the description changes; the queries and columns are as gembernodes#61 left them.
- It describes the bot once the bot runs a build with slice 6.13: deploy that build with it.
- Tested: `scripts/validate.py` with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings.

## 2026-10-04 — SpaceTraders profit by ship (slice 2.16)

Asked on 2026-10-04: "For spacetraders, I'd like to see each ships total profit. So -purchase price-market buys+market
sales-fuel (plus or minus any other relevant ship-specific credit changes)" (Gemberkoekje/projects `SpaceTraders/PLAN.md`
slice 2.16, branch `ccr-fea929ec-ptl3vh`, which adds `spacetraders_ship_ledger_credits{ship,category}`: each ship's ledger
since it joined the fleet, summed by ledger category, earnings positive and costs negative).

- **"Profit by ship"** on the SpaceTraders dashboard, under Roles; the panels below moved down by its height (10). One row
  per ship, most profitable first: ship, name, **profit**, then what it is made of: **purchase** (`ShipPurchase`,
  `MountPurchase`, `ModulePurchase`), **market buys** (`TradeBuy`), **market sales** (`TradeSell`, and `MiningSell`, which
  the bot doesn't book), **fuel** (`FuelPurchase`) and **other** (every other category: `AntimatterPurchase`,
  `ConstructionBuy`, `Repair`, …), so the columns after profit add up to it. Costs are negative; profit is green from 0 and
  red below; the bottom row sums each column, the fleet's totals.
- Each column is `sum by (ship) (max by (ship, category) (spacetraders_ship_ledger_credits{…, category=~"…"}))`: the
  `max by (ship, category)` first, so two pods during a rollout count once. Then
  `or 0 * max by (ship) (spacetraders_ship_value_credits{…}) and on () count(spacetraders_ship_ledger_credits{…})`: a ship
  with nothing in a column shows 0 rather than an empty cell, but only once the bot exports the ledger, so before that the
  numbers stay empty rather than read 0.
- Fixed widths for ship (105 px), name (130, for HUMMINGBIRD-12) and profit (100): on a phone those three fit and the
  breakdown scrolls sideways, as the other tables do.
- The contract's payments are booked to the agent, not a ship, so no row has them; the description says so and points to
  "Profit per hour by activity".
- **Until the bot runs a build with slice 2.16,** the table lists the ships and their names without numbers: deploy that
  build with this dashboard.
- Tested: the seven queries with `promtool test rules` (v2.55.1), taken verbatim from the JSON, against made-up series:
  a starting ship that trades and jumps, a probe without ledger rows (0 in every column), a mining drone on two pods
  (counted once), a builder with a mount and the jump gate's materials, the run before with the same symbols and another
  namespace (left out), and a bot without the metric (no numbers): 13 checks, each row's columns adding up to its profit.
  The table in Grafana 11.6.1 against a local Prometheus scraping the series as the bot writes them, looked at in a browser
  at 1600 and 390 pixels wide: sorted by profit, zeros for the probe, the totals row, and in place between Roles and
  Purchase order without overlap. (Headless Chromium in a container with a POSIX locale needs an explicit `en-US`:
  Grafana's frontend fails on `en-US@posix`.) `scripts/validate.py` with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1:
  no errors, no warnings.

## 2026-10-04 — SpaceTraders: the trading plan's order under the market tree (slice 2.17)

Asked on 2026-10-04: "Can you, in a new pr, add the exact logic to the market tree view that is used to determine which
trade is done first?" (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.17 and decision D75, projects#168, which adds
`GET /status/trading-routes`.) The trading plan ranks each free trader's routes with the trader's hold, fuel and position and
the credits, which Grafana can't recompute from Prometheus; the bot publishes the order it works out instead.

- **"Trade routes, in the order traders take them"**, a table under "Market tree: goods traded in $system" on the markets
  dashboard (12 rows; the panels below moved down by that). It reads `/status/trading-routes` through the SpaceTraders API
  data source (slice 2.15): the trading plan's state as its last pass stored it. First the routes traders hold, with the
  trader; then the lucrative routes no trader holds, numbered best first (a route that feeds a pricier good first, D15, then
  the most profit after fuel). Columns: order, trader (`waiting` for one no trader holds), good, buy at, sell at, units
  (D56, D74), profit after fuel, per unit, feeds, could take it (the free traders it was lucrative for) and as of (when the
  plan last changed the list). The description states the plan's rules.
- **Infinity's backend parser** returns the columns in alphabetical order, so an "organize" transformation puts them back,
  as on the snapshots dashboard; the JSONata expression wraps its rows in `[...]`, so a single route stays a list.
- **Empty:** "No routes: no trader holds one, and none waited at the trading plan's last pass". Not system-filtered: the
  plan's state covers every system its traders work in.
- **The market tree's description** points to the table.
- It shows data once the bot runs a build with slice 2.17; until then the endpoint answers 404 and the panel an error.
  Deploy that build with it.
- Tested in Grafana 11.6.1 with Infinity 3.11.1 and the data source as the cluster has it (the key from the environment),
  against a stand-in for the bot's API that checks the key and serves the JSON the bot's own endpoint wrote in its test:
  - the panel's query through Grafana's query API: seven routes in the bot's order, one route, and none (no rows, no error);
  - in a browser at 1920, 1440 and 390 pixels wide: every column fits at 1920; at 1440 with Grafana's menu docked and on a
    phone the table scrolls sideways, as the market tree does, with the good's name whole; the empty table shows its
    message; the table sits under the market tree, the rows below moved down without overlap.
  - `scripts/validate.py` with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings.

## 2026-10-05 — SpaceTraders: why the other goods aren't traded (slice 2.18)

Asked on 2026-10-05: "Can the new list also add why the other goods are not considered for trading?" (Gemberkoekje/projects
`SpaceTraders/PLAN.md` slice 2.18 and decision D76, projects#170, which adds `notTraded` to `GET /status/trading-routes`.)
For each good with a price gap (a market in the system sells it for less than another pays for it) that no listed route
carries, the trading plan says why: the first of its route checks that the good's route failed, for the free trader that
got furthest with it.

- **"Goods not traded, and why"**, a table under "Trade routes, in the order traders take them" on the markets dashboard
  (12 rows; the panels below, and the one inside the collapsed "Market tree: all goods" row, moved down by that). It reads
  `notTraded` from the same endpoint through the SpaceTraders API data source. Columns: good, check (the check that failed,
  in words: buy market out of reach, sell market out of reach, no full hold, too few credits, too little profit, below the
  listed routes), buy at, sell at, why not (the bot's sentence: the trader first, then the check's figures) and as of
  (when the plan's last pass with a free trader found it). The description states the checks in their order.
- **A table of its own**, not rows in the routes table: Grafana 11.6 sizes a table's rows by one wrapped column only, so in
  one table the reasons were either cut off, or long candidate lists and goods spilled over their rows; and a good that
  isn't traded has no units, profit, feeds or candidates, which left five empty cells a row. Here "why not" wraps, and its
  rows grow to fit it.
- **Empty:** "None: every good with a price gap is in the routes above, or no pass of the trading plan with a free trader
  has found one yet". A build without slice 2.18 sends no `notTraded`, and the table shows the same.
- **The routes table** is as slice 2.17 left it; its description and the market tree's point to the new table.
- Tested in Grafana 11.6.1 with Infinity 3.11.1 and the data source as the cluster has it, against a stand-in for the bot's
  API that checks the key and serves the JSON the bot's own endpoint wrote in its test:
  - the panel's query through Grafana's query API: six goods with every check, goods without routes, the routes without
    `notTraded` (an older build) and nothing at all (no rows, no error);
  - in a browser at 1920, 1440 and 390 pixels wide: every column fits at 1920 and 1440, and the reasons wrap; on a phone the
    table scrolls sideways, as the routes table does; the empty table shows its message; the table sits under the routes
    table, the rows below moved down without overlap.
  - `scripts/validate.py` with flux 2.5.1, kubeconform v0.8.0 and helm v3.17.1: no errors, no warnings.

## 2026-10-05 — SpaceTraders: goods that wait for a free trader (B66)

Asked on 2026-10-05: "Assault Rifles should make a tidy profit at 2191, yet it doesn't even show up in the Goods not
traded and why tab." (Gemberkoekje/projects#179, `SpaceTraders/PLAN.md` B66.) A good whose route waited for a free trader
had no row, being listed among the waiting routes, and once every trader was on a trip the waiting routes went: the good
was in neither table. The bot now gives such a good a row with the reason `waiting`.

- **"Goods not traded, and why"** maps `waiting` to "waits for a free trader", and `no_room`, the reason that replaced
  `not_full_hold` in the bot's slice 6.16 (D79), to "no room": both showed as the raw code. `not_full_hold` stays mapped,
  for an older build.
- **The table's description** lists the checks as the bot runs them since D79 (room in the hold and a price and trade
  volume at both markets, a unit the credits pay for, the first unit and the trip earning the minimum) and says what
  "waits for a free trader" means. The table shows every good no trader's route carries.

### How it was tested

- The dashboard JSON parses, and only the panel's mappings and description changed. `scripts/validate.py` runs in CI
  (flux, kubeconform and helm aren't installed on this PC).

## 2026-10-05 — SpaceTraders: the jump gate's miners in the purchase order (slice 6.25)

For the bot's slice 6.25 (Gemberkoekje/projects `SpaceTraders/PLAN.md`, decision D92, branch `ccr-ca2bf7e9-hweozt`):
while the jump gate needs materials, the mining plan buys a mining drone per ore every half hour for the smelters that
make the gate's metals (IRON_ORE into IRON for FAB_MATS, COPPER_ORE into COPPER for ADVANCED_CIRCUITRY), until each has
its ore at HIGH. Asked on 2026-10-05: "Same tier as gate loads, capped. If the gate can be built, it should be built,
otherwise extra miners can be built."

- **"Purchase order"**: the description says that a Mining plan `SHIP_MINING_DRONE` at position 6 (Construction) is one
  of the gate's miners, which waits while a load of the gate can be bought and is bought while the load waits for its
  markets. No query changed: the bot reports it with the existing metric, at the Construction tier.

### How it was tested

- The dashboard JSON parses, and only the panel's description changed. `scripts/validate.py` runs in CI.

## 2026-10-06 — SpaceTraders: trade routes per hour (slice 6.27)

For the bot's slice 6.27 (Gemberkoekje/projects `SpaceTraders/PLAN.md`, decision D95, branch
`claude/spacetraders-profit-per-hour`): the trading plan ranks its routes by what they earn an hour over the whole trip
from where the trader is, within its order (the jump gate's materials first, exchanges last, end products at half). Asked
on 2026-10-06: "I want a "profit per time unit" so the system can choose between a short route that pays less or a long
route that pays more."

- **"Trade routes, in the order traders take them"** (markets dashboard): two columns after "per unit", **minutes** (the
  trip's time, one decimal) and **per hour** (the rate the plan ranks by), from the bot's `expectedMinutes` and
  `creditsPerHour`. A route without a time (cargo a trader already held, or a bot without slice 6.27) shows "—" in both.
  The description now states the plan's order as it is: as many units as each earn the minimum, in batches (D79); the
  gate's materials first (D89, D90), exchanges last (D91), otherwise the most per hour (D95), an end product's rate at
  half (D85); one buyer at a time (D80). It still said full holds (D56, D74) and the most profit after fuel.

### How it was tested

- The dashboard JSON parses. The table's JSONata expression, evaluated with jsonata 2 (JavaScript) against the
  endpoint's answer with the new fields, without them (the bot as it runs now) and with no routes: the two columns
  filled, "—" (null), and no rows. `scripts/validate.py` runs in CI.
- Deploy it with the bot's build of slice 6.27; before that both columns show "—".

## 2026-10-06 — SpaceTraders API: CPU limit 2 cores, memory limit 2 GiB

Asked on 2026-10-06, after a watch on the bot found its CPU limit throttling it in 47% of the scheduling periods and its memory
at 87% of the limit: "Can we up the allowed CPU usage, and can you investigate whether we have memory space to up that as
well without running into issues?" Only the API container's limits change (`apps/spacetraders/deployment-api.yaml`): CPU
500m → 2, memory 1Gi → 2Gi. Its requests (100m, 512Mi) and the web UI stay as they were. To understand this, start by reading
that file's `resources:` block, then the numbers below.

### What the numbers said (Prometheus, 2026-10-05 and 06)

- **CPU.** The container uses 0.22–0.26 cores on average (p99 0.33, worst 0.39, over two-minute windows) yet was throttled in 47%
  of its 100 ms scheduling periods over 24 hours (p99 71%). Throttled time is 7% of wall time at the median, 31% at the 99th
  percentile and 50% at worst. So the bot works in short bursts over the 50 ms a 500m limit gives each period, not in a
  sustained load. The nodes have 4 cores each and were at most 37% busy over seven days (gembernode-01, where the bot runs: 29%).
- **Memory.** The working set is 680–890 MiB across the last day's pods and flat: 780 MiB four minutes after a start, and an
  11.5-hour pod grew 21 MiB in ten hours. The highest peak was 892 MiB (87% of 1 GiB). The managed heap is only about 52 MiB and
  the GC paused 1.4% of the time: the rest is runtime and native memory, reached at startup. So the limit is room, not a
  target. One thing a bigger limit can change: .NET's GC measures its memory load against the limit and turns aggressive
  above 90% (`GCHighMemPercent`), which the 87% peak came close to, so with more room it may keep a little more heap. The heap is
  small, so the effect should be small too; the check after the deploy shows it.
- **Free memory on the nodes** (7.67 GiB each). Over 15 days the least available was 4.0 GiB on gembernode-01 and 3.7 and 3.6 GiB
  on the other two. In that time: no node-level OOM kill, at most 5 seconds of memory stall in a week, no evicted pod and no
  container OOMKilled. The memory limits on gembernode-01 total 2.2 GiB, and 3.2 GiB with this change (41% of the node). The other
  nodes' limits already add up to 101% and 125% of their memory, and what they actually use is 54–62%. The namespace has no
  quota or limit range, and the cluster has no admission policy engine.

### Decisions

- **2 cores, not 1.** It ends the throttling and costs nothing while the bot is quiet. .NET takes its processor count from the CPU
  limit rounded up: 500m gave 1 (`system_runtime_dotnet_process_cpu_count`), 2 gives 2, so the thread pool starts with two
  threads instead of one. Nothing in the bot reads the processor count, and Wolverine's default parallelism is the greater of the
  processor count and 5 (the documentation of `Endpoint.MaxDegreeOfParallelism` in WolverineFx 6.44.0), so messages are
  handled five at a time either way. `1000m` would double the quota without changing the count: the alternative if 2 is too much.
- **2 GiB.** 2.2 times the highest peak. If the bot ever used all of it, the nodes would still have at least 2.5 GiB free, counted from
  their worst moment of the last 15 days.

### Gotchas

- The pod restarts when this merges: `strategy: Recreate`, so about 90 seconds without the bot, like any deploy. The image doesn't
  change, so there is no CI run to wait for.
- The memory request (512Mi) is below what the bot uses (about 800 MiB): the scheduler books less than the bot takes, and under
  memory pressure on its node the bot would be among the first to be evicted. Not changed, because the nodes have gigabytes spare;
  raise it to about 1Gi if the cluster ever fills up. The CPU request (100m) is likewise below the mean use, which matters only
  when a node's CPU is contended.
- Prometheus scrapes once a minute, so the shortest rate window that works is 2m: bursts shorter than that show only in the
  throttling counters.

### How it was measured, and what to check after the deploy

- Container, `container="spacetraders-api"`: `rate(container_cpu_usage_seconds_total[2m])`, throttled share
  `rate(container_cpu_cfs_throttled_periods_total[2m]) / rate(container_cpu_cfs_periods_total[2m])`, throttled time
  `rate(container_cpu_cfs_throttled_seconds_total[2m])`, `container_memory_working_set_bytes`; the .NET side
  `system_runtime_gc_heap_size`, `system_runtime_dotnet_process_cpu_count`. Nodes: `node_memory_MemAvailable_bytes` (min over 15d),
  `node_vmstat_oom_kill`, `node_pressure_memory_waiting_seconds_total`, and `kubectl describe node` (allocated resources).
- After the deploy expect the throttled share to fall well under the 47% above and the working set to stay near 0.8 GiB. If memory
  climbs instead, the 1 GiB limit was hiding a leak.
- The manifest parses and `kubectl kustomize apps/spacetraders` renders with the new limits; `scripts/validate.py` runs in CI.

## 2026-10-09 — SpaceTraders: two runs on one chart (slice 2.19), and 31 days in Prometheus

Asked on 2026-10-09 (Gemberkoekje/projects `SpaceTraders/PLAN.md` slice 2.19, decision D123): "If possible, I'd like the
option to overlay 2 (weekly) runs, so I can compare the value curve and see if it becomes better", with "Picker + 31 days
in Prometheus". Every series already carries its run's reset date (slice 2.13, D70), but each run shows on its own dates.

- **"Compare with"**, the SpaceTraders dashboard's second picker: the runs Prometheus holds, the newest first, but the one
  under Reset (`query_result` over `spacetraders_agent_credits`, 31 days either side of the time range's end, so the list
  doesn't depend on the time range). It opens on the run before the one under Reset.
- **"Total value, two runs"** and **"Value gained per hour, two runs"**, under Total value: the run under Reset as a solid
  line, the compared run dashed and shifted so both runs start at the same moment. A run starts with its
  first sample. The queries are Total value's top line and Value gained per hour's, with an `offset` on every selector of
  the compared run.
- **Two hidden variables**, `shift` and `shift_hour`: the seconds between the two runs' first samples (to 5 minutes:
  `min_over_time(timestamp(...)[62d:5m] offset -31d)`), and that plus an hour. Negative when the compared run is the newer
  one, which Prometheus allows since 2.33. With no run to compare with they are 1 and 3601: PromQL refuses `offset 0s`, and
  the compared run's selectors (`reset_date="$compare_with", reset_date!=""`) then match nothing, the unlabelled data from
  before slice 2.13 included.
- **Prometheus keeps 31 days** (`server.retention: "31d"`; the chart's default was 15 days), like Loki, so runs up to about
  four weeks back can be compared. The TSDB grows to about twice its size on the QNAP NFS share; the claim asks for 2Gi,
  which the NFS driver most likely doesn't enforce. The older data stays until it is 31 days old: right after the deploy only
  the last 15 days are there.
- The Reset picker's description says how to lay two runs over each other.

### How it was tested

- `promtool test rules` (Prometheus 2.55.1, what chart 25.30.2 runs) against two synthetic runs and unlabelled older
  data, the dashboard's own queries with the variables put in as Grafana does: 18 checks, including the newer run under
  Compare with (a negative shift), a time range before the newer run began, no run to compare with, and a compared run that
  had ended.
- Grafana 11.6.1 against a local Prometheus holding a week-long run that ended two days ago and one that began 30 hours ago
  (backfilled with `promtool tsdb create-blocks-from openmetrics`), looked at in a browser at desktop and phone width: the
  pickers chose 2026-10-04 and 2026-09-27, the shift came out at 670,500 s against the 670,620 s between the first samples,
  both panels drew the two runs from the same start, and the reverse (the older run under Reset, over its own dates) drew
  the newer run over it. The dashboard JSON parses; `scripts/validate.py` runs in CI.

## 2026-10-09 — SpaceTraders: descriptions for slices 6.37–6.40

For the bot's slices 6.37–6.40 (Gemberkoekje/projects `SpaceTraders/PLAN.md`, decisions D119–D122, branch
`claude/laughing-babbage-f8yqdj`), the descriptions say what changes on the dashboards; no query changes.

- **Purchase order** (SpaceTraders): position 12, `MiningAbroad`, a miner for a system abroad, last of all (D122); an ore
  hound wherever a drone is bought, where the shipyard sells one (D120), the gate's miners included; an interceptor in a
  probe's place (D119); no ship bought where its shipyard has it SCARCE, and no row for a plan whose ship is SCARCE
  everywhere (D121).
- **Probes abroad** (systems): the interceptors count with the probes (the bot's `FleetRoles.IsProbe` counts them), and
  neither is bought at SCARCE.
- **Shipyards** (markets): an interceptor's "can do" is Probe, as a probe's.
- The dashboard JSON parses. Deploy with the bot's build of those slices; until then the text runs ahead of the bot.

## 2026-11-02 — Plotboek Generator demo on plotboek.gemberkoekje.nl; vortexplotboek down to its redirect

Asked on 2026-11-02 (Gemberkoekje/plotboek-generator, phase 5 of the generic split): a public demo of the
now-open-source Plotboek Generator, at plotboek.gemberkoekje.nl with gemberkoekje.nl/plotboek redirecting there.
Visitors read only, the owner grants write access to whoever asks, and a filled example comes back every night.
The vortexplotboek leftovers go, except the redirect.

To understand this, start by reading [apps/plotboek-generator/README.md](apps/plotboek-generator/README.md), then
[apps/plotboek-generator/deployment.yaml](apps/plotboek-generator/deployment.yaml) and
[ingress/plotboek-generator-ingress.yaml](ingress/plotboek-generator-ingress.yaml).

- **The app** (`apps/plotboek-generator`, namespace `plotboek-generator`): image
  `ghcr.io/gemberkoekje/plotboek-generator:1.1.0`, the first release with demo mode. Google sign-in;
  `Authentication__DefaultRole=Reader` makes everyone who signs in a Reader (sees everything, changes nothing);
  `Demo__Enabled=true` gives the banner, the example plotboek on the first start, and `POST /api/demo/reset`.
  `Localization__DefaultCulture=en` with `SupportedCultures=en,nl`: English by default, Dutch for a Dutch
  browser or through the switcher; the example data and the Word export are English.
  It runs as UID 1654 (the .NET image's `app` user) since the image itself runs as root.
- **The nightly reset** (`reset-cronjob.yaml`, 04:00 Europe/Amsterdam): curl with `Demo__ResetApiKey`. It wipes every
  event and plot document, removes visitors' accounts and writes the example again. Admins (`Authentication__Admins`)
  and everyone with an override role keep their account, so write access granted on the Admin page lasts.
- **No volume for the data-protection keys**: a redeploy signs everyone out, which a demo can live with, and a volume
  on the NFS share would need write access for UID 1654. The nightly reset doesn't restart the pod.
- **Ingress**: `plotboek.gemberkoekje.nl` with the 32k proxy buffers every OIDC app here needs, and a second Ingress
  that redirects `gemberkoekje.nl/plotboek` (nginx answers it; the target has no trailing slash, as with vortexplotboek).
- **vortexplotboek**: the deployment (replicas 0), the suspended sync cronjob, its seven OnePasswordItems and its
  data-protection PVC are gone; Flux prunes them. Left: the namespace, `vortexplotboek-service` and
  `ingress/vortexplotboek-ingress.yaml`, which still redirects the old URLs to plotboek.the-vortex.nl.
- **Error alerting**: the error-log alert and dashboard watched the `vortexplotboek` namespace, which logs nothing any
  more; they watch `plotboek-generator` instead.

### Left for the owner

- Before merging: release 1.1.0 (CI's image check fails until it exists), then steps 1–4 of the README: the database,
  the Google client, the 1Password item and the DNS name.
- After merging: dump and drop the old `vortexplotboek` database on the shared PostgreSQL once nothing needs it.
- The 1Password items `postgress-vortexplotboek-secret`, `oauth-google-vortexplotboek-secret`,
  `oauth-microsoft-vortexplotboek-secret`, `oauth-google-refreshtoken`, `sync-api-key` and `gemini-secret` are no
  longer used by the cluster. Check whether the Portainer stack on plotboek.the-vortex.nl still reads them before
  deleting them. Keep `bearer-secret` and `discord-secret`: ebi-cs-api and armabotcs use them too.

### How it was tested

- The product side: 1390 specs in the plotboek-generator repository, plus the demo host against a local PostgreSQL 18.
  On first start it wrote 1 plotboek, 7 paginas, 1 plotlijn, 5 dummy spelleiders and 5 domains (8 streams, 107 events).
  The reset answered 401 to a missing or wrong key and `{"removedAccounts":1}` to the right one: the visitor went, the
  editor and the admin stayed, and the same example came back. A second reset removed nothing.
- Every changed kustomization renders with `kubectl kustomize` (apps, ingress, namespaces, infrastructure/pvcs). `scripts/validate.py` was not run locally (no kubeconform here); CI runs it on the pull request.

## 2026-11-05 — DungeonTable: CPU limit 2 cores

Asked on 2026-11-05, after the player view lagged seconds behind the DM screen at the table: "increase the CPU limit as I
should have CPU to spare." Only the container's CPU limit changes (`apps/dungeontable/deployment.yaml`): 500m → 2. Its
requests (250m, 512Mi) and its memory limit (1Gi) stay as they were. To understand this, start by reading that file's
`resources:` block, then the numbers below.

### What the numbers said (a local run, not Prometheus)

- Measured on a copy of DungeonTable 1.7.0 running the campaign's largest level (138×177 squares, half of it revealed), in a
  cgroup with the same quota as the pod (50 ms per 100 ms period), with a DM screen and a player view open.
- One move of the projector's frame cost the server 60–560 ms of CPU (median 170 ms), and dragging the party token 30
  squares cost 1.4–2.2 s. Each change re-renders the DM screen as well as the projector, and the DM screen's renders
  dominate. Bursts like these run past the 50 ms a period allows: the cgroup was throttled in 25–40% of its periods
  during the runs.
- The same 500m limit throttled the SpaceTraders bot in 47% of its periods (2026-10-06, above); the nodes have 4 cores
  each and were at most 37% busy over seven days then.
- Throttling alone did not reproduce the seconds of lag at the table: the rest is the DM screen's traffic over a phone
  hotspot and the projector laptop redrawing the map, which DungeonTable addresses itself. The limit is the part this
  repository owns.

### Decisions

- **2 cores, as for SpaceTraders.** It ends the throttling and costs nothing while nobody is at the table. .NET takes its
  processor count from the limit rounded up, so the thread pool starts with two threads instead of one. Nothing in
  DungeonTable reads the processor count.
- **The request stays at 250m.** The app is idle except during a session, so the scheduler need not book more.

### Gotchas

- The pod restarts when this merges (rolling update), and every open DM screen and player view reconnects to the new pod.
  The table's state is in PostgreSQL and comes back, but don't merge it during a session.

### What to check after the deploy

- Container `container="dungeontable"`: the throttled share
  `rate(container_cpu_cfs_throttled_periods_total[2m]) / rate(container_cpu_cfs_periods_total[2m])` during a session should
  be near zero. (The pod exports no metrics of its own; these come from the kubelet.)
- The manifest parses (PyYAML). `scripts/validate.py` and `kubectl kustomize` were not run locally (no flux, kubeconform or
  kubectl here); CI runs the validation on the pull request.

## 2026-11-06 — Zeef phase 0, and CI: app-defined YAML tags in ConfigMaps

To understand this, start by reading `apps/zeef/README.md`, then `infrastructure/pvcs/zeef.yaml` and
the `EmbeddedLoader` in `scripts/validate.py`. The design and runbook are in Gemberkoekje/projects
`Zeef/DESIGN.md`, `Zeef/DEPLOY.md` and `Zeef/NOTES.md`.

- **Zeef phase 0** (PR #115) adds Download Station's replacement in namespace `zeef`: qBittorrent,
  Prowlarr, Sonarr, Radarr, Cleanuparr and a nightly Recyclarr CronJob.
  - The web UIs are LAN/Tailscale only, on MetalLB `192.168.1.234`. qBittorrent's peer port is on
    `192.168.1.235`.
  - The QNAP `Multimedia` share is a static PV with `Retain` and Flux pruning disabled, mounted
    without `fsGroup`.
  - The prerequisites (NFS export, databases, 1Password item `zeef-stack`) must exist before the
    merge.
- **CI: local tags are allowed in ConfigMap contents.** The first run failed on Recyclarr's
  `!env_var` in `apps/zeef/recyclarr.yaml`: PyYAML's safe loader has no constructor for tags it
  doesn't know.
  - Recyclarr resolves `!env_var`, `!secret` and `!file` itself when it reads its config, so the YAML
    is valid. `scripts/validate.py` now parses ConfigMap contents with `EmbeddedLoader`, which reads
    any `!tag` as the plain value it tags.
  - Syntax errors and duplicate keys (also inside tagged mappings) are still errors.
  - The repository's own manifests still go through the strict loader.

## 2026-11-06 — PostgreSQL restart loop: startup probe, slower liveness

To understand this, read the `startupProbe`/`livenessProbe` comments in
`infrastructure/postgresql/postgresql-release.yaml`.

- **What happened.** From about 13:09 CET, PostgreSQL was in a restart loop. Every app on the
  shared database lost it: armabotcs and curatool crash-looped, Grafana errored, and the Zeef apps
  logged connection failures.
  - The QNAP was extremely slow at the time. The end-of-recovery checkpoint wrote 8 MB in 20 s.
    The user had just grown the Multimedia volume from 496 GB to 3.1 TB, which very likely put
    background I/O on the same disks.
  - Each start syncs the data directory over NFS (~30 s), replays the WAL, then runs the
    end-of-recovery checkpoint.
  - The chart's default liveness probe (initialDelay 30 s, 6 × 10 s) killed it during that
    checkpoint four times in a row. Every kill forced the next start into a new recovery.
  - It came back at 13:29:48, when one checkpoint finished just in time.
- **Fix.**
  - `primary.startupProbe` is enabled with 90 × 10 s = 15 minutes, the HelmRelease timeout.
    Liveness and readiness only start once it passes.
  - Liveness now allows 18 × 10 s (3 minutes, with a 10 s timeout) without an answer, instead of
    60 s. A restart doesn't help a database that is stalled on slow storage; it only adds a crash
    recovery.
  - Checked by rendering chart 18.5.14 with the new values (`helm template`).
- **What merging does.** PostgreSQL restarts once, with the preStop fast shutdown, so no crash
  recovery. Every app on it blips for about a minute.

## 2026-11-06 — LAN names: <app>.lan.gemberkoekje.nl for the internal UIs

To understand this, read `infrastructure/lan-proxy/Caddyfile` (the names), then `caddy.yaml`.

Asked: easier names than IP:port for every internal UI, Grafana included.

- **DNS** (the user's zone at the registrar):
  - `*.lan.gemberkoekje.nl` and `lan.gemberkoekje.nl` are A records to **192.168.1.236**.
  - The more specific wildcard wins over `*.gemberkoekje.nl`, which points at the public IP.
  - A private address can't be reached from the internet, so the names work only at home and over
    Tailscale (the subnet router routes `192.168.1.224/28`).
- **The switchboard:**
  - Caddy 2.11.9, 2 replicas, namespace `lan-proxy`, LoadBalancer `192.168.1.236:80`, which the
    router doesn't forward.
  - It routes by host name to each app's ClusterIP Service. Plain HTTP, like the IP:port addresses
    it replaces.
  - The config is a kustomize `configMapGenerator`, so a change rolls the pods.
- **The names:**

  | Name | Goes to |
  |---|---|
  | `lan.gemberkoekje.nl` | Start page with links |
  | `seerr.`, `jellyfin.`, `sonarr.`, `radarr.`, `prowlarr.`, `qbittorrent.`, `cleanuparr.`, `maintainerr.` | The Zeef apps (`maintainerr.` added the same day) |
  | `grafana.` | Grafana; `/` redirects to `/grafana/` |

  Each is `<name>.lan.gemberkoekje.nl`. Unknown names get a 404.
- **Grafana's `domain` is now `grafana.lan.gemberkoekje.nl`,** so alert-email links use the name.
  `http://192.168.1.230/grafana` (grafana-internal on ingress-nginx) keeps working until
  ingress-nginx is removed. Then the name is the only route, and `grafana-internal-ingress.yaml`
  can go.
- **Jellyfin's `JELLYFIN_PublishedServerUrl`** is `http://jellyfin.lan.gemberkoekje.nl`.
- **Tested:** `caddy validate` with the pinned image, and a local run. Start page 200, Grafana
  302 to `/grafana/`, unknown host 404, `/healthz` 200.
- **Live test (2026-11-06, after PR #124):** all nine names answer through 192.168.1.236. Each app
  lands on its login page, Grafana on `/grafana/login`, and the start page gives 200.
- **Gotcha: the old wildcard answer stays cached.** `*.gemberkoekje.nl` (the public IP) had a
  24-hour TTL. Resolvers that looked a `.lan` name up before the new records existed keep the old
  answer until it expires; the router (192.168.1.1) and Google (8.8.8.8) had the new one at once.
  - On 2026-11-06, Cloudflare (1.1.1.1) still served the public IP, and that PC uses 1.1.1.1 first.
  - Cloudflare's cache can be purged per name at https://one.one.one.one/purge-cache/.
  - A device's own cache needs `ipconfig /flushdns`, or airplane mode on a phone.
- **Gotcha to watch:** some home routers block public DNS answers that contain private addresses
  ("DNS rebind protection"). If the names fail at home but work over Tailscale on mobile data,
  allow `lan.gemberkoekje.nl` in the router's rebind exception list.

## 2026-11-06 — LAN names: port 443 answers, so browsers fall back to http

The `.lan` names timed out in the user's Chrome/Edge while they worked in a plain http client.
"HTTPS Upgrades" make those browsers try https first for any http:// address, and port 443 on
192.168.1.236 gave no answer at all (the Service only had port 80), so the attempt hung.

- Caddy now also listens on 8443 (Service port 443) with a certificate from its own internal CA
  (`tls internal`, `skip_install_trust`). It only redirects to the same address on http
  (`redir http://{host}{uri}`). An untrusted certificate makes the browser fall back to http at
  once. Someone who types `https://` gets a warning, then the redirect.
- `auto_https disable_redirects` instead of `off`: certificates for the https block, and no
  http→https redirects.
- Real certificates need DNS-01, and the domain's DNS (Vimexx, `ns.zxcs.*`) has no API that
  lego/libdns/cert-manager support. Moving DNS to Cloudflare was considered and dropped: Vimexx has
  DNSSEC on and no self-service way to turn it off. If the lock icon is ever wanted, the
  low-hassle route is cert-manager's acme-dns solver plus one CNAME `_acme-challenge.lan` at
  Vimexx (DNSSEC can stay on).
- Tested locally with the pinned image as UID 1000:
  - http: start page 200, Grafana 302, `/healthz` 200;
  - https: 302 to `http://<same host><same path>`, and a strict TLS client gets "untrusted root".

## 2026-11-06 — LAN names on https with a Let's Encrypt certificate

To understand this, read `configuration/certissuer-lan.yaml`, then
`infrastructure/lan-proxy/{certificate,restart}.yaml` and the Caddyfile.

- **Why.** The http fallback (PR #126) wasn't enough. The apex `gemberkoekje.nl` (`/plotboek`,
  `/grafana`, `/fileserver` through Traefik) sends `Strict-Transport-Security: max-age=15724800;
  includeSubDomains` (`configuration/traefik-hsts.yaml`, inherited from ingress-nginx's default).
  Chrome stores that for the whole domain and then refuses plain http, with no click-through, for
  every subdomain, `*.lan` included.
- **The certificate.** One Let's Encrypt certificate for `lan.gemberkoekje.nl` and
  `*.lan.gemberkoekje.nl`.
  - DNS-01 through cert-manager's built-in acme-dns solver: Vimexx, the DNS host, has no API that
    lego/libdns/cert-manager support.
  - At Vimexx, `_acme-challenge.lan.gemberkoekje.nl` is a CNAME to
    `1ee25716-1338-4406-8711-63284c80bb70.auth.acme-dns.io`.
  - The account is in 1Password `acme-dns-lan` (field `acmedns.json`, synced into the
    `cert-manager` namespace).
  - DNSSEC stays on.
  - The first issue (PR #127) took about 2.5 minutes, valid until 2027-02-04; renewal is due
    2027-01-05.
- **Caddy:**
  - All names are on https with that certificate, and http redirects to https (308).
  - The secret is a directory mount, so renewals update the files.
  - Caddy doesn't reload certificate files, so CronJob `caddy-restart` (Mondays 04:15) does a
    rolling restart. Its ServiceAccount may only get/patch the `caddy` Deployment.
- **Links that moved to https:** the start page, Grafana's `root_url`
  (`https://grafana.lan.gemberkoekje.nl/grafana/`) and Jellyfin's published URL.
- **Tested locally** with a stand-in self-signed certificate: http → https 308 with path and query
  kept, start page 200 with https links, Grafana → `/grafana/`, unknown `.lan` name 404,
  `/healthz` 200. Server-side strict dry-runs and `flux build` pass.
- **Dependency:** the public acme-dns service at auth.acme-dns.io. If it ever disappears,
  renewals fail, and the certificate shows "not Ready" a month before it expires. Then self-host
  acme-dns, or move the challenge CNAME to another provider.

## 2026-11-06 — Zeef: Bazarr for English subtitles

To understand this, read `apps/zeef/bazarr.yaml`, then the Bazarr rows in `apps/zeef/README.md`.

Asked: "make sure non-English series get English subtitles, even downloaded separately". Anime
releases had arrived without English subtitles: ToonsHub Amazon rips with no subtitle tracks,
RawsPlease raws, and French-only (VOSTFR, Tsundere-Raws) releases.

- **Bazarr** (`lscr.io/linuxserver/bazarr:v1.6.2-ls371`, the newest stable tag on 2026-11-06):
  - It reads the library through Sonarr and Radarr and fetches missing English subtitles as
    `.en.srt` next to the video.
  - It mounts the library at `/data`, the same path as Sonarr and Radarr, so no path mapping is
    needed. It runs as PUID 1000 / PGID 100 with UMASK 002, and has no `fsGroup`, like the others.
- **Database:** the shared PostgreSQL, database `bazarr`, via `POSTGRES_ENABLED` / `POSTGRES_*`
  (Bazarr's wiki: these take precedence over `config.yaml`). Bazarr creates its tables but not the
  database, so README step 2 must run before the merge. Password in `zeef-stack` field
  `BAZARR__POSTGRES__PASSWORD`.
- **`JELLYFIN__APIKEY` (optional)** is passed in for a post-processing command. It tells Jellyfin
  about a new subtitle at once; otherwise Jellyfin only sees it at its 12-hourly scan.
- **Reachable at** `192.168.1.234:6767` and `https://bazarr.lan.gemberkoekje.nl`, with a link on
  the start page.
- **Setup after the deploy** is in Gemberkoekje/projects `Zeef/DEPLOY.md`: login, Sonarr/Radarr,
  the English language profile, providers, and the post-processing command.

## 2026-11-07 — Zeef: a TRaSH anime profile in Recyclarr

To understand this, read the `sonarr:` section of `apps/zeef/recyclarr.yaml`.

Asked: fix the cause instead of searching by hand. 80 missing anime episodes were in no download
queue. Read-only release searches showed why:
- **Clannad and Strawberry Marshmallow** (2005–2007) exist only as Blu-ray or DVD releases: 0 of
  300+ releases acceptable.
  - The series profile WEB-1080p allows only WEBDL/WEBRip-1080p.
  - The series size table wants 50.4 MB/min for Bluray-1080p, so an 11 GB HEVC season is "too
    small".
  - Golden Rule HD scores x265 at -10000.
- **Dr. STONE:** SubsPlease names no source, so Sonarr parses its releases as HDTV-1080p, which
  WEB-1080p doesn't allow either.

The fix:
- **Profile `[Anime] Remux-1080p`** (TRaSH, trash_id 20e0fc959f1f1704bed501f23bdae76f).
  - It allows Blu-ray, WEB/HDTV, 720p/480p and DVD, and ranks the anime BD/Web group tiers.
  - Raws, LQ groups, VOSTFR, dub-only and AV1 score -10000.
  - Changed from the guide: `min_format_score: 0` instead of 100, so untiered fansub groups are
    allowed (Bazarr adds English subtitles where needed), and upgrades are off, as with Cleanuparr's
    proactive upgrade searches.
- **The size table stays `series`.** Recyclarr's per-quality `qualities:` overrides set Bluray-720p,
  Bluray-1080p and Bluray-1080p Remux to the anime minimum of 5 MB/min. WEB-1080p allows none of
  these, so live-action series are unaffected.
- **`assign_scores_to: WEB-1080p` on every explicitly added CF group.** Without it Recyclarr scores
  a group into every guide-backed profile, and Golden Rule HD's x265 (HD) -10000 would land in the
  anime profile.
- **Checked:** `recyclarr sync sonarr --preview` (8.8.1, run locally against the live Sonarr). It
  creates the anime profile and 37 custom formats, changes the three size minimums, and leaves
  WEB-1080p unchanged (41 CFs unchanged).
- **After the merge:**
  - run the Recyclarr job once;
  - move the anime-type series to the new profile, and set Seerr's anime profile to it, so new anime
    requests use it;
  - Cleanuparr's Seeker: "Proactive search" on, with "Use cutoff" and "Use custom format score" off.
    That searches only for missing items, one at a time, at most once a week per item. Those
    are the automatic retries that were missing.

## 2026-11-09 — Zeef: audiobooks with Audiobookshelf, AudioBookRequest and Chaptarr

To understand this, read `apps/zeef/chaptarr.yaml`, `apps/zeef/audiobookrequest.yaml` and
`apps/zeef/audiobookshelf.yaml`, then the audiobook rows in `apps/zeef/README.md`.

Asked: a stack like Sonarr, Seerr and Jellyfin for audiobooks, on the existing storage. Then: a
malware check for the audiobook downloads, like the one films and series get.

- **The chain.** AudioBookRequest (requests, like Seerr) → Chaptarr (search, grab, import, like
  Sonarr) → qBittorrent → `/data/Audiobooks` → Audiobookshelf (playback, like Jellyfin).
  - Prowlarr syncs its indexers into Chaptarr. Prowlarr has no Chaptarr app type, so Chaptarr is
    added as a "Readarr" app, the way AudioBookRequest's own test setup does it.
  - Cleanuparr checks Chaptarr's queue with the Malware Blocker and Queue Cleaner, as it does for
    Sonarr. Chaptarr support is new in Cleanuparr 2.11.0 (2026-11-08), hence the bump from 2.10.12.
    The other changes in 2.11.0 are Seeker features and fixes for other download clients.
  - **Chaptarr gets its own Malware Blocker list.** The shared blacklist that Sonarr and Radarr use
    (`cleanuparr.pages.dev/static/blacklist`, 850 patterns) is built for video. It blocks `*.mp3`,
    `*.m4a`, `*.flac`, `*.jpg`, `*.png`, `*.cue`, `*.nfo` and `*.txt`, so it would throw away most
    audiobook releases. Instead, `cleanuparr.yaml` ships a whitelist as ConfigMap
    `cleanuparr-blocklists`, mounted at `/blocklists/audiobooks.txt`: audio, cover, cue and
    companion-file extensions. Any other file (`.exe`, `.lnk`, `.scr`, `.msi`, archives, scripts)
    is skipped, and a release with nothing on the list is removed and searched again.
- **Why Chaptarr.**
  - Readarr is retired: its repo is archived and its metadata servers are gone.
  - The first design had no import step: AudioBookRequest grabbed through Prowlarr straight into
    the library folder. That left audiobooks outside Cleanuparr, which only reads the queues of
    the *arr apps (checked in its source). qBittorrent has no virus-scanner integration of its own.
  - Chaptarr is beta. Its README reports no data loss in the last 6 months across 11,000 users.
- **Chaptarr** (`chaptarr/chaptarr:0.9.965`, the newest release and identical to `latest` on
  2026-11-09):
  - Three databases in the shared PostgreSQL (`chaptarr-main`, `-log`, `-cache`), through
    `CHAPTARR__POSTGRES__*`. Chaptarr doesn't create them, so README step 2 must run first.
  - `/config` on local-path (`chaptarr-config`, Flux pruning disabled). Even with PostgreSQL,
    Chaptarr keeps a SQLite cache in `/config/staging.db` (WAL mode), which must not be on NFS.
  - Runs like the Servarr images: it starts as root, sets the owner of `/config` and drops to
    PUID 1000 / PGID 100 (UMASK 002). It mounts the library at `/data`, like Sonarr, so imports
    are hardlinks with no path mapping.
  - Its defaults leave hardlinked files alone: "Tag Audio Files with Metadata" is off, and "Use
    Hardlinks instead of Copy" is on. Ebooks are not used. (If they ever are: "Write Book Tags"
    defaults to new files, which would also change the copy that is seeding.)
- **AudioBookRequest** (`markbeep/audiobookrequest:1.11.0`): download backend Chaptarr, set in its
  UI. Database `audiobookrequest` in PostgreSQL. No volume; `/config` is an emptyDir, because the
  migration step creates that directory even with PostgreSQL. Runs as 1000:1000.
- **Audiobookshelf** (`ghcr.io/advplyr/audiobookshelf:2.37.2`):
  - SQLite on local-path (`audiobookshelf-config`); `/metadata` (covers, logs, its own backups) on
    qnap-nfs. Runs as 1000:100 on port 13378. The library is mounted read-only at `/media`.
  - **The watcher must stay on** ("Automatically watch libraries for changes", the default).
    Chaptarr reports imports through Audiobookshelf's watcher API. With the watcher off,
    Audiobookshelf answers 200, logs "Invalid library id from watcher" and adds nothing.
    Tested both ways.
- **Reachable at** `.234:13378` / `audiobookshelf.lan…`, `.234:8000` / `audiobookrequest.lan…`,
  `.234:8789` / `chaptarr.lan…`, with links on the start page.
- **Tested locally (Docker, 2026-11-08/09)**, with the pinned images, the manifests' users and
  ports, and one shared `/data` directory, on `postgres:17-alpine` with the databases made exactly
  as in README step 2:
  - Chaptarr: migrations on all three databases; `/ping` 200 after 8 s. `system/status` reports
    postgreSQL 17, and the API key comes from the env var. Root folder `/data/Audiobooks`
    accessible. A test file written as 1000:100 got mode 664, and a hardlink from
    `@Downloads/complete` worked.
  - Chaptarr → qBittorrent (`5.3.0_v2.1.2-ls486`): the download client test passed, with category
    `chaptarr`.
  - Prowlarr (`2.7.0.5723-ls167`) → Chaptarr as a Readarr app: the test passed. A stand-in
    Torznab indexer synced into Chaptarr as "(Prowlarr)", with categories 3030, 7000 and 7020.
  - Chaptarr → Audiobookshelf: the connection test passed. Audiobookshelf as 1000:100 with a
    read-only library scanned a test book; the watcher API added a book with the watcher on, and
    ignored it with the watcher off.
  - AudioBookRequest → Chaptarr: "connected". AudioBookRequest → Audiobookshelf: library listed,
    scan started.
  - Cleanuparr: 2.10.12 then 2.11.0 on the same PostgreSQL database, healthy after the upgrade.
    "Connection to Chaptarr instance successful"; a wrong key fails with 401. With the list
    mounted at `/blocklists`, Malware Blocker → Chaptarr (Whitelist, `/blocklists/audiobooks.txt`)
    saved, and the job logged "Successfully loaded 1 blocklists". Cleanuparr's matching rule,
    replayed on sample names, keeps `Part 01.mp3`, `Book.m4b`, `cover.jpg` and `Book.pdf`, and
    skips `Book.mp3.exe`, `Book.m4b.lnk`, `setup.scr`, `Book.zip` and `run.bat`.
  - Caddy 2.11.9 `validate`; `scripts/validate.py` and `scripts/check_images.py`.
- **Not tested:** a real request from end to end. The sandbox can't reach Chaptarr's metadata
  server (`api2.chaptarr.com`), so no book could be looked up, grabbed or imported, and the
  Malware Blocker never saw a real Chaptarr download. The cluster itself (local-path and NFS
  ownership) and the phone app weren't tested either.
- **After the merge:** Gemberkoekje/projects `Zeef/DEPLOY.md`, part D.

## 2026-11-09 — Chaptarr on SQLite, after a PostgreSQL outage

To understand this, read the header of `apps/zeef/chaptarr.yaml` and the `chaptarr-config` claim in
`infrastructure/pvcs/zeef.yaml`.

- **What failed.** After #143 merged, Chaptarr stopped on its first start with
  `XX000: could not compute MD5 hash: unsupported`, then "Non-recoverable failure, waiting for user
  intervention". The pod stays Running 0/1 until its 20-minute startup probe restarts it, then fails
  again. One of its PostgreSQL migrations names CHECK constraints with
  `substr(md5(schema || '.' || table || '.' || column), 1, 16)`.
- **Why.** The Bitnami chart runs the shared PostgreSQL in FIPS mode (`global.defaultFips:
  restricted`, so `OPENSSL_FIPS=yes`). OpenSSL's FIPS provider has no MD5, so SQL `md5()` fails. No
  other app on the server calls it. #143's local test passed because it ran on
  `postgres:17-alpine`, which has no FIPS mode.
- **The first fix took every database app down (#144, reverted in #145).** `primary.fips.openssl:
  "off"` renders `OPENSSL_FIPS=no`, and with that this image refused every connection with
  `FATAL: could not generate random cancel key`. From 08:18 to 08:26Z, Sonarr, Radarr, Prowlarr,
  AudioBookRequest, SpaceTraders, Curatool and ArmaBot had no database; ArmaBot and Curatool went
  into a crash loop and came back by themselves at 08:30Z. Sonarr's RSS sync has a gap for that
  window.
  - **Leave `fips` alone on the shared PostgreSQL.** `relaxed` renders `OPENSSL_FIPS=no` as well.
  - Try image-level settings in a throwaway pod before changing the shared database.
- **Fix: Chaptarr keeps its databases in SQLite**, in `/config` on local-path (`chaptarr.db`,
  `logs.db`, `cache.db`, `staging.db`), and its manifest no longer mentions PostgreSQL (no
  `CHAPTARR__POSTGRES__*`, no wait-for-postgres init container). Its migrations on SQLite contain
  no `md5()`.
  - **Tested** in a throwaway Job in `zeef` (the pinned image, the same user and env, an emptyDir
    `/config`): `/ping` 200 about 10 s after start; `system/status` reports `databaseType`
    `sqLite` 3.50.4; no errors or warnings in the log besides ASP.NET's two start-up notes.
  - **Cost:** the shared PostgreSQL's nightly backup no longer covers Chaptarr. Losing the
    local-path volume (a dead node disk) loses Chaptarr's settings and its list of books; the
    audiobook files stay on the QNAP and can be imported again. Audiobookshelf has the same trade.
- **After the merge:**
  - The Deployment rolls; the new pod creates its SQLite files in `/config` on first start.
  - The `chaptarr` role and its three databases on the shared PostgreSQL are unused. In DBeaver:
    `DROP DATABASE "chaptarr-main"; DROP DATABASE "chaptarr-log"; DROP DATABASE "chaptarr-cache";
    DROP ROLE chaptarr;`
  - The `CHAPTARR__POSTGRES__PASSWORD` field in the 1Password item `zeef-stack` can go.
  - Then Gemberkoekje/projects `Zeef/DEPLOY.md`, part D3 onwards (its D1 still lists the Chaptarr
    databases, to be updated there).

## 2026-11-09 — Maintainerr behind a login

To understand this, read the maintainerr block in `infrastructure/lan-proxy/Caddyfile`, then
`infrastructure/lan-proxy/maintainerr-login.yaml`.

- **What was open.** Maintainerr 3.32 has no login at all. Asked from another pod without
  credentials, `/api/rules` and `/api/settings` answered 200, and the settings carry the filled
  `jellyfin_api_key` and `seerr_api_key`: admin access to Jellyfin and Seerr. Anyone on the home
  network or the tailnet could read those keys, or change the rules so that the library is deleted.
  Every other Zeef UI refuses without a login (Sonarr, Radarr, Prowlarr, qBittorrent, Cleanuparr,
  Bazarr with form login, Jellyfin, Seerr, Audiobookshelf, AudioBookRequest, Chaptarr).
- **Fix.**
  - Caddy asks for a user name and password on `maintainerr.lan.gemberkoekje.nl` (`basic_auth`).
    The user name and a bcrypt hash of the password come from the 1Password item `lan-proxy` as
    environment variables. The repository is public, so even the hash stays out of Git.
  - Maintainerr's Service is now ClusterIP, so `192.168.1.234:6246` is closed and Caddy is the only
    way in. Nothing else calls Maintainerr; it only calls Jellyfin, Sonarr, Radarr and Seerr.
  - Caddy reads `{$MAINTAINERR_USER}` and `{$MAINTAINERR_PASSWORD_HASH}` once, when it starts.
    After changing the item, restart Caddy (`kubectl -n lan-proxy rollout restart deploy/caddy`).
- **Tested** before the PR: `caddy validate` of the new Caddyfile in a running Caddy pod
  (caddy 2.11.9) with a throwaway user and hash; a second Caddy in that pod on a spare port with the
  same block answered 401 without credentials, 401 with a wrong password and 200 with Maintainerr's
  page with the right one; `kubectl apply --server-side --dry-run=server` accepted the Service
  change from LoadBalancer to ClusterIP.
- **Before the merge:** create the item, or the new Caddy pods wait in
  `CreateContainerConfigError`. The old pods keep serving, so the names stay up, but a kured reboot
  could then take them away.
  - Hash: `kubectl -n lan-proxy exec -it deploy/caddy -- caddy hash-password` (asks for the
    password twice, prints the hash).
  - 1Password, vault Gembercluster: item **`lan-proxy`**, with the fields `MAINTAINERR_USER` and
    `MAINTAINERR_PASSWORD_HASH`.
- **After the merge:** the browser asks for the login once on `maintainerr.lan.gemberkoekje.nl`.
  Projects `Zeef/DEPLOY.md` still mentions Maintainerr's port 6246, to be updated there.

## 2026-11-11 — qBittorrent back to 5.2.4 for MyAnonamouse

To understand this, read the image line in `apps/zeef/qbittorrent.yaml`, then this entry.

- **Why.** MyAnonamouse does not allow qBittorrent 5.3.0 yet. The image goes from
  `5.3.0_v2.1.2-ls486` to `5.2.4_v2.0.15-ls481`, the newest 5.2 build, which also takes libtorrent
  from 2.1.2 back to 2.0.15. 5.2.4 (2026-09-28) ends the 5.2 line: its branch has nothing after the
  tag, so no more fixes will come, and Zeef should move up once MAM allows 5.3.x.
- **What 5.2.4 lacks.** Nothing Zeef relies on. 5.3.0 added conveniences: share limits that must
  all be met before they act (5.2.4 acts on whichever limit comes first), downloading finished
  files and free disk space in the WebUI, IP range bans, filtering by infohash, a .torrent backup
  folder, and libtorrent 2.1's pread disk I/O. Its security fixes do not reach this setup. The
  X-Forwarded-For login bypass (#24889) needs reverse-proxy support switched on in qBittorrent,
  behind a proxy that passes a client's own X-Forwarded-For along; Caddy replaces that header (no
  `trusted_proxies` in the Caddyfile). The rest is CSRF hardening and mail and dynamic-DNS fixes.
- **Checked in the source** (qBittorrent release-5.2.4 against release-5.3.0, libtorrent v2.0.15
  against v2.1.2):
  - The torrents load. libtorrent 2.1 writes resume files with `file-version` 2, and 2.0.15 reads
    versions 1 and 2. 5.3.0 still writes every `qBt-*` key that 5.2.4 reads and only adds
    `qBt-shareLimitsMode`; `categories.json` only gains `share_limits_mode`.
  - The config loads. 5.3.0 left `Meta\MigrationVersion` at 12; 5.2.4 knows up to 8, so it runs no
    migration and writes 8 back.
  - **The WebUI settings do not carry over.** 5.3.0 moved them from `WebUI\*` under `[Preferences]`
    to their own `[WebUI]` section (its migration 11), and 5.2.4 reads only the old place. On 5.2.4
    the login is `admin` with a temporary password printed in the pod log, and the WebUI tab
    (subnet whitelist, reverse proxy, API key, ban settings) is back to defaults. The `[WebUI]`
    section stays in the file, unused.
  - Disk I/O. "Default" is pread in libtorrent 2.1 but memory-mapped files in 2.0.15, the mode
    known for high memory use and trouble on network storage. The downloads are on the QNAP NFS
    share, and the pod has a 1 GiB memory limit.
- **After the merge** (the new pod starts on 5.2.4):
  1. `kubectl -n zeef logs deploy/qbittorrent | grep -i "temporary password"`, then sign in on
     `qbittorrent.lan.gemberkoekje.nl` as `admin` with that password.
  2. Options → WebUI: set the user name and password the apps were given (the password is
     `QBITTORRENT__PASSWORD` in the 1Password item `zeef-stack`), and whatever else was changed on
     that tab.
  3. Options → Advanced → Disk IO type: "Simple pread/pwrite" (libtorrent's mmap backend made to
     always use pread/pwrite, the closest to what 2.1 did). Save.
  4. `kubectl -n zeef rollout restart deploy/qbittorrent`. It applies the disk I/O type and lifts
     the bans: after 5 failed logins qBittorrent bans an address for an hour, and Sonarr, Radarr,
     Chaptarr and Cleanuparr kept trying the old login until step 2.
  5. MAM's tracker shows "Working" on its torrents, and the apps' download client tests pass.
- **Moving back to 5.3.x:** check MAM's client list first. 5.3.x then runs its migrations 9 to 12
  again and moves the WebUI settings from step 2 into `[WebUI]`, over the stale ones, so nothing
  needs redoing. Set Disk IO type back to "Default" (pread with libtorrent 2.1) and restart.

## 2026-11-11 (evening) — After the downgrade: API keys, MAM in Chaptarr, seeding

To understand this, read the entry above, then projects `Zeef/DEPLOY.md` B3, B7 and D3 to D5,
updated the same evening.

- **The apps log in with qBittorrent's API key, not the password.** Sonarr, Radarr, Chaptarr
  (Settings → Download Clients → qBittorrent) and Cleanuparr (Download Clients) send it as
  `Authorization: Bearer`. Step 2 above was incomplete: 5.2.4 couldn't see 5.3.0's key either (it
  sat in the `[WebUI]` section), so a new key was made and put into all four.
  - API-key requests are never banned. 5.2.4 bans an address only after 5 failed
    username/password logins (an hour, in memory, gone after a restart). A missing or wrong key
    gets a plain 403 with the body `Forbidden`.
  - Chaptarr's qBittorrent client refuses a user name or password next to an API key.
- **Restarting qBittorrent.** Flux undoes `kubectl rollout restart`: about 18 seconds later it
  removes the `restartedAt` annotation, so the pod restarts a second time (harmless with
  Recreate; step 4 above did exactly that). For a single restart:
  `kubectl -n zeef scale deploy/qbittorrent --replicas=0`, wait until the pod is gone, then
  `--replicas=1`.
- **Seeding limits.** Global: ratio 2.0 (was 1.0) or 7 days, then Stop. Category `chaptarr`:
  `"ratio_limit": -1` in `/config/qBittorrent/categories.json` (the old file is
  `categories.json.bak-2026-11-11`), because MAM wants 72 hours of seeding per torrent and a ratio
  stop can come sooner.
  - qBittorrent takes the torrent's own limit, then its category's (and the parents'), then the
    global one. Chaptarr leaves the ratio at "default" (-2), so the category's applies.
  - 5.2.4's WebUI and API can't edit a category's share limits (5.3.x's can), hence the file.
    qBittorrent writes it only when a category is added, changed or removed, so an edit made while
    it runs survives a restart.
- **MAM goes through Chaptarr's own indexer, not Prowlarr's.** Chaptarr 0.9.965 has a native
  MyAnonaMouse indexer. It rejects VIP-only torrents unless the account is VIP, pauses MAM grabs
  before the limit on unsatisfied torrents ("Protect Unsatisfied Slots", reserve 5), and sends its
  Seed Time (default 72 hours, minimum 72) to qBittorrent as the torrent's seeding limit.
  - Through Prowlarr, Chaptarr tried two VIP-only releases. MAM answered 406, "Download blocked:
    VIP torrent and you are not VIP or higher", and Prowlarr then disabled the indexer for a few
    minutes, so the next grab got a 429.
  - Chaptarr ranks releases by title match, native category, format, profile preference,
    protocol, indexer priority, size and then seeders. With every indexer on priority 25, *The Way
    of Kings* came from Knaben (public); MAM on priority 10 wins otherwise equal releases.
- **Queued torrents earn no seeding time on MAM**, since they don't announce. Chaptarr's
  qBittorrent client has Initial State "Force Start", and qBittorrent 5.2.4 skips share limits for
  forced torrents (`processTorrentShareLimits` returns early): they seed until stopped by hand, and
  Chaptarr never removes them. Indexers can be pinned to a download client, so a second client,
  "qbittorrent MAM" (category `chaptarr mam`, Force Start), takes the MAM indexer's grabs (DEPLOY
  D3). A torrent added to qBittorrent by hand gets no Force Start; force-start it there.
- **Cleanuparr 2.11.0 and private torrents.** The Malware Blocker has Ignore Private (on), queue
  rules have a Privacy Type (Public, Private or Both), and Failed Import has Ignore Private. A
  skipped file would leave a MAM torrent seeding only in part. Cleanuparr did skip a file in *The
  Way of Kings*, a 4 KB checksum file named `.sv`, but that torrent is public (private flag 0).
- **Chaptarr doesn't search missing books on a schedule.** 0.9.965's tasks are RSS sync, download
  monitoring, refreshes, the MAM account status, Hardcover sync, housekeeping and backups. RSS only
  sees new uploads, so after adding an indexer: Wanted → Missing → Search All.
- **Checked that evening:**
  - *The Way of Kings* (Knaben, 38 MP3s, 1.9 GB) was downloading in category `chaptarr`, with the
    category's no-ratio limit.
  - *Project Hail Mary* is in `/data/Audiobooks/Andy Weir/Project Hail Mary - Ray Porter/` as a
    hardlink (2 links). Its torrent (public) stopped after 29 minutes of seeding, and its data
    still sits under `@Downloads/incomplete`. qBittorrent's log no longer reaches back far enough
    to say why.
- **Set up the same evening:** the client "qbittorrent MAM" (category `chaptarr mam`, Initial
  State Force Start) and the MyAnonaMouse indexer (priority 10, pinned to that client, Seed Time
  256 hours, Protect Unsatisfied Slots on; MAM reported 1 of 20 unsatisfied). *Elantris*, added to
  qBittorrent by hand in that category, was imported by Chaptarr as a hardlink.
- **Still open:** projects `Zeef/DEPLOY.md` D1 and D9 still describe Chaptarr on PostgreSQL (from
  2026-11-09).

## 2026-11-11 (night) — Tailscale subnet router: room for video streams

To understand this, read the `resources` block and its comment in
`infrastructure/tailscale/subnet-router.yaml`, then this entry.

- **Symptom.** Jellyfin "hiccups": playback on the phone (Findroid) and in the browser stopped and
  restarted. Jellyfin itself was fine. In 5 days it had no restarts, was never unready and peaked at
  0.5 CPU and 1.2 GiB (limit 2 GiB), with at most 1.2% CPU throttling. NFS had no retransmissions
  on any node.
- **Cause: the subnet router ran out of memory.** Every Findroid and Jellyfin Web session of the
  past 4 days went through it, with the phone on the home Wi-Fi and Tailscale on. Its direct
  endpoint was 192.168.1.120, so it was on the LAN. Kodi on the PC connects directly: the router
  relayed nothing during its sessions.
  - One stream is 3-9 Mbit/s and costs the router 100-200 MiB (userspace networking ends each
    connection in the pod and buffers both sides). With two streams at 22:20 it reached 255 MiB; at
    23:40 it hit 256 MiB and was OOMKilled at 23:40:19. The new container went straight back to
    255 MiB.
  - At the limit, the kernel kept evicting tailscaled's code and reading it back: 1,500-2,700 major
    page faults/s, 140-300 MB/s of reads from node-02's disk, and node-02 iowait at 29-51%. Jellyfin's
    config (local-path) sits on that disk, so those minutes were slow for every client.
  - The Jellyfin log matches: Findroid playback stopped and restarted at 23:34:57, at 23:42:41 (after
    the OOM kill) and at 23:43:29.
- **Fix.** The memory limit goes from 256Mi to 1Gi, the request from 64Mi to 128Mi, and
  `GOMEMLIMIT=768MiB` makes Go collect garbage before the limit. Go doesn't read the cgroup limit,
  and by default it lets the heap reach about twice the live data.
- **Not chosen: kernel networking** (`TS_USERSPACE=false`). The kernel would route the packets
  instead of the pod proxying each connection, which uses far less memory. But it needs root,
  `NET_ADMIN`, `/dev/net/tun` and `net.ipv4.ip_forward` (not a safe sysctl), exactly the privileges
  this pod avoids. Revisit if 1 GiB isn't enough.
- **Devices at home use the router too** when Tailscale is on. The routes (/29 and /28) are
  narrower than the home /24, so they win there as well as on foreign networks. With enough memory
  that costs nothing. Turning Tailscale off at home gives the direct path.
- **To check after the merge,** while something is streaming over Tailscale:
  `container_memory_working_set_bytes{namespace="tailscale"}` stays well under 1 GiB,
  `rate(container_fs_reads_bytes_total{namespace="tailscale"}[5m])` stays near 0, and
  `kubectl -n tailscale get pod` shows no new restarts.
- **Seen in passing** (not Jellyfin): spacetraders-api restarted 119 times in the past week (Error,
  one OOMKilled), but not since the 19:00 deploy. armabotcs and curatool both exited with code 139
  (segfault) at 08:25 UTC on 2026-11-09, on different nodes. The eno1 counters show receive drops
  only, no errors. The metallb-speaker restarts line up with kured reboots.

## 2026-11-12 — graphify out, MAP.md in, vortexplotboek's old files archived

To understand this, read [MAP.md](MAP.md), then [CLAUDE.md](CLAUDE.md).

- **Why.** The graphify knowledge graph went stale with every manifest change. In this YAML repo
  all its nodes came from semantic extraction, which only a full re-extract refreshed. A short map,
  kept up to date in the same commit as each change, replaces it.
- **Removed:**
  - `graphify-out/` (graph, cache and Obsidian vault: 378 generated files).
  - `.claude/settings.json`, whose only content was two `graphify hook-guard` hooks (on Bash/Grep
    and Read/Glob).
  - The graphify section of `CLAUDE.md`.
  - The `graphify-out/` exclusions in `scripts/validate.py`.
- **Added:**
  - `MAP.md`: the folders in Flux's order, the IP addresses, the three ways in (internet, LAN
    names, Tailscale), the shared services, the apps and their dependencies, the infrastructure and
    the checks.
  - `CLAUDE.md` now points at MAP.md and NOTES.md and says when MAP.md must change.
- **Checked while writing the map:** every app's `ConnectionStrings__*` host is
  `postgresql.flux-system.svc.cluster.local` (11 apps; only the host and database name were read
  from the live Secrets).
- **vortexplotboek's old app files are archived; its redirect stays.** The app has run on the-vortex
  cluster since 2026-10-23. Commit 0910ef7 (2026-11-02) removed everything here except the redirect.
  - `archive/vortexplotboek/` now holds those removed files, in the repository's own layout (see
    `archive/README.md`): the Deployment at `replicas: 0`, the sync CronJob, the 1Password item
    references and the `kustomization.yaml`. It also holds the Ingress from before the redirect.
  - Unchanged and still live: the Ingress that sends `vortexplotboek.gemberkoekje.nl` and
    `gemberkoekje.nl/vortexplotboek` to `https://plotboek.the-vortex.nl/vortexplotboek`, the
    pod-less Service it names as its backend, and the Namespace.
  - `scripts/check_images.py` skips `archive/`, since those images aren't deployed. A missing image
    (the old one on GitLab) would otherwise hold a pull request for 20 minutes and then fail it.
    `scripts/validate.py` doesn't treat archived files as manifests.
- **The Traefik header comment is fixed.** It still said the router sent public traffic to
  ingress-nginx on .230. The router has pointed at Traefik (.231) since 2026-09-26.

## 2026-11-12 — Traefik phase 4, step 1: keep the IngressClass

To understand this, read phase 4 and the last progress-log entry in
[docs/ingress-nginx-migration-plan.md](docs/ingress-nginx-migration-plan.md), then
`infrastructure/traefik/ingressclass.yaml`.

- **Why.** ingress-nginx gets no security fixes and has served nothing since the cutover, so it can
  go. Uninstalling it would make Helm delete IngressClass `nginx-public`, which every Ingress names
  and which Traefik's Ingress NGINX provider serves. Step 1 makes the class survive the uninstall.
- **Change:**
  - The keep annotation in `infrastructure/nginx/nginx-release.yaml`.
  - The IngressClass in `infrastructure/traefik/ingressclass.yaml`, listed in its
    `kustomization.yaml`.
  - A line in MAP.md saying where the class is defined.
- **Checked:**
  - Chart 4.15.1 renders the annotation, and nothing else in the render changes.
  - A server-side dry run as kustomize-controller accepted the IngressClass.
  - `flux build` of `infrastructure` passes.
  - The checks for removal (certificates, traffic, Grafana) are in the plan's log.
- **The next PR (step 2) waits** until the live IngressClass shows the keep annotation.

## 2026-11-12 — Traefik phase 4, steps 2–4: ingress-nginx removed

To understand this, read the last progress-log entry in
[docs/ingress-nginx-migration-plan.md](docs/ingress-nginx-migration-plan.md), then
`infrastructure/traefik/traefik-release.yaml` and `infrastructure/traefik/ingressclass.yaml`.

- **Step 1 was live first.** Helm release v16 is `deployed` and stores the IngressClass with
  `helm.sh/resource-policy: keep`. The live object has the annotation and Flux's labels.
- **Removed:** `infrastructure/nginx/` (the HelmRelease: the controller, its LoadBalancer on .230
  and its admission webhook) and `repos/nginx-repo.yaml`.
- **Traefik's `publishService` is on.** The Ingresses' status shows .231 instead of ingress-nginx's
  stale .230. In the chart render this adds one argument,
  `--providers.kubernetesingressnginx.publishservice=traefik/traefik`; the ClusterRole already
  allows updating `ingresses/status`.
- **.230 is free.** Grafana by IP is now `http://192.168.1.231/grafana`; the main address stays
  `https://grafana.lan.gemberkoekje.nl`.
- **Text updated** wherever it still pointed at .230 or ingress-nginx: MAP.md, the plan, and the
  comments in the Traefik release, the IngressClass, the Grafana release, the HSTS middleware, the
  spacetraders Ingress and README, and the print-manager-test Service.
- **Checked:**
  - The Traefik render differs only by the `publishService` argument.
  - A server-side dry run of the HelmRelease was accepted.
  - `kubectl kustomize` builds infrastructure, repos, configuration, ingress and apps, and
    `flux build` builds infrastructure and repos with no nginx objects left.
- **Left behind by the uninstall:** `kube-system/nginx-ingress-public-ingress-nginx-admission`, the
  webhook's certificate secret. A hook job created it, so Helm doesn't track it. Three more such
  secrets survive from ingress-nginx releases removed over a year ago
  (`nginx-ingress-ingress-nginx-admission`, `nginx-ingress-internal-…`, `nginx-ingress-private-…`).
  None is used, and none is in Git; delete them by hand.
- **After the merge (2026-11-12):**
  - The uninstall hung on the `.230` Service, whose old ServiceLB finalizer nothing removes any
    more. Removing it by hand finished the uninstall.
  - `flux-system/postgresql` carries the same finalizer.
  - The four admission Secrets are deleted.
  - Details and checks are in the plan's progress log.

## 2026-11-12 — Gateway API for public routes, kluskat first

To understand this, read the "Public routes" section of [CLAUDE.md](CLAUDE.md), then
`infrastructure/traefik/gateway.yaml` and `ingress/kluskat-route.yaml`; the reasoning is phase 5 of
[docs/ingress-nginx-migration-plan.md](docs/ingress-nginx-migration-plan.md).

- **Why Gateway API.** The Ingresses spoke ingress-nginx's annotation dialect, so retiring that
  controller meant migrating every route. Gateway API routes don't depend on the controller, and
  Traefik supports them. Its CRDs (v1.6.3, standard channel) were already installed by the Traefik
  chart.
- **The pieces:**
  - **Traefik:** `providers.kubernetesGateway` on; the chart's GatewayClass `traefik`; the chart's
    default Gateway off.
  - **The Gateway** `traefik/public` in Git: an `http` listener (port 80, routes from every
    namespace) and an `https-kluskat` listener (kluskat's hostname, Secret `kluskat-tls` in
    `traefik`, routes only from namespace `kluskat`). Listener ports are Traefik's in-pod
    entrypoint ports, 8000 and 8443.
  - **cert-manager:** `config.gatewayAPI.enabled`. Its gateway-shim reads the Gateway's
    `cert-manager.io/cluster-issuer: letsencrypt-gateway` annotation and issues a certificate per
    HTTPS listener.
  - **A new ClusterIssuer,** `letsencrypt-gateway`. It answers HTTP-01 with a temporary HTTPRoute
    (exact path) on the `http` listener. `letsencrypt-prod` stays for the Ingresses.
  - **kluskat's Ingress is replaced** by two HTTPRoutes: a 301 to HTTPS on `http`, and the app on
    `https-kluskat`.
- **The rule:** new public routes (and reworked ones) use this layout; no new Ingress objects or
  nginx annotations. CLAUDE.md has the steps; MAP.md shows both kinds of route.
- **Expect a short TLS gap on kluskat at the merge.** The Ingress and its certificate leave, and the
  Gateway's certificate takes a minute or so to be issued. cert-manager's self-check only asks Let's
  Encrypt to validate once the challenge URL answers, so a failed attempt costs no backoff.
- **Checked before the merge:** chart renders (only the intended changes), server-side dry runs,
  and `kubectl kustomize`/`flux build` (details in the plan's log).
- **To check after the merge:**
  - `kubectl -n traefik get gateway public` is Programmed, and the Certificate `traefik/kluskat-tls`
    is Ready.
  - `https://kluskat.gemberkoekje.nl` answers with a valid certificate and an HSTS header, and
    `http://` gives a 301 to `https://` without a port.
  - Then delete the old Secret `kluskat/kluskat-tls`.
