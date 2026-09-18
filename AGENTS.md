# Cursor Agents for HAS

Project-local Cursor rules mirror the GitHub Copilot custom agents under `.github/agents/`.

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

## Shared memory

- `.github/repo-memory/codegen-quirks.md` — register/peephole/codegen conventions discovered in the field.

When GitHub agent files and Cursor rules diverge, prefer updating both; GitHub agents remain the longer-form playbooks.
