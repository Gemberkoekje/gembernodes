---
type: community
members: 14
---

# Ingress Routing & TLS

**Members:** 14 nodes

## Members
- [[AdventureEngine Ingress]] - document - ingress/adventureengine-ingress.yaml
- [[COV Website Ingress]] - document - ingress/cov-website-ingress.yaml
- [[Cluster Healthcheck Ingress]] - document - ingress/healthcheck-ingress.yaml
- [[ClusterIssuer letsencrypt-prod]] - document - configuration/certissuer.yaml
- [[Curatool Ingress]] - document - ingress/curatool-ingress.yaml
- [[EBI CS API Ingress]] - document - ingress/ebi-cs-api-ingress.yaml
- [[EBI CS Frontend Ingress]] - document - ingress/ebi-cs-frontend-ingress.yaml
- [[File Server Ingress]] - document - ingress/fileserver-ingress.yaml
- [[Grafana Ingress]] - document - ingress/grafana-ingress.yaml
- [[Hacker Minigames Ingress]] - document - ingress/hackerminigames-ingress.yaml
- [[Ingress Kustomization]] - document - ingress/kustomization.yaml
- [[STS2 Viewer Ingress]] - document - ingress/sts2viewer-ingress.yaml
- [[SpaceTraders Assets Ingress]] - document - ingress/spacetraders-assets-ingress.yaml
- [[Vortexplotboek Ingress]] - document - ingress/vortexplotboek-ingress.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Ingress_Routing__TLS
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_ArmaBot & EBI-CS Apps]]
- 2 edges to [[_COMMUNITY_STS2 Viewer & Vortexplotboek]]
- 2 edges to [[_COMMUNITY_SpaceTraders App]]
- 1 edge to [[_COMMUNITY_Adventure Engine App]]
- 1 edge to [[_COMMUNITY_AI Usage Monitor & COV Website]]
- 1 edge to [[_COMMUNITY_Clocktower Bot & Curatool]]
- 1 edge to [[_COMMUNITY_File Server App]]
- 1 edge to [[_COMMUNITY_Hacker Minigames App]]
- 1 edge to [[_COMMUNITY_Cluster Healthcheck App]]
- 1 edge to [[_COMMUNITY_Flux GitOps Cluster Root]]
- 1 edge to [[_COMMUNITY_Observability  Monitoring Stack]]

## Top bridge nodes
- [[ClusterIssuer letsencrypt-prod]] - degree 14, connects to 2 communities
- [[Ingress Kustomization]] - degree 13, connects to 1 community
- [[EBI CS Frontend Ingress]] - degree 4, connects to 1 community
- [[STS2 Viewer Ingress]] - degree 4, connects to 1 community
- [[AdventureEngine Ingress]] - degree 3, connects to 1 community