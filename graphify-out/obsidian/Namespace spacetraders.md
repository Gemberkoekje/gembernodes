---
source_file: "apps/spacetraders/deployment-api.yaml"
type: "document"
community: "SpaceTraders App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/SpaceTraders_App
---

# Namespace: spacetraders

## Connections
- [[ConfigMap spacetraders-config]] - `references` [EXTRACTED]
- [[Deployment spacetraders-api]] - `references` [EXTRACTED]
- [[Deployment spacetraders-webui]] - `references` [EXTRACTED]
- [[OnePasswordItem ghcr-login (spacetraders)]] - `references` [EXTRACTED]
- [[Service spacetraders-api-service]] - `references` [EXTRACTED]
- [[Service spacetraders-webui-service]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/SpaceTraders_App