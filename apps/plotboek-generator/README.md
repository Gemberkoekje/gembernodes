# Plotboek Generator (demo)

The public demo of the Plotboek Generator: plan the encounters of a LARP weekend and export them as a
Word document. Source: https://github.com/Gemberkoekje/plotboek-generator (image
`ghcr.io/gemberkoekje/plotboek-generator:<version>`, built by its release workflow on a `v*` tag).
Served at https://plotboek.gemberkoekje.nl; https://gemberkoekje.nl/plotboek redirects there.

It runs as a demo (`Demo__Enabled`): a banner on every page, an example plotboek on the first start,
and a nightly reset (`reset-cronjob.yaml`, 04:00) that puts the example back and removes visitors'
accounts. Whoever signs in with Google is a Reader: they see everything, the unfinished plots and
the feedback included, and change nothing. It speaks English, and Dutch to a browser that asks for
it (or through the switcher in the menu); the example data and the Word export are English.

## Before the first deploy

### 1. Database and login on the shared PostgreSQL

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
CREATE ROLE plotboek_generator LOGIN;
\password plotboek_generator
CREATE DATABASE plotboek_generator OWNER plotboek_generator;
REVOKE CONNECT, TEMPORARY ON DATABASE plotboek_generator FROM PUBLIC;
```

Make the password with `openssl rand -hex 24`. The app creates its tables (Marten) on its first start.

### 2. A Google sign-in client

In the Google Cloud console, under APIs & Services:

- **OAuth consent screen**: External, the scopes `openid`, `email` and `profile`, and published ("In
  production"). While it is in testing only the listed test users can sign in.
- **Credentials**, OAuth client ID, type Web application, authorized redirect URI
  `https://plotboek.gemberkoekje.nl/signin-oidc-google`.

### 3. The 1Password item

Item `plotboek-generator-secrets` in the Gembercluster vault, with exactly these field labels:

- `ConnectionStrings__Postgres`:
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=plotboek_generator;Username=plotboek_generator;Password=<from step 1>`
- `Oidc__Google__ClientId`, `Oidc__Google__ClientSecret`: from step 2.
- `Authentication__Admins`: the Google addresses that are Admin, separated by commas.
- `Demo__ResetApiKey`: `openssl rand -hex 32`. The cronjob sends it; without it the reset answers 503.
- `Branding__ContactUrl` (optional): where visitors ask for write access, a `mailto:` or `https:` link.
  The banner and the privacy page link to it; left out, they don't.

A missing required field keeps the pod in `CreateContainerConfigError`.

### 4. DNS

`plotboek.gemberkoekje.nl` pointing where `kluskat.gemberkoekje.nl` points. cert-manager fetches the
certificate once the name resolves.

## Deploying

Bump the image tag in `deployment.yaml` to a released version and merge. CI checks that the image
exists.

```bash
kubectl -n plotboek-generator get pods                                  # Running, 1/1
kubectl -n plotboek-generator logs deploy/plotboek-generator | grep -m1 "Demo example written"
```

## Running it

- **Write access**: someone signs in once, then an admin opens Admin, finds them under Reader and
  sets their override role to User. An override survives the nightly reset; clearing it makes them a
  Reader again, and the next reset removes the account.
- **Reset now**: `kubectl -n plotboek-generator create job --from=cronjob/demo-reset demo-reset-now`.
  The answer is `{"removedAccounts":N}`.
- **Sign-ins** don't survive a redeploy: the data-protection keys live in the container.
