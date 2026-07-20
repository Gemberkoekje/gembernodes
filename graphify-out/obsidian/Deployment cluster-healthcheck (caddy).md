---
source_file: "apps/healthcheck/deployment.yaml"
type: "document"
community: "Cluster Healthcheck App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/Cluster_Healthcheck_App
---

# Deployment: cluster-healthcheck (caddy)

## Connections
- [[ConfigMap cluster-healthcheck-page]] - `references` [EXTRACTED]
- [[Image caddy2.10.2-alpine]] - `references` [EXTRACTED]
- [[Kustomization healthcheck]] - `references` [EXTRACTED]
- [[Namespace cluster-healthcheck]] - `references` [EXTRACTED]
- [[Service cluster-healthcheck]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/Cluster_Healthcheck_App