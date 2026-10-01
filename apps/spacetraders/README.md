# SpaceTraders

The SpaceTraders bot and its dashboard, from `SpaceTraders/` in Gemberkoekje/projects. Its plan is
`SpaceTraders/PLAN.md` there: these manifests are its slice 4.2, bringing the bot back after it was
taken off in May 2026 for filling the shared PostgreSQL.

| File | What it is |
|---|---|
| `deployment-api.yaml` | The bot and its internal API. One pod, never two (`Recreate`). Prometheus scrapes its metrics on port 9090, which the Service doesn't route. |
| `deployment-webui.yaml` | The React dashboard (nginx). |
| `service-api.yaml`, `service-webui.yaml` | Port 80 of each. |
| `api.env` | The API's environment: Production, its ports, Serilog levels. Flux rolls the pod when it changes. |
| `spacetraders-secrets.yaml` | The 1Password item; `secret.yaml.template` lists its fields. |
| `../../ingress/spacetraders-ingress.yaml` | LAN only: http://192.168.1.231/spacetraders/dashboard/ and `/spacetraders/api`. |
| `../../namespaces/spacetraders-namespace.yaml` | The namespace. |

Grafana's "SpaceTraders" dashboard and the alert groups `spacetraders` and `spacetraders-logs`
(`infrastructure/monitoring/`) read its metrics and its log.

## Before the first deploy (by hand)

### 1. Database logins (slice 4.1)

The bot gets a login of its own that owns only the `spacetraders` database, and Claude gets a
read-only one. A database of its own doesn't cap the disk; the bot's size guard does (a warning at
1 GB, automation off at 3 GB), and so does the Grafana alert.

Connect as the PostgreSQL admin (`postgres`; the password is in the 1Password item
`postgresql-admin-secret`), from a LAN machine:

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

First, look for anything left from before the May shutdown:

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname = 'spacetraders';
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname LIKE 'spacetraders%';
```

- An old `spacetraders` database: drop it (`DROP DATABASE spacetraders;`) once you've checked that
  nothing else uses it. The bot starts empty, and a database from before its slice 1.4 doesn't
  fit its tables.
- An old `spacetraders` login that isn't a superuser and can't create databases or roles: keep it,
  and skip its `CREATE ROLE` line below. Otherwise drop it or pick another name.

Then create both logins. `\password` asks for the password; make one up with, for example,
`openssl rand -hex 24` (hex keeps the connection string valid).

```sql
-- The bot's login: not a superuser, and it can't create databases or roles (the defaults).
CREATE ROLE spacetraders LOGIN;
\password spacetraders
CREATE DATABASE spacetraders OWNER spacetraders;
-- Every login may connect to a new database; only these two may connect to this one.
REVOKE CONNECT, TEMPORARY ON DATABASE spacetraders FROM PUBLIC;

-- The read-only login, for Claude on your PC (slice 5.2).
CREATE ROLE spacetraders_ro LOGIN;
\password spacetraders_ro
ALTER ROLE spacetraders_ro SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE spacetraders TO spacetraders_ro;
\connect spacetraders
GRANT USAGE ON SCHEMA public TO spacetraders_ro;
-- The bot creates its tables at its first start: reading rights on every table it creates, and on
-- any it already has.
ALTER DEFAULT PRIVILEGES FOR ROLE spacetraders IN SCHEMA public GRANT SELECT ON TABLES TO spacetraders_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO spacetraders_ro;
```

Keep the read-only password where Claude will read it on your PC (slice 5.2), not in the item
below: nothing on the cluster uses it.

Tested against PostgreSQL 18 on 2026-10-01: the bot started as `spacetraders` and created its 28
tables; `spacetraders_ro` could read them but not write, even with read-only switched off; another
app's login couldn't connect; and `spacetraders` couldn't create a database.

### 2. The 1Password item

The item `spacetraders-secrets` in the Gembercluster vault needs the four fields of
`secret.yaml.template`, labelled exactly like that:

- `ConnectionStrings__DefaultConnection`:
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=spacetraders;Username=spacetraders;Password=<from step 1>`
- `SpaceTraders__AccountToken`: the account token from https://my.spacetraders.io.
- `SpaceTraders__AgentName`: the agent's callsign.
- `SPACETRADERS_INTERNAL_API_KEY`: a random secret, for example `openssl rand -hex 32`.

Fields with other labels, such as any left from before May, are ignored. A missing one keeps the
pod in `CreateContainerConfigError`, which the "Container crash-looping or failing to start" alert
reports after 15 minutes.

## Deploying

Merge. Flux creates the namespace, the Secret (through the 1Password operator), both deployments
and the ingress within a few minutes; until the Secret exists the pods wait in
`CreateContainerConfigError`. The API pod counts as started only once its startup chain has
completed (`/health/startup`), and a chain that fails restarts it.

```bash
kubectl -n spacetraders get pods                 # both Running, 1/1
kubectl -n spacetraders logs deploy/spacetraders-api | grep -m1 'Deferred startup initialization completed'
```

Then, once the bot has started:

1. In Grafana, Explore, Prometheus: `up{namespace="spacetraders"}` is 1.
2. Restart Grafana, so it reads the alert rules (it reads them only at startup). Wait for step 1
   first: without that series, "SpaceTraders bot is down" fires after a minute.

   ```bash
   kubectl -n monitoring rollout restart deployment grafana
   ```

3. Take the agent token out of the read-only login's reach (the table exists from the first start
   on). As `postgres`, in the `spacetraders` database:

   ```sql
   REVOKE SELECT ON stored_credentials FROM spacetraders_ro;
   ```

4. Open http://192.168.1.231/spacetraders/dashboard/ on the LAN (`.230` works too while
   ingress-nginx runs). From outside it, for example a phone on mobile data,
   https://gemberkoekje.nl/spacetraders/dashboard/ must be refused.

What to watch in the first hours and days is slice 4.3 of the plan.

## A new image

CI builds `ghcr.io/gemberkoekje/spacetraders-api` and `-webui` on every push to `main` of
Gemberkoekje/projects that touches `SpaceTraders/`, tagged with the commit SHA. To deploy one,
change both image tags to that SHA.
