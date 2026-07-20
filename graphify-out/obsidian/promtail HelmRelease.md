---
source_file: "infrastructure/monitoring/promtail-release.yaml"
type: "document"
community: "Observability / Monitoring Stack"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/Observability_/_Monitoring_Stack
---

# promtail HelmRelease

## Connections
- [[Observability Stack]] - `implements` [INFERRED]
- [[grafana HelmRepository]] - `references` [EXTRACTED]
- [[grafana-loki HelmRelease]] - `shares_data_with` [EXTRACTED]
- [[monitoring Kustomization]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/Observability_/_Monitoring_Stack