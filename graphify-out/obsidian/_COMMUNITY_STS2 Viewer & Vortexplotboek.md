---
type: community
members: 8
---

# STS2 Viewer & Vortexplotboek

**Members:** 8 nodes

## Members
- [[CronJob sync-google-drive]] - document - apps/vortexplotboek/sync-cronjob.yaml
- [[Deployment sts2viewer]] - document - apps/sts2viewer/deployment.yaml
- [[Deployment vortexplotboek]] - document - apps/vortexplotboek/deployment.yaml
- [[Kustomize overlay sts2viewer]] - document - apps/sts2viewer/kustomization.yaml
- [[Kustomize overlay vortexplotboek]] - document - apps/vortexplotboek/kustomization.yaml
- [[OnePasswordItem ghcr-login]] - document - apps/sts2viewer/ghcr-login.yaml
- [[Service sts2viewer-service]] - document - apps/sts2viewer/service.yaml
- [[Service vortexplotboek-service]] - document - apps/vortexplotboek/vortexplotboek-service.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/STS2_Viewer__Vortexplotboek
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Flux GitOps Cluster Root]]
- 2 edges to [[_COMMUNITY_Ingress Routing & TLS]]

## Top bridge nodes
- [[Kustomize overlay sts2viewer]] - degree 5, connects to 1 community
- [[Kustomize overlay vortexplotboek]] - degree 5, connects to 1 community
- [[Service vortexplotboek-service]] - degree 4, connects to 1 community
- [[Service sts2viewer-service]] - degree 3, connects to 1 community