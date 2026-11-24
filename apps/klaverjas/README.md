# Klaverjas

The weekly scoring of a klaverjas club (De Samenspelers), kept by a 70-year-old. Players see the
standings at https://klaverjas.gemberkoekje.nl behind the club's password; Dad keeps the scores at
`/beheer` with his own password, puts the standings online with one button, and can mail them with a
PDF. Source: Gemberkoekje/projects `Klaverjas/` (image `ghcr.io/gemberkoekje/klaverjas:<commit sha>`,
built by the "Build and Push Klaverjas" workflow on `main`). The plan and every decision are in
`Klaverjas/PLAN.md` there; the per-slice notes in `Klaverjas/NOTES.md`.

This app took over the hostname from the design mock (NOTES.md, 2026-11-20), so DNS, the Gateway
listener `https-klaverjas` and its certificate are already in place. `gemberkoekje.nl/klaverjas`
now redirects to the hostname: the app doesn't run under a path.

## Before the first deploy

Do these before the PR merges. A missing database or 1Password item keeps the pod in
`CreateContainerConfigError` or crash-looping, and the cluster's "pod stuck" alerts start emailing
after 15 minutes.

### 1. Database and login on the shared PostgreSQL

In DBeaver: open [create-database.sql](create-database.sql) on a connection to the database
`postgres` as `postgres`, with auto-commit on, and follow its steps (it makes the password too). The
app creates its own tables (Marten) at its first start. The data-protection key ring lives there
too, so a redeploy doesn't sign anyone out (players stay signed in for a year).

### 2. The 1Password item

Item `klaverjas-secrets` in the Gembercluster vault, with exactly these field labels:

- `ConnectionStrings__Postgres` (required):
  `Host=postgresql.flux-system.svc.cluster.local;Port=5432;Database=klaverjas;Username=klaverjas;Password=<from step 1>`
- `Auth__Password` (required): Dad's first password for `/beheer`. Make it one he can type. See
  "After the first deploy" for why to change it later.
- `Mail__User` (optional): the Gmail address the standings are mailed from, the account whose app
  password is in the existing `mail-secret` item (field `SMTP_PASSWORD`). Without it, mailing stays
  off and the screens say so; everything else works.

Other fields are ignored. The `mail-secret` item already exists (cov-website and Grafana use it);
this app only reads it.

## Deploying

Bump the image tag in `deployment.yaml` to a sha that the workflow has already pushed, and merge.
The PR's "Images exist" check waits up to 20 minutes for an image that's still building.

```bash
flux reconcile kustomization flux-system --with-source
kubectl -n klaverjas get pods                          # klaverjas-… 1/1 Running
curl -s https://klaverjas.gemberkoekje.nl/healthz      # ok
curl -sI https://gemberkoekje.nl/klaverjas | grep -i location   # https://klaverjas.gemberkoekje.nl/
```

Marten updates the schema on start, and the key ring is in the database, so an image bump signs
nobody out.

## After the first deploy

1. Sign in at https://klaverjas.gemberkoekje.nl/beheer with `Auth__Password`.
2. **Instellingen:** choose the players' password (the players' page stays closed until then), and
   fill in "Antwoorden gaan naar" with Dad's own address: replies and the test mail go there.
3. **The live mail check:** put a week online (Stand → "Zet de stand online"), then "Proefmail naar
   mij". It should arrive at that address from the Gmail account, with the PDF.
4. **Dad's own password:** once Dad has chosen his own in Instellingen (it is stored as a hash), the
   configured `Auth__Password` still opens `/beheer`: it is the way back in when he forgets his. So
   change it then to a long random one that only you keep, wait for the operator's sync (at most 10
   minutes; its log says `Updating kubernetes secret 'klaverjas-secrets'`), and restart, because the
   operator doesn't restart pods:

   ```bash
   kubectl -n klaverjas rollout restart deployment klaverjas
   ```

The same wait-then-restart applies whenever you change a field in the item.
