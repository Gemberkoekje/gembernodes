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

Every new public route, and every existing one you rework, goes through the Gateway API. Never add
an `Ingress` object or a `nginx.ingress.kubernetes.io/*` annotation. The Ingresses still in
`ingress/` are the old way and move over one by one (phase 5 of
`docs/ingress-nginx-migration-plan.md`). The model is kluskat:

1. **A listener on the public Gateway** (`infrastructure/traefik/gateway.yaml`): copy the
   `https-kluskat` block as `https-<app>`, with the app's hostname, `certificateRefs` name
   `<app>-tls`, and the app's namespace in `allowedRoutes`. cert-manager issues the certificate
   by itself; don't add a `Certificate` or a `tls:` block anywhere else.
2. **The routes:** `ingress/<app>-route.yaml`, copied from `ingress/kluskat-route.yaml`. One
   HTTPRoute on the `http` listener redirects to HTTPS, and one on `https-<app>` sends the
   traffic to the app's Service. List the file in `ingress/kustomization.yaml`.
3. **When it replaces an Ingress,** delete that Ingress in the same change. Its old certificate
   Secret stays in the app's namespace: delete it after the new route works.

Path rewrites and redirects are HTTPRoute filters (`URLRewrite`, `RequestRedirect`). An IP
allowlist has no Gateway API equivalent: use a Traefik `Middleware`, referenced from the route
with an `ExtensionRef` filter. LAN-only `<app>.lan.gemberkoekje.nl` names are not public routes;
they stay with Caddy (`infrastructure/lan-proxy/`).
