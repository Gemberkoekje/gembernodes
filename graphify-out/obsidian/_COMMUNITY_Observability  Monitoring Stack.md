---
type: community
members: 10
---

# Observability / Monitoring Stack

**Members:** 10 nodes

## Members
- [[Observability Stack]] - concept - infrastructure/monitoring/kustomization.yaml
- [[grafana HelmRelease]] - document - infrastructure/monitoring/grafana-release.yaml
- [[grafana HelmRepository]] - document - repos/grafana-repo.yaml
- [[grafana-alerting-provisioning ConfigMap]] - document - infrastructure/monitoring/grafana-alerting-provisioning.yaml
- [[grafana-internal Ingress]] - document - infrastructure/monitoring/grafana-internal-ingress.yaml
- [[grafana-loki HelmRelease]] - document - infrastructure/monitoring/loki-release.yaml
- [[kube-state-metrics HelmRelease]] - document - infrastructure/monitoring/kube-state-metrics-release.yaml
- [[monitoring Kustomization]] - document - infrastructure/monitoring/kustomization.yaml
- [[prometheus HelmRelease]] - document - infrastructure/monitoring/prometheus-release.yaml
- [[promtail HelmRelease]] - document - infrastructure/monitoring/promtail-release.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Observability_/_Monitoring_Stack
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Infrastructure Helm Releases & Sources]]
- 2 edges to [[_COMMUNITY_Persistent Storage & PostgreSQL]]
- 1 edge to [[_COMMUNITY_Ingress Routing & TLS]]

## Top bridge nodes
- [[grafana HelmRelease]] - degree 10, connects to 3 communities
- [[prometheus HelmRelease]] - degree 6, connects to 2 communities
- [[monitoring Kustomization]] - degree 7, connects to 1 community
- [[grafana HelmRepository]] - degree 5, connects to 1 community