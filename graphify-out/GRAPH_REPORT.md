# Graph Report - .  (2026-07-20)

## Corpus Check
- 154 files · ~53,403 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 195 nodes · 318 edges · 20 communities (17 shown, 3 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 32 edges (avg confidence: 0.84)
- Token cost: 450,980 input · 0 output

## Community Hubs (Navigation)
- Infrastructure Helm Releases & Sources
- Per-App Namespaces
- ArmaBot & EBI-CS Apps
- AI Usage Monitor & COV Website
- Flux GitOps Cluster Root
- Clocktower Bot & Curatool
- Ingress Routing & TLS
- SpaceTraders App
- Persistent Storage & PostgreSQL
- Observability / Monitoring Stack
- STS2 Viewer & Vortexplotboek
- Adventure Engine App
- File Server App
- Hacker Minigames App
- Cluster Healthcheck App
- Dockhand App
- k3s System Upgrade Plans
- Graphify Knowledge Graph
- System Upgrade Controller
- HTTP Routing / TLS Concept

## God Nodes (most connected - your core abstractions)
1. `Namespaces Kustomization (aggregator)` - 19 edges
2. `ClusterIssuer: letsencrypt-prod` - 14 edges
3. `Ingress Kustomization` - 13 edges
4. `Parent Kustomization: apps (aggregator)` - 11 edges
5. `Flux Kustomization: flux-system (root sync)` - 10 edges
6. `grafana HelmRelease` - 10 edges
7. `Repos Kustomization (aggregator)` - 10 edges
8. `GitRepository: flux-system (root source)` - 9 edges
9. `infrastructure Kustomization (aggregator)` - 8 edges
10. `CronJob aiusagemonitor` - 7 edges

## Surprising Connections (you probably didn't know these)
- `Flux Kustomization: apps` --references--> `Kustomize overlay: sts2viewer`  [INFERRED]
  clusters/home/apps-kustomization.yaml → apps/sts2viewer/kustomization.yaml
- `Flux Kustomization: apps` --references--> `Kustomize overlay: vortexplotboek`  [INFERRED]
  clusters/home/apps-kustomization.yaml → apps/vortexplotboek/kustomization.yaml
- `Grafana Ingress` --references--> `grafana HelmRelease`  [INFERRED]
  ingress/grafana-ingress.yaml → infrastructure/monitoring/grafana-release.yaml
- `grafana HelmRepository` --semantically_similar_to--> `prometheus-community HelmRepository`  [INFERRED] [semantically similar]
  repos/grafana-repo.yaml → repos/prometheus-repo.yaml
- `AdventureEngine Ingress` --references--> `Service adventureengine-service`  [EXTRACTED]
  ingress/adventureengine-ingress.yaml → apps/adventureengine/service.yaml

## Hyperedges (group relationships)
- **adventureengine app deployment stack** — apps_adventureengine_kustomization, apps_adventureengine_deployment_adventureengine, apps_adventureengine_service_adventureengine_service, apps_adventureengine_deployment_adventureengine_secrets [EXTRACTED 1.00]
- **aiusagemonitor cronjob deployment stack** — apps_aiusagemonitor_kustomization, apps_aiusagemonitor_cronjob_aiusagemonitor, apps_aiusagemonitor_serviceaccount_default, apps_aiusagemonitor_ghcr_login_ghcr_login, apps_aiusagemonitor_cronjob_aiusagemonitor_secrets, apps_aiusagemonitor_cronjob_mail_secret [EXTRACTED 1.00]
- **curatool web app deployment stack** — apps_curatool_kustomization, apps_curatool_web_deployment_curatool, apps_curatool_web_service_curatool, apps_curatool_web_configmap_curatool_web_config, apps_curatool_ghcr_login_ghcr_login, apps_curatool_web_deployment_curatool_secrets [EXTRACTED 1.00]
- **SpaceTraders app: api + webui deployments, their services, and shared config** — apps_spacetraders_configmap_spacetraders_config, apps_spacetraders_deployment_api_spacetraders_api, apps_spacetraders_deployment_webui_spacetraders_webui, apps_spacetraders_service_api_spacetraders_api_service, apps_spacetraders_service_webui_spacetraders_webui_service [EXTRACTED 1.00]
- **EBI-CS app: api + frontend deployments and their services in namespace ebi-cs-api** — apps_ebi_cs_api_deployment_ebi_cs_api, apps_ebi_cs_api_ebi_cs_api_service_ebi_cs_api_service, apps_ebi_cs_frontend_deployment_ebi_cs_frontend, apps_ebi_cs_frontend_service_ebi_cs_frontend_service [INFERRED 0.85]
- **Cluster-root Flux reconciliation topology (dependsOn ordering)** — clusters_home_namespaces_kustomization_namespaces, clusters_home_repos_kustomization_repos, clusters_home_infrastructure_kustomization_infrastructure, clusters_home_apps_kustomization_apps, clusters_home_configuration_kustomization_configuration, clusters_home_system_upgrade_plans_kustomization_system_upgrade_plans, clusters_home_ingress_kustomization_ingress [INFERRED 0.85]
- **Flux GitOps bootstrap (source + root sync + controllers)** — clusters_home_flux_system_gotk_sync_flux_system_gitrepository, clusters_home_flux_system_gotk_sync_flux_system, clusters_home_flux_system_gotk_components_bootstrap, clusters_home_flux_system_kustomization_overlay [INFERRED 0.85]
- **vortexplotboek app deployment stack** — apps_vortexplotboek_deployment_vortexplotboek, apps_vortexplotboek_vortexplotboek_service_vortexplotboek_service, apps_vortexplotboek_sync_cronjob_sync_google_drive, apps_vortexplotboek_kustomization_overlay [INFERRED 0.85]
- **Observability Stack** — infrastructure_monitoring_grafana_release_grafana, infrastructure_monitoring_prometheus_release_prometheus, infrastructure_monitoring_loki_release_grafana_loki, infrastructure_monitoring_promtail_release_promtail, infrastructure_monitoring_kube_state_metrics_release_kube_state_metrics [INFERRED 0.85]
- **Log Aggregation Pipeline** — infrastructure_monitoring_promtail_release_promtail, infrastructure_monitoring_loki_release_grafana_loki, infrastructure_monitoring_grafana_release_grafana [INFERRED 0.85]
- **QNAP NFS Storage Consumers** — infrastructure_nfs_provisioner_qnap_nfs_storageclass_qnap_nfs, infrastructure_monitoring_prometheus_release_prometheus, infrastructure_monitoring_grafana_release_grafana, infrastructure_postgresql_backup_backup_pvc_postgresql_backup_pvc_qnap [INFERRED 0.75]
- **Monitoring stack persistent volume claims** — infrastructure_pvcs_grafana_grafana_qnap, infrastructure_pvcs_loki_loki_qnap, infrastructure_pvcs_prometheus_prometheus_server_qnap [INFERRED 0.75]
- **Ingresses TLS-terminated by letsencrypt-prod ClusterIssuer** — configuration_certissuer_letsencrypt_prod, ingress_adventureengine_ingress_adventureengine_ingress, ingress_cov_website_ingress_cov_website_ingress, ingress_curatool_ingress_curatool_ingress, ingress_ebi_cs_api_ingress_ebi_cs_api_ingress, ingress_ebi_cs_frontend_ingress_ebi_cs_frontend_ingress, ingress_fileserver_ingress_file_server_ingress, ingress_grafana_ingress_grafana, ingress_hackerminigames_ingress_hackerminigames_ingress, ingress_healthcheck_ingress_healthcheck_ingress, ingress_spacetraders_ingress_spacetraders_ingress, ingress_spacetraders_assets_ingress_spacetraders_assets_ingress, ingress_sts2viewer_ingress_sts2viewer_ingress, ingress_vortexplotboek_ingress_vortexplotboek_ingress [EXTRACTED 1.00]
- **Ingresses reusing the ebi-cs-api-tls TLS secret** — ingress_adventureengine_ingress_adventureengine_ingress, ingress_cov_website_ingress_cov_website_ingress, ingress_curatool_ingress_curatool_ingress, ingress_ebi_cs_api_ingress_ebi_cs_api_ingress, ingress_fileserver_ingress_file_server_ingress, ingress_hackerminigames_ingress_hackerminigames_ingress, ingress_healthcheck_ingress_healthcheck_ingress, ingress_spacetraders_ingress_spacetraders_ingress, ingress_spacetraders_assets_ingress_spacetraders_assets_ingress, ingress_sts2viewer_ingress_sts2viewer_ingress, ingress_vortexplotboek_ingress_vortexplotboek_ingress [EXTRACTED 1.00]
- **Ingress manifests aggregated by the ingress Kustomization** — ingress_kustomization_kustomization, ingress_adventureengine_ingress_adventureengine_ingress, ingress_ebi_cs_api_ingress_ebi_cs_api_ingress, ingress_ebi_cs_frontend_ingress_ebi_cs_frontend_ingress, ingress_vortexplotboek_ingress_vortexplotboek_ingress, ingress_cov_website_ingress_cov_website_ingress, ingress_healthcheck_ingress_healthcheck_ingress, ingress_fileserver_ingress_file_server_ingress, ingress_sts2viewer_ingress_sts2viewer_ingress, ingress_spacetraders_ingress_spacetraders_ingress, ingress_spacetraders_assets_ingress_spacetraders_assets_ingress, ingress_curatool_ingress_curatool_ingress, ingress_hackerminigames_ingress_hackerminigames_ingress [EXTRACTED 1.00]
- **Helm chart sources feeding infrastructure HelmReleases** — repos_onepassword_repo_onepassword, repos_grafana_repo_grafana, repos_metallb_repo_metallb, repos_postgresql_repo_postgresql, repos_prometheus_repo_prometheus, repos_nginx_repo_nginx, repos_certmanager_repo_certmanager, repos_kured_repo_kured, repos_csi_driver_nfs_repo_csi_driver_nfs [INFERRED 0.75]
- **Per-app Namespaces enforcing pod-security baseline isolation** — namespaces_curatool_namespace_curatool, namespaces_dockhand_namespace_dockhand, namespaces_hackerminigames_namespace_hackerminigames, namespaces_spacetraders_namespace_spacetraders, namespaces_armabotcs_namespace_armabotcs [INFERRED 0.75]

## Communities (20 total, 3 thin omitted)

### Community 0 - "Infrastructure Helm Releases & Sources"
Cohesion: 0.09
Nodes (27): Helm chart sources, cert-manager HelmRelease, certmanager Kustomization, connect (1Password Connect) HelmRelease, externalsecrets Kustomization, kured HelmRelease, kured Kustomization, infrastructure Kustomization (aggregator) (+19 more)

### Community 1 - "Per-App Namespaces"
Cohesion: 0.10
Nodes (20): Namespace isolation per app, adventureengine Namespace, aiusagemonitor Namespace, armabotcs Namespace, bot-on-the-clocktower Namespace, cluster-healthcheck Namespace, cov-website Namespace, curatool Namespace (+12 more)

### Community 2 - "ArmaBot & EBI-CS Apps"
Cohesion: 0.18
Nodes (16): Deployment armabotcs, Secret discord-secret, Image ghcr.io/gemberkoekje/armabotcs, Secret postgress-secret, armabotcs Kustomization, Deployment: ebi-cs-api, Image: ghcr.io/eosfrontier/ebi-cs-api:1.0.0-27, Service: ebi-cs-api-service (NodePort) (+8 more)

### Community 3 - "AI Usage Monitor & COV Website"
Cohesion: 0.24
Nodes (15): CronJob aiusagemonitor, Secret aiusagemonitor-secrets, Image ghcr.io/gemberkoekje/aiusagemonitor, Secret mail-secret (aiusagemonitor), OnePasswordItem ghcr-login (aiusagemonitor), aiusagemonitor Kustomization, AiUsageMonitor Deployment Notes, ServiceAccount default (aiusagemonitor) (+7 more)

### Community 4 - "Flux GitOps Cluster Root"
Cohesion: 0.29
Nodes (15): Flux Kustomization: apps, Flux Kustomization: configuration, Flux Controllers Bootstrap (gotk-components), Flux Kustomization: flux-system (root sync), GitRepository: flux-system (root source), Kustomize overlay: flux-system, Flux Kustomization: infrastructure, Flux Kustomization: ingress (+7 more)

### Community 5 - "Clocktower Bot & Curatool"
Cohesion: 0.22
Nodes (14): Deployment bot-on-the-clocktower, Secret bot-on-the-clocktower-secrets, Image ghcr.io/gemberkoekje/bot-on-the-clocktower, OnePasswordItem ghcr-login (bot-on-the-clocktower), bot-on-the-clocktower Kustomization, OnePasswordItem ghcr-login (curatool), curatool Kustomization, ConfigMap curatool-web-config (+6 more)

### Community 6 - "Ingress Routing & TLS"
Cohesion: 0.27
Nodes (14): ClusterIssuer: letsencrypt-prod, AdventureEngine Ingress, COV Website Ingress, Curatool Ingress, EBI CS API Ingress, EBI CS Frontend Ingress, File Server Ingress, Grafana Ingress (+6 more)

### Community 7 - "SpaceTraders App"
Cohesion: 0.44
Nodes (11): ConfigMap: spacetraders-config, Image: ghcr.io/gemberkoekje/spacetraders-api, Deployment: spacetraders-api, Image: ghcr.io/gemberkoekje/spacetraders-webui, Deployment: spacetraders-webui, OnePasswordItem: ghcr-login (spacetraders), Kustomization: spacetraders, Service: spacetraders-api-service (+3 more)

### Community 8 - "Persistent Storage & PostgreSQL"
Cohesion: 0.31
Nodes (10): Persistent Storage Layer (qnap-nfs), PostgreSQL Kustomization, PostgreSQL Data PVC (postgresql-data-qnap), PostgreSQL LoadBalancer Service, PostgreSQL HelmRelease, File Server PVC (file-server-pvc-qnap), Grafana PVC (grafana-qnap), Shared PVCs Kustomization (+2 more)

### Community 9 - "Observability / Monitoring Stack"
Cohesion: 0.47
Nodes (10): grafana-alerting-provisioning ConfigMap, grafana-internal Ingress, grafana HelmRelease, kube-state-metrics HelmRelease, monitoring Kustomization, grafana-loki HelmRelease, prometheus HelmRelease, promtail HelmRelease (+2 more)

### Community 10 - "STS2 Viewer & Vortexplotboek"
Cohesion: 0.43
Nodes (8): Deployment: sts2viewer, OnePasswordItem: ghcr-login, Kustomize overlay: sts2viewer, Service: sts2viewer-service, Deployment: vortexplotboek, Kustomize overlay: vortexplotboek, CronJob: sync-google-drive, Service: vortexplotboek-service

### Community 11 - "Adventure Engine App"
Cohesion: 0.53
Nodes (6): Deployment adventureengine, Secret adventureengine-secrets, Image ghcr.io/gemberkoekje/adventureengine, adventureengine Kustomization, Service adventureengine-service, Namespace adventureengine

### Community 12 - "File Server App"
Cohesion: 0.47
Nodes (6): Deployment: file-server (filebrowser), Image: busybox:1.36 (init-permissions), Image: filebrowser/filebrowser:latest, Kustomization: fileserver, Service: file-server (ClusterIP), Namespace: file-server

### Community 13 - "Hacker Minigames App"
Cohesion: 0.60
Nodes (6): Deployment: hackerminigames, Image: ghcr.io/gemberkoekje/hackerminigames, OnePasswordItem: ghcr-login (hackerminigames), Kustomization: hackerminigames, Service: hackerminigames-service (ClusterIP), Namespace: hackerminigames

### Community 14 - "Cluster Healthcheck App"
Cohesion: 0.53
Nodes (6): Deployment: cluster-healthcheck (caddy), ConfigMap: cluster-healthcheck-page, Image: caddy:2.10.2-alpine, Kustomization: healthcheck, Service: cluster-healthcheck, Namespace: cluster-healthcheck

### Community 15 - "Dockhand App"
Cohesion: 0.60
Nodes (5): Deployment: dockhand, Image: fnsys/dockhand:v1.0.34, Kustomization: dockhand, Service: dockhand (NodePort), Namespace: dockhand

### Community 16 - "k3s System Upgrade Plans"
Cohesion: 1.00
Nodes (3): k3s Agent Upgrade Plan, k3s Server Upgrade Plan, System Upgrade Plans Kustomization

## Knowledge Gaps
- **47 isolated node(s):** `Graphify Knowledge Graph`, `Image ghcr.io/gemberkoekje/adventureengine`, `Image ghcr.io/gemberkoekje/armabotcs`, `Namespace armabotcs`, `Image ghcr.io/gemberkoekje/bot-on-the-clocktower` (+42 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `grafana HelmRelease` connect `Observability / Monitoring Stack` to `Infrastructure Helm Releases & Sources`, `Persistent Storage & PostgreSQL`, `Ingress Routing & TLS`?**
  _High betweenness centrality (0.318) - this node is a cross-community bridge._
- **Why does `Grafana Ingress` connect `Ingress Routing & TLS` to `Observability / Monitoring Stack`?**
  _High betweenness centrality (0.304) - this node is a cross-community bridge._
- **Why does `ClusterIssuer: letsencrypt-prod` connect `Ingress Routing & TLS` to `Flux GitOps Cluster Root`, `SpaceTraders App`?**
  _High betweenness centrality (0.293) - this node is a cross-community bridge._
- **What connects `Graphify Knowledge Graph`, `Image ghcr.io/gemberkoekje/adventureengine`, `Image ghcr.io/gemberkoekje/armabotcs` to the rest of the system?**
  _47 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Infrastructure Helm Releases & Sources` be split into smaller, more focused modules?**
  _Cohesion score 0.09116809116809117 - nodes in this community are weakly interconnected._
- **Should `Per-App Namespaces` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._