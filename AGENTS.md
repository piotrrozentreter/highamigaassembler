# Cursor Agents for HAS

HAS has two Cursor surfaces that must not be confused:

| Surface | Path | Role |
|---|---|---|
| **Task subagents (tool pool)** | `.cursor/agents/*.md` | Invocable via the Agent/Task tool (`subagent_type` = frontmatter `name:`). Full playbooks adapted from GitHub agents. |
| **Always-on / scoped rules** | `.cursor/rules/*.mdc` | Short Cursor rules injected by context; **not** Task-invocable subagents. |

GitHub Copilot custom agents under `.github/agents/*.agent.md` remain the longer-form source of truth. Cursor Task agents are adaptations (Cursor frontmatter only; Copilot-only fields like `tools:`, `user-invocable:`, `argument-hint:` are omitted).

## Task-invocable subagents (`.cursor/agents/`)

| Task `name` | Cursor agent file | Source of truth | Invoke when |
|---|---|---|---|
| **has-compiler** | `.cursor/agents/has-compiler.md` | `.github/agents/compiler.agent.md` | Changing `hasc/` pipeline |
| **has-review** | `.cursor/agents/has-review.md` | `.github/agents/review.agent.md` | Severity-based correctness review |
| **has-tests** | `.cursor/agents/has-tests.md` | `.github/agents/tests.agent.md` | Regression / vasm / Musashi |
| **has-docs** | `.cursor/agents/has-docs.md` | `.github/agents/docs.agent.md` | README / docs / changelog |
| **has-gamedev** | `.cursor/agents/has-gamedev.md` | `.github/agents/gamedev.agent.md` | Games, chipset, cycle tuning |
| **has-amigados** | `.cursor/agents/has-amigados.md` | `.github/agents/amigados.agent.md` | Shell/Workbench OS tools |

Invoke with Task and `subagent_type` matching the `name:` value (e.g. `has-compiler`).

A copy of `has-compiler.md` also lives in the Graveyard Shadows game repo tool pool so game chats can call the compiler specialist when toolchain/codegen questions arise; implementation root remains `hasc/` in this repo.

## Cursor rules (`.cursor/rules/`) — not Task agents

| Agent | Cursor rule | Source of truth | Invoke when |
|---|---|---|---|
| **compiler** | `.cursor/rules/compiler.mdc` | `.github/agents/compiler.agent.md` | Changing `hasc/` pipeline |
| **review** | `.cursor/rules/review.mdc` | `.github/agents/review.agent.md` | Severity-based correctness review |
| **tests** | `.cursor/rules/tests.mdc` | `.github/agents/tests.agent.md` | Regression / vasm / Musashi |
| **docs** | `.cursor/rules/docs.mdc` | `.github/agents/docs.agent.md` | README / docs / changelog |
| **gamedev** | `.cursor/rules/gamedev.mdc` | `.github/agents/gamedev.agent.md` | Games, chipset, cycle tuning |
| **amigados** | `.cursor/rules/amigados.mdc` | `.github/agents/amigados.agent.md` | Shell/Workbench OS tools |

Always-on context: `.cursor/rules/has-project.mdc` (from `.github/copilot-instructions.md`).

## Skills (GitHub; use as references)

- `.github/skills/python-compiler-engineering/`
- `.github/skills/assembly-validator/`
- `.github/skills/has-language/`
- `.github/skills/regression-sweep/`
- `.github/skills/has-ptplayer-audio/` — MOD + IFF SFX via ptplayer (also `.cursor/skills/has-ptplayer-audio/`)

## Shared memory

- `.github/repo-memory/codegen-quirks.md` — register/peephole/codegen conventions discovered in the field.

When GitHub agent files, Cursor Task agents, and Cursor rules diverge, prefer updating all three; GitHub agents remain the longer-form playbooks.
