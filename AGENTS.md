# FinWise — Agent entry

Read these before changing code:

1. [`.cursor/agent/INDEX.md`](.cursor/agent/INDEX.md) — map + how to navigate
2. [`.cursor/agent/CHANGELOG.md`](.cursor/agent/CHANGELOG.md) — append every change
3. [`.cursor/agent/AUDIT.md`](.cursor/agent/AUDIT.md) — known bugs / holes
4. Skills: `.cursor/skills/finanse-navigate`, `finanse-audit`, `finanse-feature`
5. Rules: `.cursor/rules/finanse-core.mdc`, `finanse-flet.mdc`

Product: local-first personal finance (Flet 0.83–0.86, SQLite). Desktop: `python main.py`. Data: `%LOCALAPPDATA%\finanse\finanse`.

Do not break unrelated features. Prefer version-safe Flet APIs. Update CHANGELOG after each task.
