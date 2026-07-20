---
source_file: "ingress/spacetraders-ingress.yaml"
type: "document"
community: "SpaceTraders App"
tags:
  - graphify/document
  - graphify/EXTRACTED
  - community/SpaceTraders_App
---

# SpaceTraders Ingress

## Connections
- [[ClusterIssuer letsencrypt-prod]] - `references` [EXTRACTED]
- [[Ingress Kustomization]] - `references` [EXTRACTED]
- [[Service spacetraders-api-service]] - `references` [EXTRACTED]
- [[Service spacetraders-webui-service]] - `references` [EXTRACTED]

#graphify/document #graphify/EXTRACTED #community/SpaceTraders_App