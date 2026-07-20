---
type: community
members: 27
---

# Infrastructure Helm Releases & Sources

**Members:** 27 nodes

## Members
- [[Helm chart sources]] - concept - repos/kustomization.yaml
- [[Repos Kustomization (aggregator)]] - document - repos/kustomization.yaml
- [[cert-manager HelmRelease]] - document - infrastructure/certmanager/certmanager-helmrelease.yaml
- [[certmanager Kustomization]] - document - infrastructure/certmanager/kustomization.yaml
- [[connect (1Password Connect) HelmRelease]] - document - infrastructure/externalsecrets/connect.yaml
- [[csi-driver-nfs HelmRelease]] - document - infrastructure/nfs-provisioner/nfs-csi-release.yaml
- [[csi-driver-nfs HelmRepository]] - document - repos/csi-driver-nfs-repo.yaml
- [[externalsecrets Kustomization]] - document - infrastructure/externalsecrets/kustomization.yaml
- [[infrastructure Kustomization (aggregator)]] - document - infrastructure/kustomization.yaml
- [[ingress-nginx-charts HelmRepository]] - document - repos/nginx-repo.yaml
- [[jetstack HelmRepository (cert-manager charts)]] - document - repos/certmanager-repo.yaml
- [[kured HelmRelease]] - document - infrastructure/kured/kured-release.yaml
- [[kured HelmRepository]] - document - repos/kured-repo.yaml
- [[kured Kustomization]] - document - infrastructure/kured/kustomization.yaml
- [[metallb HelmRelease]] - document - infrastructure/metallb/metallb-release.yaml
- [[metallb HelmRepository]] - document - repos/metallb-repo.yaml
- [[metallb Kustomization]] - document - infrastructure/metallb/kustomization.yaml
- [[nfs-provisioner Kustomization]] - document - infrastructure/nfs-provisioner/kustomization.yaml
- [[nginx Kustomization]] - document - infrastructure/nginx/kustomization.yaml
- [[nginx-ingress-public HelmRelease]] - document - infrastructure/nginx/nginx-release.yaml
- [[onepassword HelmRepository (1Password Connect charts)]] - document - repos/onepassword-repo.yaml
- [[postgresql-backup CronJob]] - document - infrastructure/postgresql-backup/backup-cronjob.yaml
- [[postgresql-backup Kustomization]] - document - infrastructure/postgresql-backup/kustomization.yaml
- [[postgresql-backup-pvc-qnap PVC]] - document - infrastructure/postgresql-backup/backup-pvc.yaml
- [[postgresql-chart OCIRepository (Bitnami)]] - document - repos/postgresql-repo.yaml
- [[prometheus-community HelmRepository]] - document - repos/prometheus-repo.yaml
- [[qnap-nfs StorageClass]] - document - infrastructure/nfs-provisioner/qnap-nfs-storageclass.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Infrastructure_Helm_Releases__Sources
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Observability  Monitoring Stack]]

## Top bridge nodes
- [[Repos Kustomization (aggregator)]] - degree 10, connects to 1 community
- [[infrastructure Kustomization (aggregator)]] - degree 8, connects to 1 community
- [[qnap-nfs StorageClass]] - degree 5, connects to 1 community
- [[prometheus-community HelmRepository]] - degree 2, connects to 1 community