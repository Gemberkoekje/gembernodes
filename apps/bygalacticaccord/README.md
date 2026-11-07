# By Galactic Accord

A space-economy game in development. Source: Gemberkoekje/projects `ByGalacticAccord/` (image
`ghcr.io/gemberkoekje/bygalacticaccord:<commit sha>`, built by the "CI - By Galactic Accord" workflow
on `main` once its build, tests and browser check pass). Served at https://bygalacticaccord.gemberkoekje.nl.

The client is Blazor WebAssembly and runs the whole simulation in the browser, so the pod is nginx
serving static files: no database, no secrets, no volume, nothing to back up. Every browser tab plays
its own game, and a reload starts a new one; nothing is stored on the server.

## Deploying

Set the image tag in `deployment.yaml` to a sha that the workflow has already pushed, and merge.
`scripts/check_images.py` (the `images` job on pull requests) waits for it if the build is still
running.

```bash
kubectl -n bygalacticaccord get pods                                      # Running, 1/1
curl -sI https://bygalacticaccord.gemberkoekje.nl/ | head -1              # 200
```

The site's files under `_framework/` are cached for a year (their names change with their content);
`index.html` and the rest revalidate on each load, so a new deploy shows on the next reload.
