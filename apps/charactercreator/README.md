# Character Creator (demo)

The Vortex Character Creator's proof of concept: a rebuild of Thorfgin's builder on the Vortex
stack, with VOID's skill rules. Source: Gemberkoekje/projects `CharacterCreator/` (image
`ghcr.io/gemberkoekje/charactercreator:<commit sha>`, built by the "Build and Push CharacterCreator"
workflow on `main`). Served at https://charactercreator.gemberkoekje.nl.

It lives here only until Thorfgin has seen it; then it moves to Vortex's own hosting
(`builder.the-vortex.nl`) and this app is removed.

## Before the first deploy

### 1. Database and login on the shared PostgreSQL

In DBeaver: open [create-database.sql](create-database.sql) on a connection to the database
`postgres` as `postgres`, with auto-commit on, and follow its steps (it makes the password too).
Or in psql:

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
-- Not a superuser, can't create databases or roles (the defaults).
CREATE ROLE charactercreator LOGIN;
\password charactercreator
CREATE DATABASE charactercreator OWNER charactercreator;
-- Every login may connect to a new database; only charactercreator may connect to this one.
REVOKE CONNECT, TEMPORARY ON DATABASE charactercreator FROM PUBLIC;
```

Make the password with `openssl rand -hex 24` (hex keeps the connection string valid). The app
creates its own tables (Marten) at its first start, and seeds a provisional ruleset.

### 2. The 1Password item

Item `charactercreator-secrets` in the Gembercluster vault, with exactly this field label:

- `ConnectionStrings__Postgres`:
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=charactercreator;Username=charactercreator;Password=<from step 1>`

Other fields are ignored. A missing one keeps the pod in `CreateContainerConfigError`.

### 3. The Keycloak redirect (Vortex ERU)

Signing in goes through the realm `vortex` on `auth.the-vortex.nl` with the client `vortex-dev`.
Add to that client:

- Valid redirect URIs: `https://charactercreator.gemberkoekje.nl/signin-oidc`
- Valid post logout redirect URIs: `https://charactercreator.gemberkoekje.nl/signout-callback-oidc`
  and `https://charactercreator.gemberkoekje.nl/`

Without them everything works except signing in (which only SL and EC need, to import the rules
from VOID).

## Deploying

Bump the image tag in `deployment.yaml` to a sha that the workflow has already pushed, and merge.

```bash
kubectl -n charactercreator get pods                                   # Running, 1/1
kubectl -n charactercreator logs deploy/charactercreator | grep -m1 seeded
```

The first start seeds the ruleset from the offline snapshot (marked provisional); later starts
leave it alone. An SL or EC replaces it under Beheer → Rulesets by importing from `void-test`. The
data-protection key ring lives in the database too, so a redeploy doesn't sign anyone out.
