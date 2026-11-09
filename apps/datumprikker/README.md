# DatumPrikker

Propose a few dates, share a link, and see which day works. Answering needs no account; making a
poll needs a login (Google or Microsoft) and the admin's approval. Source: Gemberkoekje/projects
`DatumPrikker/` (image `ghcr.io/gemberkoekje/datumprikker:<commit sha>`, built by the "Build and
Push DatumPrikker" workflow on `main`). Served at https://datumprikker.gemberkoekje.nl.

The name already resolves to the public ingress (checked 2026-11-09), so there's no DNS step.
cert-manager fetches the certificate on the first deploy.

## Before the first deploy

Do these before the PR merges. A missing database or 1Password item keeps the pod in
`CreateContainerConfigError` or crash-looping, and the cluster's "pod stuck" alerts start emailing
after 15 minutes.

### 1. Database and login on the shared PostgreSQL

In DBeaver: open [create-database.sql](create-database.sql) on a connection to the database
`postgres` as `postgres`, with auto-commit on, and follow its steps (it makes the password too).
Or in psql:

```bash
psql -h 192.168.1.232 -U postgres -d postgres
```

```sql
CREATE ROLE datumprikker LOGIN;
\password datumprikker
CREATE DATABASE datumprikker OWNER datumprikker;
REVOKE CONNECT, TEMPORARY ON DATABASE datumprikker FROM PUBLIC;
```

Make the password with `openssl rand -hex 24`. The app creates its own tables (Marten) at its first
start. The data-protection key ring lives there too, so a redeploy doesn't sign anyone out.

### 2. The sign-in apps (optional for the first deploy, needed to log in)

Each provider shows up on the sign-in page only when both of its values are in the item (step 3).
Without either, the site works for answering, but nobody can log in to make polls.

- **Google:** in the Google Cloud console, under APIs & Services.
  - Use a project of its own, because the consent screen shows the project's app name.
  - **OAuth consent screen:**
    - External;
    - scopes `openid`, `email` and `profile`;
    - published ("In production"). While it's in testing, only the listed test users can sign in.
  - **Credentials:** OAuth client ID, type Web application, with authorized redirect URI
    `https://datumprikker.gemberkoekje.nl/signin-google`.
- **Microsoft:** in the Microsoft Entra admin center, under App registrations, choose New
  registration.
  - Supported account types: "Accounts in any organizational directory and personal Microsoft
    accounts".
  - Redirect URI: platform Web, `https://datumprikker.gemberkoekje.nl/signin-microsoft`.
  - Under Certificates & secrets, make a client secret and copy its **Value** (not its ID). Note
    its expiry date; logging in with Microsoft stops working when it expires.
  - The Application (client) ID is the client id.

### 3. The 1Password item

Item `datumprikker-secrets` in the Gembercluster vault, with exactly these field labels:

- `ConnectionStrings__Postgres` (required):
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=datumprikker;Username=datumprikker;Password=<from step 1>`
- `Authentication__Google__ClientId` and `Authentication__Google__ClientSecret` (optional): from
  step 2.
- `Authentication__Microsoft__ClientId` and `Authentication__Microsoft__ClientSecret` (optional):
  from step 2.
- `Admin__Accounts` (optional): leave it out for now; see "After the first deploy".

Other fields are ignored. A missing `ConnectionStrings__Postgres` keeps the pod in
`CreateContainerConfigError`.

## Deploying

Bump the image tag in `deployment.yaml` to a sha that the workflow has already pushed, and merge.
The PR's "Images exist" check waits up to 20 minutes for an image that's still building.

```bash
flux reconcile kustomization flux-system --with-source
kubectl -n datumprikker get pods,ingress,certificate          # pod 1/1 Running, certificate Ready
curl -s https://datumprikker.gemberkoekje.nl/healthz          # ok
```

## After the first deploy: become admin

Admins are account ids, not email addresses: an email claim from a Microsoft work account can be
spoofed, and admin is worth more than making polls. To set yours:

1. On https://datumprikker.gemberkoekje.nl, log in and open **Nieuwe prikker**. It shows
   "Je account-id: google:…".
2. Put that id in the item as `Admin__Accounts`. More than one admin is fine, separated by commas.
3. Wait for the 1Password operator's next sync (at most 10 minutes; its log says
   `Updating kubernetes secret 'datumprikker-secrets'`). Then restart, because the operator
   doesn't restart pods:

   ```bash
   kubectl -n datumprikker rollout restart deployment datumprikker
   ```

4. Reload the site: the header now shows **Beheer**. That's where you approve people who ask to
   make polls, and pre-approve email addresses.

The same wait-then-restart applies whenever you change a field in the item, such as adding Microsoft
later or renewing its secret.
