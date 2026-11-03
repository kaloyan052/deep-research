@AGENTS.md

## Claude Code specifics

- Research protocol: `.agents/skills/deep-research/SKILL.md` (also exposed as the
  `deep-research` skill via `.claude/skills/`). Tool mapping: `WebSearch` / `WebFetch` (or a
  search MCP such as Exa) for the web, `Agent` for parallel researcher and verifier
  subagents, `AskUserQuestion` for clarifications that change the plan.
- Run Python through the project venv: `.venv/Scripts/python.exe` (Bash) or
  `.venv\Scripts\python.exe` (PowerShell).
