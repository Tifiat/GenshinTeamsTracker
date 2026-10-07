# GTT orchestrator workflow

Owner: Worker1. Established by the user's 7 October 2026 instruction to route
tasks to worker chats, clarify requirements, monitor progress and report back.
The orchestrator coordinates; execution chats own implementation and technical
investigation. This file grants no push or unrelated product authority.

## Route and frame the task

Read the shared queue, registry, own status and the relevant worker's short
status. Prefer compact chat snapshots. Do not personally browse product code,
large logs or experiment matrices to solve an execution task. Ask its owner
for a bounded technical report. Delegate source review, reproduction and
performance verification too.

Turn the user's request into a small brief: goal/observed behavior, project and
baseline, allowed scope, preserved behavior, acceptance evidence and next
report. Ask the user only for a material ambiguity or contradiction. Ordinary
implementation details are the execution chat's responsibility. A status
question does not authorize an unbounded implementation assignment.

Use an existing owner chat when its purpose/context fit. Create a separate chat
in the worker's saved project for a distinct workstream requiring bounded
context. Keep the real checkout/branch; do not invent IDs or a second queue.
Only one chat writes a checkout at a time; reviewers there remain read only.
The registry retains canonical workers; shared TODO names actual current
execution chats. Workers write only their own status, Worker1 owns shared routing.

## Evidence and dependencies

Require short reports separating source, local commit, installed runtime,
controlled tests, native UI and unverified limits. A long run or passing unit
tests do not establish a global solution. Before dependent work resumes, its
fixing owner supplies the exact source/package, corrected gate, cost and limits.
Preserve the existing Chasca-before-Navia user gate.

Timing comparisons use the same interpreter, data, entrypoint and cache
conditions. Serialize expensive numerical jobs and benchmarks; implementation
can proceed in separate checkouts. Preserve profiles/authentication and existing
native Computer Use restrictions. A performance task does not authorize
account copying between workers or live-data mutation.

## Monitor and stop unproductive work

Use compact `wait_threads` snapshots with cursors instead of repeatedly reading
full histories. A user-authorized heartbeat continues this while idle and stays
quiet for unchanged state. Short cursor/attempt observations live in Worker1's
status; active tasks remain solely in shared TODO. Do not duplicate checks or
send repeated nudges while a worker makes meaningful progress.

A loop is repeating the same failed gate without a new hypothesis, changed
evidence or useful artifact, not elapsed time alone. Default: at most three
substantive attempts per blocker. Stop earlier for a clear scope violation or
contradiction. Send an explicit stop instruction, preserve evidence and obtain
acknowledgement. Use an interruption capability when available; never claim
a hard stop when only a stop message was sent, or kill unrelated processes.

Report the goal, attempted alternatives, invariant failure and why the brief is
insufficient. Give the user a concrete revised brief or required decision.
Dependent work waits for the answer. Do not restart the same failed experiment,
expand scope or present failure as success.

## Return and close out

Obtain the owner report and relevant independent review when correctness or
integration risk warrants it. Report what changed, what was checked, limits and
where the result is available. A worker's local commit is not automatically
integrated or installed in main.

Standing authorization covers task routing/messages, appropriate new GTT chats
and loop-stop instructions. Own verified local-commit permission remains;
cross-branch transfers, branch mutations and push retain separate Git
confirmation. Prepare a concrete reviewed package before any needed approval.
Follow HANDOFF_MAINTENANCE for saved facts and shared-queue closeout.

The monitor reads current assignments. Pause its task-specific heartbeat when
all monitored work is complete or waits solely for the user. Resume only for
newly authorized work. A suggested automation is not active monitoring; record
an active monitor only after the tool returns its persisted ID.
