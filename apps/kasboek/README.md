# Kasboek

A personal budgeting app: the ASN bank account, the ASN VISA card and PayPal in one overview.
Source: the private repo Gemberkoekje/Kasboek (image `ghcr.io/gemberkoekje/kasboek:<commit sha>`,
built by its "Build and Push" workflow). Served at https://kasboek.lan.gemberkoekje.nl, **LAN and
Tailscale only**: Caddy (`infrastructure/lan-proxy/Caddyfile`) is the one way in. It holds bank
data, so it has no Gateway listener or HTTPRoute, and must never get one.

## Before the first deploy

### 1. Database and login on the shared PostgreSQL

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
-- Not a superuser, can't create databases or roles (the defaults).
CREATE ROLE kasboek LOGIN;
\password kasboek
CREATE DATABASE kasboek OWNER kasboek;
-- Every login may connect to a new database; only kasboek may connect to this one.
REVOKE CONNECT, TEMPORARY ON DATABASE kasboek FROM PUBLIC;
```

Make the password with `openssl rand -hex 24` (hex keeps the connection string valid). The app
creates its own tables (Marten) at its first start. The nightly `pg_dumpall`
(`infrastructure/postgresql-backup/`) includes the new database by itself.

### 2. The 1Password item

Item `kasboek-secrets` in the Gembercluster vault, with exactly these field labels:

- `ConnectionStrings__Postgres`:
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=kasboek;Username=kasboek;Password=<from step 1>`
- `Auth__Password`: the sign-in password (typed once per device; the sign-in lasts 90 days of
  not using it).

Other fields are ignored. A missing one keeps the pod in `CreateContainerConfigError`.

## Deploying

Bump the image tag in `deployment.yaml` to a sha that the workflow has already pushed, and merge.

```bash
kubectl -n kasboek get pods                      # Running, 1/1
kubectl -n kasboek logs deploy/kasboek --tail=20
```

The data-protection key ring lives in the database, so a redeploy doesn't sign anyone out.
