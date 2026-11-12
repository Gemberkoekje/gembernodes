## Start here

[MAP.md](MAP.md) is the map of this repository: which folder holds what, the IP addresses and
hostnames, the shared services (PostgreSQL, 1Password, storage, certificates) and which app depends
on what. Read it first to find your way, then open the manifests it points at. The manifests are
the source of truth; MAP.md only points at them.

[NOTES.md](NOTES.md) is the dated log of changes: why, gotchas, what was tested. Read the latest
entries about a subsystem before changing it, and end each change with an entry of your own, like
the existing ones.

## Keep MAP.md current

Check every change against MAP.md before committing it:

- **Update MAP.md in the same commit** when the change adds, removes, renames or moves anything it
  describes: an app, namespace, folder or Flux Kustomization; an IP address, hostname, port or
  route; a volume or StorageClass; a shared service, or which apps use it; a script or CI check; how
  two pieces connect.
- **Leave it alone** when the picture stays the same: an image bump, a resource limit, a setting
  inside one app.
- **Found MAP.md wrong** about something you didn't change? Fix it in the same change and say so in
  the pull request.
- Keep it short and current-state only: no history, no image tags, no numbers that drift by
  themselves. History goes in NOTES.md.
