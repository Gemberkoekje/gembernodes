---
source_file: "infrastructure/monitoring/kustomization.yaml"
type: "document"
community: "Observability / Monitoring Stack"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/Observability_/_Monitoring_Stack
---

# monitoring Kustomization

## Connections
- [[grafana HelmRelease]] - `references` [EXTRACTED]
- [[grafana-alerting-provisioning ConfigMap]] - `references` [EXTRACTED]
- [[grafana-internal Ingress]] - `references` [EXTRACTED]
- [[grafana-loki HelmRelease]] - `references` [EXTRACTED]
- [[infrastructure Kustomization (aggregator)]] - `references` [EXTRACTED]
- [[prometheus HelmRelease]] - `references` [EXTRACTED]
- [[promtail HelmRelease]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/Observability_/_Monitoring_Stack