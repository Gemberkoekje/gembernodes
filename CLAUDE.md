## Start here

[MAP.md](MAP.md) is the map of this repository: which folder holds what, the IP addresses and
hostnames, the shared services (PostgreSQL, 1Password, storage, certificates) and which app depends
on what. Read it first to find your way, then open the manifests it points at. The manifests are
the source of truth; MAP.md only points at them.

[NOTES.md](NOTES.md) is the dated log of changes: why, gotchas, what was tested. Read the latest
entries about a subsystem before changing it, and end each change with an entry of your own, like
the existing ones.

## Keep MAP.md current

Check every change against MAP.md before committing it:

- **Update MAP.md in the same commit** when the change adds, removes, renames or moves anything it
  describes: an app, namespace, folder or Flux Kustomization; an IP address, hostname, port or
  route; a volume or StorageClass; a shared service, or which apps use it; a script or CI check; how
  two pieces connect.
- **Leave it alone** when the picture stays the same: an image bump, a resource limit, a setting
  inside one app.
- **Found MAP.md wrong** about something you didn't change? Fix it in the same change and say so in
  the pull request.
- Keep it short and current-state only: no history, no image tags, no numbers that drift by
  themselves. History goes in NOTES.md.

## Public routes: Gateway API, not Ingress

Every public route goes through the Gateway API; there are no `Ingress` objects left. Never add
one, nor a `nginx.ingress.kubernetes.io/*` annotation. The model is kluskat:

1. **A listener on the public Gateway** (`infrastructure/traefik/gateway.yaml`): copy the
   `https-kluskat` block as `https-<app>`, with the app's hostname, `certificateRefs` name
   `<app>-tls`, and the app's namespace in `allowedRoutes`. cert-manager issues the certificate
   by itself; don't add a `Certificate` or a `tls:` block anywhere else.
2. **The routes:** `ingress/<app>-route.yaml`, copied from `ingress/kluskat-route.yaml`. One
   HTTPRoute on the `http` listener redirects to HTTPS (308), and one on `https-<app>` sends the
   traffic to the app's Service. List the file in `ingress/kustomization.yaml`.
3. **A path on the bare `gemberkoekje.nl`** as well: a third HTTPRoute on the shared
   `https-gemberkoekje-nl` listener, with a `PathPrefix` match (see
   `ingress/adventureengine-route.yaml`), and the app's namespace added to that listener's
   `allowedRoutes` list. The bare domain's port-80 redirect is `ingress/gemberkoekje-nl-route.yaml`.

Path rewrites and redirects are HTTPRoute filters (`URLRewrite`, `RequestRedirect`; see
`ingress/ebi-cs-frontend-route.yaml` and `ingress/plotboek-generator-route.yaml`). An IP allowlist
has no Gateway API equivalent: use a Traefik `Middleware`, referenced from the route with an
`ExtensionRef` filter.

A **LAN-only path by IP** (like `http://192.168.1.231/grafana`) is an HTTPRoute without a hostname
on the `http` listener, behind a `lan-only` Middleware (see `ingress/spacetraders-route.yaml`).
Traefik ranks a longer path above a hostname match, so such a path wins on every hostname's port 80:
keep these paths specific, and always put the allowlist on them. LAN-only
`<app>.lan.gemberkoekje.nl` names are not public routes; they stay with Caddy
(`infrastructure/lan-proxy/`).
