---
source_file: "infrastructure/monitoring/prometheus-release.yaml"
type: "document"
community: "Observability / Monitoring Stack"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/Observability_/_Monitoring_Stack
---

# prometheus HelmRelease

## Connections
- [[Observability Stack]] - `implements` [INFERRED]
- [[Prometheus PVC (prometheus-server-qnap)]] - `references` [INFERRED]
- [[grafana HelmRelease]] - `references` [EXTRACTED]
- [[kube-state-metrics HelmRelease]] - `shares_data_with` [INFERRED]
- [[monitoring Kustomization]] - `references` [EXTRACTED]
- [[qnap-nfs StorageClass]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/Observability_/_Monitoring_Stack