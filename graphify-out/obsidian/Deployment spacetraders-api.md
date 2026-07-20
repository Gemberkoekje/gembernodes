---
source_file: "apps/spacetraders/deployment-api.yaml"
type: "document"
community: "SpaceTraders App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/SpaceTraders_App
---

# Deployment: spacetraders-api

## Connections
- [[ConfigMap spacetraders-config]] - `references` [EXTRACTED]
- [[Image ghcr.iogemberkoekjespacetraders-api]] - `references` [EXTRACTED]
- [[Kustomization spacetraders]] - `references` [EXTRACTED]
- [[Namespace spacetraders]] - `references` [EXTRACTED]
- [[OnePasswordItem ghcr-login (spacetraders)]] - `references` [EXTRACTED]
- [[Service spacetraders-api-service]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/SpaceTraders_App