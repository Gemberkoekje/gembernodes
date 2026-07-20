---
source_file: "apps/spacetraders/service-api.yaml"
type: "document"
community: "SpaceTraders App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/SpaceTraders_App
---

# Service: spacetraders-api-service

## Connections
- [[ConfigMap spacetraders-config]] - `references` [INFERRED]
- [[Deployment spacetraders-api]] - `references` [EXTRACTED]
- [[Deployment spacetraders-webui]] - `shares_data_with` [INFERRED]
- [[Kustomization spacetraders]] - `references` [EXTRACTED]
- [[Namespace spacetraders]] - `references` [EXTRACTED]
- [[SpaceTraders Ingress]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/SpaceTraders_App