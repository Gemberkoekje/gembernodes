# AiUsageMonitor deployment notes

## 1Password items

Create or update these items in the `Gembercluster` vault:

### `aiusagemonitor-secrets`
Store the following fields with these **exact names** so `envFrom` binds correctly in .NET:

- `CoPilot__ApiToken`
- `CoPilot__Organization`
- `Claude__ApiToken`
- `ConnectionStrings__Marten`
- `Email__To`

### `mail-secret`
- `SMTP_PASSWORD`

## Image

The CronJob expects the container image at:

```text
ghcr.io/gemberkoekje/aiusagemonitor:latest
```
