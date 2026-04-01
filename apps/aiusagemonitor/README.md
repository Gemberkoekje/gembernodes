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

### `ghcr-login`
Store this as a **Docker Registry** item for `ghcr.io` with:

- username: your GitHub username or org service account
- password: a PAT with at least `read:packages`

This gets attached to the namespace `default` `ServiceAccount`, so new pods in this app do not need their own `imagePullSecrets` block.

> If you are happy for the image to be public, making the GHCR package public is even simpler and removes the need for this secret entirely.

## Image

The CronJob expects the container image at:

```text
ghcr.io/gemberkoekje/aiusagemonitor:latest
```
