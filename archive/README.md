# Archive

Manifests taken out of the cluster but kept just in case. Nothing here is applied: no Flux
Kustomization points at `archive/`, `scripts/validate.py` doesn't treat these files as manifests,
and `scripts/check_images.py` doesn't look up their images.

Each entry mirrors the repository's own layout. To restore one, copy its files back to the same
paths and make sure the `kustomization.yaml` files list them.

| Entry | Archived | What it is |
|---|---|---|
| `vortexplotboek/` | 2026-11-12 | The app as it ran here before moving to the-vortex cluster (`https://plotboek.the-vortex.nl`) on 2026-10-23. It holds the Deployment (left at `replicas: 0`), the sync CronJob, the 1Password item references and the `kustomization.yaml`, all as of 2026-11-02, when commit 0910ef7 removed them. It also holds the Ingress from before it became a redirect. The redirect is still live (`apps/vortexplotboek/`, `ingress/vortexplotboek-ingress.yaml`); restoring the archived Ingress replaces it. |
