---
type: community
members: 11
---

# SpaceTraders App

**Members:** 11 nodes

## Members
- [[ConfigMap spacetraders-config]] - document - apps/spacetraders/configmap.yaml
- [[Deployment spacetraders-api]] - document - apps/spacetraders/deployment-api.yaml
- [[Deployment spacetraders-webui]] - document - apps/spacetraders/deployment-webui.yaml
- [[Image ghcr.iogemberkoekjespacetraders-api]] - document - apps/spacetraders/deployment-api.yaml
- [[Image ghcr.iogemberkoekjespacetraders-webui]] - document - apps/spacetraders/deployment-webui.yaml
- [[Kustomization spacetraders]] - document - apps/spacetraders/kustomization.yaml
- [[Namespace spacetraders]] - document - apps/spacetraders/deployment-api.yaml
- [[OnePasswordItem ghcr-login (spacetraders)]] - document - apps/spacetraders/ghcr-login.yaml
- [[Service spacetraders-api-service]] - document - apps/spacetraders/service-api.yaml
- [[Service spacetraders-webui-service]] - document - apps/spacetraders/service-webui.yaml
- [[SpaceTraders Ingress]] - document - ingress/spacetraders-ingress.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/SpaceTraders_App
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Ingress Routing & TLS]]
- 1 edge to [[_COMMUNITY_Hacker Minigames App]]

## Top bridge nodes
- [[OnePasswordItem ghcr-login (spacetraders)]] - degree 5, connects to 1 community
- [[SpaceTraders Ingress]] - degree 4, connects to 1 community