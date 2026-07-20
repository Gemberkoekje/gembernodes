---
type: community
members: 6
---

# File Server App

**Members:** 6 nodes

## Members
- [[Deployment file-server (filebrowser)]] - document - apps/fileserver/deployment.yaml
- [[Image busybox1.36 (init-permissions)]] - document - apps/fileserver/deployment.yaml
- [[Image filebrowserfilebrowserlatest]] - document - apps/fileserver/deployment.yaml
- [[Kustomization fileserver]] - document - apps/fileserver/kustomization.yaml
- [[Namespace file-server]] - document - apps/fileserver/deployment.yaml
- [[Service file-server (ClusterIP)]] - document - apps/fileserver/service.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/File_Server_App
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_ArmaBot & EBI-CS Apps]]
- 1 edge to [[_COMMUNITY_Ingress Routing & TLS]]

## Top bridge nodes
- [[Service file-server (ClusterIP)]] - degree 4, connects to 1 community
- [[Kustomization fileserver]] - degree 3, connects to 1 community