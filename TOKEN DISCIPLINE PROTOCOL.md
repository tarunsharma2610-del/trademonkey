TOKEN DISCIPLINE PROTOCOL — read this before anything else.

You are operating under a strict token budget. Treat every token as paid-for
compute: the goal is a committed, tested unit of work — NOT exploration.
Wasting tokens is the worst failure mode. Follow these rules without exception.

1. CONTEXT FIRST, NEVER REDISCOVER
   - Read the project's persistent context docs FIRST (e.g. README, HANDOVER,
     AGENTS.md, MASTER_ROADMAP) before any source code.
   - Never scan the repository to "understand" it. Never re-derive what the
     docs already state. If docs and code disagree, investigate ONLY that
     discrepancy.
   - Use any provided reading plan / file map. Read only task-relevant files.

2. BOUNDED READS
   - Grep/glob FIRST to locate symbols; then Read only the exact ranges needed
     (use offset/limit, never dump whole large files).
   - For files over ~150 lines, read segments, not the whole thing.
   - Prefer small reads over broad reads. Never read a file twice in a session
     if one targeted read suffices.

3. ONE TASK PER SESSION
   - Pick ONE well-scoped task. Finish it end-to-end: code -> tests -> docs ->
     commit -> push. Do not start a second task.
   - If the task is large, break it into small units and land each unit
     (commit+push) before continuing.

4. CHECKS, ONCE PER COMMIT
   - Run tests/lint/typecheck/build exactly ONCE per commit, not after every
     edit. Batch independent checks in parallel.
   - Use quiet flags and tail small outputs. A single CI-style run can cost
     tens of thousands of tokens; re-running it repeatedly is the fastest way
     to blow your budget.
   - Do NOT re-run checks for code you did not touch. Do NOT re-verify
     already-green modules.

5. NO UNRELATED WORK
   - No refactoring, no "improvements", no re-formatting of code you were not
     asked to touch. No rewriting working architecture.
   - If you notice an issue unrelated to your task, note it in the handover
     doc instead of fixing it.

6. COMMIT AND PUSH EARLY
   - The moment a unit is correct and green, commit + push. Never leave work
     only in the local workspace.
   - Never start cleanup or exploration AFTER finishing — stop and report.

7. TOOL OUTPUT DISCIPLINE
   - Suppress noise: use --quiet, -q, --porcelain, head/tail with small
     limits. Prefer grep to read files for content.
   - If a command will print thousands of lines, redirect to a file or add a
     timeout/limit first.
   - Do not cat/print files wholesale.

8. STOP CONDITIONS
   - If a task needs more than ~2 debug iterations, STOP and rethink the
     approach (or ask the user) instead of trial-and-error spending.
   - If you sense budget is running low: finish the current safe unit, update
     docs, commit, push, then STOP. Never start a new unit on a low budget.
   - If you cannot finish: document exactly what remains in the handover doc,
     commit, push, and report. Never pretend unfinished work is done.

9. CONTEXT ECONOMY
   - Use subagents for open-ended exploration so their context does not bloat
     yours.
   - Keep conversation lean: do not repeat large file contents in replies.
   - When in doubt about scope, ask ONE short question before spending tokens
     on the wrong direction.

SUCCESS LOOKS LIKE: one committed, tested, documented unit per session, repo
green, pushed to remote, handover doc updated. Not: volume of code written,
exploration done, or extra polish.
