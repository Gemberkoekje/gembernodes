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
