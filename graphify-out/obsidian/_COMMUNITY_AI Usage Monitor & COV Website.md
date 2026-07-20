---
type: community
members: 15
---

# AI Usage Monitor & COV Website

**Members:** 15 nodes

## Members
- [[AiUsageMonitor Deployment Notes]] - document - apps/aiusagemonitor/README.md
- [[CronJob aiusagemonitor]] - document - apps/aiusagemonitor/cronjob.yaml
- [[Deployment cov-website]] - document - apps/cov-website/deployment.yaml
- [[Image ghcr.iogemberkoekjeaiusagemonitor]] - document - apps/aiusagemonitor/cronjob.yaml
- [[Image ghcr.iogemberkoekjecov-website]] - document - apps/cov-website/deployment.yaml
- [[Namespace aiusagemonitor]] - document - apps/aiusagemonitor/cronjob.yaml
- [[Namespace cov-website]] - document - apps/cov-website/deployment.yaml
- [[OnePasswordItem ghcr-login (aiusagemonitor)]] - document - apps/aiusagemonitor/ghcr-login.yaml
- [[Secret aiusagemonitor-secrets]] - document - apps/aiusagemonitor/cronjob.yaml
- [[Secret mail-secret (aiusagemonitor)]] - document - apps/aiusagemonitor/cronjob.yaml
- [[Secret mail-secret (cov-website)]] - document - apps/cov-website/deployment.yaml
- [[Service cov-website-service]] - document - apps/cov-website/service.yaml
- [[ServiceAccount default (aiusagemonitor)]] - document - apps/aiusagemonitor/serviceaccount.yaml
- [[aiusagemonitor Kustomization]] - document - apps/aiusagemonitor/kustomization.yaml
- [[cov-website Kustomization]] - document - apps/cov-website/kustomization.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/AI_Usage_Monitor__COV_Website
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Clocktower Bot & Curatool]]
- 1 edge to [[_COMMUNITY_ArmaBot & EBI-CS Apps]]
- 1 edge to [[_COMMUNITY_Ingress Routing & TLS]]

## Top bridge nodes
- [[OnePasswordItem ghcr-login (aiusagemonitor)]] - degree 4, connects to 1 community
- [[cov-website Kustomization]] - degree 4, connects to 1 community
- [[Service cov-website-service]] - degree 3, connects to 1 community