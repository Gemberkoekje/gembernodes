---
type: community
members: 15
---

# Flux GitOps Cluster Root

**Members:** 15 nodes

## Members
- [[Flux Controllers Bootstrap (gotk-components)]] - document - clusters/home/flux-system/gotk-components.yaml
- [[Flux Kustomization apps]] - document - clusters/home/apps-kustomization.yaml
- [[Flux Kustomization configuration]] - document - clusters/home/configuration-kustomization.yaml
- [[Flux Kustomization flux-system (root sync)]] - document - clusters/home/flux-system/gotk-sync.yaml
- [[Flux Kustomization infrastructure]] - document - clusters/home/infrastructure-kustomization.yaml
- [[Flux Kustomization ingress]] - document - clusters/home/ingress-kustomization.yaml
- [[Flux Kustomization namespaces]] - document - clusters/home/namespaces-kustomization.yaml
- [[Flux Kustomization repos]] - document - clusters/home/repos-kustomization.yaml
- [[Flux Kustomization system-upgrade-plans]] - document - clusters/home/system-upgrade-plans-kustomization.yaml
- [[GitOps reconciliation order]] - concept - clusters/home/flux-system/gotk-sync.yaml
- [[GitRepository flux-system (root source)]] - document - clusters/home/flux-system/gotk-sync.yaml
- [[Kustomize overlay configuration]] - document - configuration/kustomization.yaml
- [[Kustomize overlay flux-system]] - document - clusters/home/flux-system/kustomization.yaml
- [[MetalLB IPAddressPool first-pool]] - document - configuration/ipaddresspool.yaml
- [[MetalLB L2Advertisement l2lbadv]] - document - configuration/ipaddresspool.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Flux_GitOps_Cluster_Root
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_STS2 Viewer & Vortexplotboek]]
- 1 edge to [[_COMMUNITY_Ingress Routing & TLS]]

## Top bridge nodes
- [[Flux Kustomization apps]] - degree 6, connects to 1 community
- [[Kustomize overlay configuration]] - degree 4, connects to 1 community