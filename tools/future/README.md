# Future Tools

This folder is for narrow manual/debug utilities that are useful now and may
become app/admin features later.

Rules:

- Do not put ordinary research probes here. Use `tools/experiments/` for those.
- Add a tool here only when the user explicitly asks, after clarification, or
  when it is genuinely reusable and no planned product surface owns it yet.
- Tools here must be conservative around generated user data: validate inputs,
  avoid broad deletes, and document which runtime files they write.
- Tools here are not production UI wiring by themselves.
