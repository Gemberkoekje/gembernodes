# Plan: replace ingress-nginx with Traefik

Status (2026-09-26): phases 0–3 are done, and public traffic goes through Traefik (see the
progress log at the end). Next: phase 4, removing ingress-nginx, after a few quiet days.

To understand this, start by reading the 2026-09-26 section of [NOTES.md](../NOTES.md), then
[infrastructure/nginx/nginx-release.yaml](../infrastructure/nginx/nginx-release.yaml),
[configuration/certissuer.yaml](../configuration/certissuer.yaml) and the files in [ingress/](../ingress/).

## Why

ingress-nginx was retired by the Kubernetes project: best-effort maintenance ended in March 2026, and
there are no further releases, bug fixes or security fixes. It is this cluster's internet-facing entry
point (the router forwards 80/443 to it), so it has to go.

## Current setup

- **Controller:** HelmRelease `kube-system/nginx-ingress-public`, chart `ingress-nginx` 4.x (controller
  1.15.1), IngressClass `nginx-public` (controller `k8s.io/ingress-nginx`). It runs 2 replicas behind a
  MetalLB LoadBalancer on `192.168.1.230` with `externalTrafficPolicy: Local`. The admission webhook's
  failurePolicy is Ignore, and the global config sets `strict-validate-path-type: false`,
  `strict-validate: false` and `allow-snippet-annotations: false`.
- **Certificates:** ClusterIssuer `letsencrypt-prod`, HTTP-01 solver with `ingressClassName: nginx-public`.
  Every Ingress requests its certificate through the `cert-manager.io/cluster-issuer` annotation.
- **Routes:** every app is reachable on its own subdomain *and* on a path of the apex `gemberkoekje.nl`.

| Ingress (namespace) | Routes | nginx annotations that change behaviour |
|---|---|---|
| adventureengine | `/adventureengine`, `adventureengine.` | ssl-redirect |
| cov-website | `/cov-website`, `cov-website.` | ssl-redirect |
| curatool | `/curatool`, `curatool.` | ssl-redirect |
| dungeontable | `/dnd`, `dungeontable.` | ssl-redirect |
| ebi-cs-api | `/ebi-cs-api`, `ebi-cs-api.` | ssl-redirect |
| ebi-cs-frontend (ebi-cs-api) | `/ebi-frontend(/\|$)(.*)`, `ebi-frontend.` `/(/\|$)(.*)` | use-regex, rewrite-target `/$2` |
| file-server | `/fileserver`, `fileserver.` | proxy-body-size 200m |
| healthcheck (cluster-healthcheck) | `/healthcheck`, `healthcheck.` | ssl-redirect |
| hackerminigames | `/hackerminigames`, `hackerminigames.` | ssl-redirect |
| vortexplotboek | `/vortexplotboek`, `vortexplotboek.` | proxy-buffer-size 32k, proxy-buffers-number 4 (large OIDC headers) |
| grafana-internal (monitoring) | any host, `/grafana` | ssl-redirect false, whitelist-source-range (LAN only) |

Behaviour that comes from nginx defaults rather than annotations, and has to be recreated or checked:

- HSTS: nginx sends `Strict-Transport-Security` (about 6 months, includeSubDomains) on every HTTPS response.
- `use-regex` on ebi-cs-frontend turns *every* path on the `gemberkoekje.nl` host into a regex, across all Ingresses.
- The ebi-cs-frontend subdomain rule `/(/|$)(.*)` only matches `/` and `//…` literally. Check what nginx actually serves there before "fixing" it.
- Request bodies are buffered by nginx (and limited to 1 MB except on fileserver); Traefik streams them without a limit.

Leftovers relevant to Traefik: k3s's bundled Traefik is disabled, but its CRDs (`traefik.io`, `hub.traefik.io`),
the Gateway API CRDs and the ClusterRoleBindings `helm-kube-system-traefik` and `helm-kube-system-traefik-crd`
are still in the cluster.

## Decision

**Traefik v3 (≥ 3.6.2), installed by Flux, serving the existing Ingress objects through its
`kubernetesIngressNGINX` provider.** That provider reads the nginx annotations used here (ssl-redirect,
rewrite-target, use-regex, proxy-body-size, proxy-buffer-size, whitelist/allowlist-source-range), so the
Ingresses don't have to be rewritten for the move. Traefik is also what k3s ships, and RKE2 made the same
move with a published guide.

Options considered and set aside:

- **Gateway API** (Envoy Gateway, NGINX Gateway Fabric, or Traefik's own Gateway provider): the long-term
  standard, but every Ingress becomes an HTTPRoute, TLS moves to Gateway listeners and cert-manager needs its
  Gateway integration. Too much at once; it can be done later on top of Traefik (phase 5).
- **Re-enabling k3s's bundled Traefik:** it would be configured through a k3s HelmChartConfig and versioned with
  k3s, outside this repo's Flux flow.
- **F5's NGINX Ingress Controller** (`nginx-ingress`): a different project with different annotations, so the
  same rewrite work without the compatibility layer.

## Phases

Each phase ends in a state that can stay as-is for days.

### Phase 0: prerequisites

1. k3s ServiceLB is disabled (NOTES.md runbook step 4). Otherwise ServiceLB also picks up Traefik's
   LoadBalancer Service and tries to bind 80/443 on every node, which nginx's svclb pods already hold.
2. The router forwards 80/443 to `192.168.1.230` (NOTES.md runbook step 0).
3. Delete the leftover k3s ClusterRoleBindings `helm-kube-system-traefik` and `helm-kube-system-traefik-crd`.

### Phase 1: install Traefik next to nginx (no traffic)

- `repos/traefik-repo.yaml`: HelmRepository `traefik`, `https://traefik.github.io/charts` (`source.toolkit.fluxcd.io/v1`).
- `namespaces/traefik-namespace.yaml`.
- `infrastructure/traefik/traefik-release.yaml` (+ `kustomization.yaml`, listed in `infrastructure/kustomization.yaml`).
  Pin the chart major and set `install.crds: CreateReplace` / `upgrade.crds: CreateReplace` so the chart's
  CRDs replace the stale k3s ones. Values, to be checked key by key against that chart version's
  `values.yaml` (a misspelled key is silently ignored):

  ```yaml
  deployment:
    replicas: 2
    podAnnotations:                       # let the existing Prometheus scrape Traefik's metrics
      prometheus.io/scrape: "true"
      prometheus.io/port: "9100"
  podDisruptionBudget:
    enabled: true
    maxUnavailable: 1
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: kubernetes.io/hostname
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          app.kubernetes.io/name: traefik
  service:
    annotations:
      metallb.io/loadBalancerIPs: 192.168.1.231
    spec:
      externalTrafficPolicy: Local        # keep client IPs for the grafana-internal allowlist
  ingressClass:
    enabled: false                        # keep using nginx-public
  providers:
    kubernetesIngress:
      enabled: false                      # the NGINX provider serves the Ingresses; both would create duplicate routers
    kubernetesCRD:
      enabled: true                       # for the HSTS Middleware
    kubernetesIngressNGINX:
      enabled: true
      ingressClass: nginx-public
      controllerClass: k8s.io/ingress-nginx
      # no publishService while nginx still runs, so the two don't fight over Ingress status
  ports:
    websecure:
      transport:
        respondingTimeouts:
          readTimeout: 0                  # Traefik v3 defaults to 60s, which cuts off long fileserver uploads
      http:
        middlewares:
          - traefik-hsts@kubernetescrd
  ```
- `configuration/traefik-hsts.yaml` (the `configuration` Kustomization runs after `infrastructure`, so the CRD exists):

  ```yaml
  apiVersion: traefik.io/v1alpha1
  kind: Middleware
  metadata:
    name: hsts
    namespace: traefik
  spec:
    headers:
      stsSeconds: 15724800
      stsIncludeSubdomains: true
  ```

Done when: two Traefik pods are running on different nodes, the Service has `192.168.1.231`, and
`kubectl get ingress -A` still shows `192.168.1.230` everywhere. Rollback: remove the files, and Flux uninstalls Traefik.

### Phase 2: verify everything through .231

Traefik now serves the same Ingresses as nginx, but only nginx gets real traffic. From a LAN machine:

```bash
# per host: HTTPS answer, and the HTTP → HTTPS redirect
curl -sS -o /dev/null -w '%{http_code}\n' --resolve adventureengine.gemberkoekje.nl:443:192.168.1.231 https://adventureengine.gemberkoekje.nl/
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' --resolve adventureengine.gemberkoekje.nl:80:192.168.1.231 http://adventureengine.gemberkoekje.nl/
# certificate and HSTS
curl -sSI --resolve adventureengine.gemberkoekje.nl:443:192.168.1.231 https://adventureengine.gemberkoekje.nl/ | grep -i strict-transport
```

Check list:

- [ ] Every subdomain and every apex path (`/adventureengine`, `/dnd`, `/fileserver`, `/healthcheck`, …) answers like it does on .230, with its own Let's Encrypt certificate.
- [ ] ebi-frontend on the apex (`/ebi-frontend/...`) and on the subdomain behaves exactly like nginx (compare responses from .230 and .231).
- [ ] fileserver: an upload over 1 MB that takes longer than 60 seconds.
- [ ] vortexplotboek: a full Google/OIDC login. Point the browser at .231 through a hosts-file entry.
- [ ] Any app with WebSockets/SignalR/Blazor Server keeps its connection.
- [ ] `http://192.168.1.231/grafana` works from the LAN.
- [ ] Strict-Transport-Security header present.

Rollback: nothing to roll back, nginx still serves all traffic.

### Phase 3: cut over

1. Change the router's 80/443 port-forward from `192.168.1.230` to `192.168.1.231`. It takes effect at once, and switching it back is the rollback.
2. Use `http://192.168.1.231/grafana` on the LAN and set `grafana.ini.server.domain` to `192.168.1.231`.
3. cert-manager needs no change: its HTTP-01 solver Ingresses use class `nginx-public`, which Traefik now serves.
   Confirm with the next renewal (`kubectl get certificate -A` shows renewal times), or force one on a single certificate.
4. From a phone on mobile data, `https://<public ip>/grafana` must be refused (allowlist).
5. Leave it running for a few days; watch the Grafana alerts and Traefik's logs.

### Phase 4: remove ingress-nginx

1. Keep the IngressClass: add `controller.ingressClassResource.annotations: {helm.sh/resource-policy: keep}` to
   `nginx-release.yaml` and push. Then commit an `IngressClass` manifest for `nginx-public` (controller
   `k8s.io/ingress-nginx`) under `infrastructure/traefik/`, so Git owns it once Helm lets go.
2. Delete `infrastructure/nginx/` (and its line in `infrastructure/kustomization.yaml`) and `repos/nginx-repo.yaml`.
   Flux uninstalls ingress-nginx, including its admission webhook.
3. Turn on the NGINX provider's `publishService` so Ingress status shows Traefik's IP.
4. Optionally move Traefik to `.230` (change its MetalLB annotation, then point the router back), or keep `.231` for good.

Rollback: restore `infrastructure/nginx/` from git history and point the router back at .230.

### Phase 5 (optional, later): native Traefik or Gateway API

The NGINX provider is a compatibility layer. Converting the Ingresses to `ingressClassName: traefik` with
Traefik Middlewares, or to Gateway API HTTPRoutes, removes the dependency on nginx annotation semantics.
That covers StripPrefix for ebi-frontend, IPAllowList for grafana-internal and a scheme redirect. It is not urgent.

## Effort

Phases 0–2 take an evening. Phase 3 takes ten minutes plus a few days of watching. Phase 4 takes half an hour.

## Progress log

**2026-09-26, phases 0–1** (`a07ec39`):

- Phase 0 done: ServiceLB was disabled earlier the same day, and the dead ClusterRoleBindings
  `helm-kube-system-traefik(-crd)` were deleted.
- Traefik chart 41.6.0 (Traefik v3.7.13), in `infrastructure/traefik/traefik-release.yaml`, with
  the HSTS Middleware in `configuration/traefik-hsts.yaml`. It runs 2 pods (gembernode-01 and 03)
  on `192.168.1.231` with `externalTrafficPolicy: Local`. It doesn't write Ingress status; every
  Ingress still shows `.230`.
- Differences from the values sketched in phase 1, found while checking them against the chart's
  `values.yaml`:
  - access logs are `accessLog.enabled`;
  - `ingressClass` defaults to `enabled: true, isDefaultClass: true`, so it is turned off to keep
    Traefik from becoming the cluster's default class;
  - `providers.kubernetesIngress` is on by default, so it is turned off explicitly;
  - the websecure `readTimeout` is `600s` rather than unlimited;
  - `global.checkNewVersion: false`. Anonymous usage reporting is already off by default in this
    chart version.
- Traefik logs one warning, "SafeNaming is not explicitly set". It is informational: the
  `traefik-hsts@kubernetescrd` reference relies on the legacy naming, so it stays unset.

**Phase 2, automated comparison:** every host and apex path in `ingress/`, fetched through `.230`
and `.231` with `curl --resolve`, gave the same status codes, the same redirect targets
(trailing-slash, login and HTTP→HTTPS 308 redirects), valid certificates and the HSTS header.
Response sizes matched to within a few bytes (per-request tokens). `/grafana` works on both from
the LAN.

The browser checks through a hosts-file entry pointing at `.231` also passed: the vortexplotboek
sign-in, a large fileserver upload and dungeontable.

**2026-09-26, phase 3:** at about 13:50Z the router's 80/443 port-forward was moved from
`192.168.1.230` to `192.168.1.231`. A phone on mobile data loads the sites normally. Traefik's
access log shows the external clients (client IPs are preserved) and no errors, and
ingress-nginx's external traffic dropped to nothing. Rollback is pointing the router back at
`.230`; ingress-nginx still serves every Ingress until phase 4.

Before phase 4, let a certificate renewal run through Traefik (the ebi-cs-api certificates renew
on 2026-09-26 around 16:02Z; check `kubectl get certificate -A`) and a night's kured reboot
cycle. Decision for phase 4: Traefik keeps `192.168.1.231`, since the router already points there,
so ingress-nginx's `.230` is simply released. That means `grafana.ini.server.domain` and Grafana
bookmarks move to `.231`.

## Sources

- Kubernetes blog, [Ingress NGINX Retirement: What You Need to Know](https://www.kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/) (2025-11-11)
- Kubernetes blog, [Ingress NGINX: Statement from the Kubernetes Steering and Security Response Committees](https://www.kubernetes.io/blog/2026/01/29/ingress-nginx-statement/) (2026-01-29)
- Traefik, [Migrate from Ingress NGINX Controller to Traefik](https://doc.traefik.io/traefik/migrate/nginx-to-traefik/)
- Traefik, [Kubernetes Ingress NGINX provider](https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-ingress-nginx/) and [annotation support](https://doc.traefik.io/traefik/reference/routing-configuration/kubernetes/ingress-nginx/)
- Traefik, [EntryPoints reference](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/) (readTimeout default 60s)
- RKE2, [Ingress NGINX to Traefik migration guide](https://docs.rke2.io/reference/ingress_migration)
