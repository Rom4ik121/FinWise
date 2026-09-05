# FinWise — Agent entry

Read these before changing code:

1. [`.cursor/agent/INDEX.md`](.cursor/agent/INDEX.md) — map + how to navigate
2. [`.cursor/agent/CHANGELOG.md`](.cursor/agent/CHANGELOG.md) — append every change
3. [`.cursor/agent/AUDIT.md`](.cursor/agent/AUDIT.md) — known bugs / holes
4. Skills: `.cursor/skills/finwise-navigate`, `finwise-audit`, `finwise-feature`, `finwise-verify`
5. Rules: `.cursor/rules/finanse-core.mdc`, `finanse-flet.mdc`

Product: local-first personal finance (Flet 0.83–0.86, SQLite). Desktop: `python main.py`. Data: `%LOCALAPPDATA%\finanse\finanse`.

Do not break unrelated features. Prefer version-safe Flet APIs. Update CHANGELOG after each task.

**Post-change rule:** After EVERY code change, run `finwise-verify` skill — tests, architecture audit, invariant checks, UI↔logic integration, regression suite, and docs update (`docs/*`, README when user-facing). Never report "done" without verification.

Keep public docs in sync with Alembic head (**0026**), paging/UoW modules, and live UI languages (**ru/en/uz** only until uk/be/kk are wired).
