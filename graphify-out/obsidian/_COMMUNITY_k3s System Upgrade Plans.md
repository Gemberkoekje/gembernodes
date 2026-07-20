---
type: community
members: 3
---

# k3s System Upgrade Plans

**Members:** 3 nodes

## Members
- [[System Upgrade Plans Kustomization]] - document - infrastructure/system-upgrade-plans/kustomization.yaml
- [[k3s Agent Upgrade Plan]] - document - infrastructure/system-upgrade-plans/k3s-upgrade-plan.yaml
- [[k3s Server Upgrade Plan]] - document - infrastructure/system-upgrade-plans/k3s-upgrade-plan.yaml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/k3s_System_Upgrade_Plans
SORT file.name ASC
```
