## graphify

Knowledge graph at graphify-out/ (god nodes, communities, cross-file
relationships) + an Obsidian vault at graphify-out/obsidian/.

INVOCATION: the `graphify` CLI is NOT on PATH here. Always run it through the
recorded interpreter:
  bash:       "$(cat graphify-out/.graphify_python)" -m graphify <args>
  powershell: & (Get-Content graphify-out/.graphify_python) -m graphify <args>

Rules:
- Codebase questions: run `... -m graphify query "<question>"` first (also
  `path "<A>" "<B>"`, `explain "<concept>"`). Every result line carries
  `src=<file>` — that is the real manifest. Use query to LOCATE, then Read/Edit
  the actual src= file. Never treat graph or vault text as the source of truth
  for a fix; it is derived and may lag the code.
- Staleness: the graph and vault go stale the moment a manifest changes. This is
  a YAML/config repo — all nodes come from semantic extraction, not AST — so
  `graphify update .` (AST-only) will NOT pick up manifest edits. After changing
  files, either treat the graph as describing the prior state, or run a full
  re-extract to refresh it.
- graphify-out/obsidian/ is the human entry point (open in Obsidian):
  _COMMUNITY_*.md per subsystem, [[wikilinks]] between notes, graph.canvas for
  the spatial view. For agent work prefer `query` — same relationships, already
  scoped, with real file paths.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review.
