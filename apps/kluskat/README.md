# Kluskat

One household chore at a time, with a pixel cat. Source: Gemberkoekje/projects `Kluskat/`
(image `ghcr.io/gemberkoekje/kluskat:<commit sha>`, built by the "Build and Push Kluskat"
workflow). Served at https://kluskat.gemberkoekje.nl.

## Before the first deploy

### 1. Database and login on the shared PostgreSQL

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
-- Not a superuser, can't create databases or roles (the defaults).
CREATE ROLE kluskat LOGIN;
\password kluskat
CREATE DATABASE kluskat OWNER kluskat;
-- Every login may connect to a new database; only kluskat may connect to this one.
REVOKE CONNECT, TEMPORARY ON DATABASE kluskat FROM PUBLIC;
```

Make the password with `openssl rand -hex 24` (hex keeps the connection string valid). The app
creates its own tables (Marten) at its first start.

### 2. The 1Password item

Item `kluskat-secrets` in the Gembercluster vault, with exactly these field labels:

- `ConnectionStrings__Postgres`:
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=kluskat;Username=kluskat;Password=<from step 1>`
- `Auth__Password`: the sign-in password (typed once per device).

Other fields are ignored. A missing one keeps the pod in `CreateContainerConfigError`.

## Deploying

Bump the image tag in `deployment.yaml` to a sha that the workflow has already pushed, and merge.

```bash
kubectl -n kluskat get pods                      # Running, 1/1
kubectl -n kluskat logs deploy/kluskat | grep -m1 Startvulling
```

The first start seeds the chore list; later starts leave it alone. The data-protection key ring
lives in the database too, so a redeploy doesn't sign anyone out.
