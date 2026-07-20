---
type: community
members: 10
---

# Persistent Storage & PostgreSQL

**Members:** 10 nodes

## Members
- [[File Server PVC (file-server-pvc-qnap)]] - document - infrastructure/pvcs/fileserver.yaml
- [[Grafana PVC (grafana-qnap)]] - document - infrastructure/pvcs/grafana.yaml
- [[Loki PVC (loki-qnap)]] - document - infrastructure/pvcs/loki.yaml
- [[Persistent Storage Layer (qnap-nfs)]] - concept - infrastructure/pvcs/kustomization.yaml
- [[PostgreSQL Data PVC (postgresql-data-qnap)]] - document - infrastructure/postgresql/postgresql-data-pvc.yaml
- [[PostgreSQL HelmRelease]] - document - infrastructure/postgresql/postgresql-release.yaml
- [[PostgreSQL Kustomization]] - document - infrastructure/postgresql/kustomization.yaml
- [[PostgreSQL LoadBalancer Service]] - document - infrastructure/postgresql/postgresql-loadbalancer.yaml
- [[Prometheus PVC (prometheus-server-qnap)]] - document - infrastructure/pvcs/prometheus.yaml
- [[Shared PVCs Kustomization]] - document - infrastructure/pvcs/kustomization.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Persistent_Storage__PostgreSQL
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Observability  Monitoring Stack]]

## Top bridge nodes
- [[Grafana PVC (grafana-qnap)]] - degree 3, connects to 1 community
- [[Prometheus PVC (prometheus-server-qnap)]] - degree 3, connects to 1 community