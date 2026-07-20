---
source_file: "apps/spacetraders/configmap.yaml"
type: "document"
community: "SpaceTraders App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/SpaceTraders_App
---

# ConfigMap: spacetraders-config

## Connections
- [[Deployment spacetraders-api]] - `references` [EXTRACTED]
- [[Deployment spacetraders-webui]] - `references` [EXTRACTED]
- [[Kustomization spacetraders]] - `references` [EXTRACTED]
- [[Namespace spacetraders]] - `references` [EXTRACTED]
- [[Service spacetraders-api-service]] - `references` [INFERRED]

#graphify/document #graphify/EXTRACTED #community/SpaceTraders_App