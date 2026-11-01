# print-manager test desk

The Vortex print desk (vortexadventures/print-manager) with two fake HP LaserJet 4250s instead of
real ones, locked to the test void `test-void-api.the-vortex.nl`. Image, start-up and the local
docker compose version are described in that repository's `deploy/README.md`.

- Dashboard: http://192.168.1.233/ (LAN only; includes /admin with the void login).
- LAN printers: `http://192.168.1.233:631/printers/Vortex_White` (also Vortex_Special,
  Vortex_Extra_1, Vortex_Extra_2), added by URL.
- Fake printer pages: `kubectl -n print-manager-test port-forward deploy/print-manager-test 8100 8101`,
  then http://localhost:8100/ (Printer B: Special tray, cards) and http://localhost:8101/ (Printer A).
- State is on `print-manager-test-data-qnap` (`/data`): `config.yaml`, `env`, `outbox/`, `spool/`,
  `fake-printer-a/`, `fake-printer-b/`. Nothing prunes the fake-printer folders.

Before the first deploy, in 1Password vault Gembercluster:

- `print-manager-test-secrets`: fields `VOID_PLIN`, `VOID_PASSWORD` (the test void login).
- `gitlab-login`: field `.dockerconfigjson` for registry.gitlab.com, from a GitLab deploy token
  with `read_registry` on vortexadventures/print-manager.

The image tag in `deployment.yaml` (three `image:` lines) is the one the manual `build-and-push`
job in print-manager's GitLab CI prints. The PR image check can't see a private GitLab image and
only warns, so merge after the job has pushed it.

Never set `replicas` above 1: two desks would print the same cards twice. Keep
`PRINT_MANAGER_VOID_HOST_LOCK` and `VOID_BASE_URL` in the pod spec, not on the volume: the lock is
what stops the Admin page pointing this desk at the production void, and the image will not start
without it.
