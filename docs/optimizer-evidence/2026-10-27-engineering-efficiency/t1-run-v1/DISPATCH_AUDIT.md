# T1 dispatch and usage audit — 28 October 2026

Human requested one cheap Luna observation, then discussion. ROOT instead
dispatched the long-running existing Sol/high writer for a new wrapper/READY
cycle while coordinating on Astra/xhigh. This was disproportionate preparation,
not optimizer algorithm work. Existing-owner/product-writer routing was applied
too broadly to a measurement-only task; the project also explicitly requires
bounded low-context cheap delegation. Those rules did not require this expense.

Local session accounting, 10:57:48–11:19:00 UTC (13:57:48–14:19 Moscow):

| Agent | Usage events | Input tokens, including repeated/cached context | Cached input | Output tokens |
| --- | ---: | ---: | ---: | ---: |
| ROOT Astra/xhigh | 30 | 5196183 | 5169792 | 12826 |
| MAIN Sol/high | 36 | 13111575 | 12741888 | 22777 |
| Internal Luna/low | 10 | 663212 | 586880 | 1624 |

These are differences of cumulative token counters in the local session logs,
not unique text sizes, exact billed usage or attributable subscription percent.
MAIN carried approximately309–386k input tokens per response, ROOT165–199k.
The Plus snapshot during preparation reported48% used of300min; the later
platform denial confirms exhaustion but cannot allocate its cost per chat.
The next account snapshot exposes a different account/bucket and is not a
continuation of that Plus measurement. No account switch was performed by ROOT.

Luna DID receive the command via collaboration.followup_task to
/root/chasca_r5_luna, not the separate sidebar Luna chat. Its T1 turn started
11:16:58 UTC; the existing owner dispatched the child11:17:18 UTC. The agent hit
the usage limit11:18:58 UTC. ROOT also hit the limit11:18:59 UTC. A command sent
to an internal subagent does not create a message in the old sidebar tester chat.

Observed failure before worker construction/optimizer launch:
`t1_theory_button.py:114: ValueError: T1 actual Theory settings differ`.
The real button harness wraps the request with its sentinel product timeout1;
the existing adapter normalizes that to0 inside its superclass. T1 checked0
before calling that superclass, so the added assertion rejected the valid
adapter input. Individual command/type and synthetic Finish tests missed the
actual wrapper composition. The Qt callback exception left the test waiting;
no gtt-optimizer/gtt-gcsim child was present during ROOT diagnosis.

Do not report this as a Theory quality/performance result. No new run, algorithm
fix, next team or expensive execution chat is authorized by this audit. Preserve
the failed evidence and close only the owned stalled child/original owner.

Future measurement-only dispatch: use an existing verified command with one
cheap low-context tester; return its compact result for discussion. Do not wake
the context-heavy implementation chat or create a new admission pipeline unless
a concrete missing capability is first established. Any necessary runner fix
must stay narrow and verify the actual adapter seam, not just its components.
