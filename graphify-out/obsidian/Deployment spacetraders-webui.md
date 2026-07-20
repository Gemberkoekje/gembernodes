---
source_file: "apps/spacetraders/deployment-webui.yaml"
type: "document"
community: "SpaceTraders App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/SpaceTraders_App
---

# Deployment: spacetraders-webui

## Connections
- [[ConfigMap spacetraders-config]] - `references` [EXTRACTED]
- [[Image ghcr.iogemberkoekjespacetraders-webui]] - `references` [EXTRACTED]
- [[Kustomization spacetraders]] - `references` [EXTRACTED]
- [[Namespace spacetraders]] - `references` [EXTRACTED]
- [[OnePasswordItem ghcr-login (spacetraders)]] - `references` [EXTRACTED]
- [[Service spacetraders-api-service]] - `shares_data_with` [INFERRED]
- [[Service spacetraders-webui-service]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/SpaceTraders_App