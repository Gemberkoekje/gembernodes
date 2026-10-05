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
