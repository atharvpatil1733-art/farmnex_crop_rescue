---
description: Build one phase from docs/BUILD_PLAN.md, test it, then stop for review
argument-hint: <phase number 1-6>
---

Build **Phase $ARGUMENTS** from `docs/BUILD_PLAN.md`, and only that phase.

1. Read CLAUDE.md and the phase section in docs/BUILD_PLAN.md.
2. Load the skills the phase lists.
3. Before writing code, list the files you'll create or change in 3–6 bullets.
4. Implement it. Write the phase's tests alongside the code.
5. Run `pytest -q`. Fix failures until everything is green.
6. Run the judge-reviewer agent on the changed files and fix anything it marks MUST-FIX.
7. Tick the phase's checkboxes in docs/BUILD_PLAN.md.
8. Stop. Summarise in five lines or fewer what was built, how to try it, and anything that needs my decision. Don't start the next phase.
