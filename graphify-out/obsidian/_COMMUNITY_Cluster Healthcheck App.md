---
type: community
members: 6
---

# Cluster Healthcheck App

**Members:** 6 nodes

## Members
- [[ConfigMap cluster-healthcheck-page]] - document - apps/healthcheck/deployment.yaml
- [[Deployment cluster-healthcheck (caddy)]] - document - apps/healthcheck/deployment.yaml
- [[Image caddy2.10.2-alpine]] - document - apps/healthcheck/deployment.yaml
- [[Kustomization healthcheck]] - document - apps/healthcheck/kustomization.yaml
- [[Namespace cluster-healthcheck]] - document - apps/healthcheck/deployment.yaml
- [[Service cluster-healthcheck]] - document - apps/healthcheck/service.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_Healthcheck_App
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_ArmaBot & EBI-CS Apps]]
- 1 edge to [[_COMMUNITY_Ingress Routing & TLS]]

## Top bridge nodes
- [[Service cluster-healthcheck]] - degree 4, connects to 1 community
- [[Kustomization healthcheck]] - degree 3, connects to 1 community