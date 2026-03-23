You are diagnosing an issue in the Nova AI assistant. Work through the orchestration loop systematically.

The issue the user is reporting: $ARGUMENTS

## Nova Orchestration Loop (trace order)

```
User input
  → Input parser / intent classifier
  → Tool router (selects tool by name)
  → Tool executor (calls tool.execute())
  → Response formatter
  → Output to user
```

Each layer can fail. Work top-down.

---

## Phase 1 — Reproduce and characterize

Ask the user (if not already clear from $ARGUMENTS):
1. What exact input triggered the issue?
2. What was the actual output or error?
3. What was the expected output?
4. Does it happen every time or intermittently?

Then check: `git status` and `git log --oneline -10` to understand recent changes.

---

## Phase 2 — Locate the failure layer

### Check: Input parsing
- Read `src/parser/index.ts` (or equivalent entry point)
- Look for how user input is normalized and classified
- Common failures: intent not matched → wrong tool selected, or no tool selected

### Check: Tool router
- Read `src/router/index.ts`
- Verify the tool name is registered in the tools map
- Common failures: tool not registered, name mismatch (e.g., `weather` vs `get-weather`)

### Check: Tool executor
- Read `src/tools/<tool-name>/index.ts`
- Check the `execute()` function signature matches the input being passed
- Look for silent failures: does `execute()` return `{ success: false }` that gets ignored upstream?
- Common failures: missing required input validation, uncaught exceptions, wrong return shape

### Check: External API (if tool makes API calls)
- Read `src/tools/<tool-name>/client.ts`
- Check: Is the env var for the API key set? (`process.env.API_KEY_NAME`)
- Check: Is the request URL correct? Any path/query param issues?
- Common failures: missing auth, wrong endpoint, rate limit hit, network timeout

### Check: Response formatter
- Read `src/formatter/index.ts` (or equivalent)
- Verify it handles `{ success: false, error: string }` gracefully
- Common failures: crashes on null/undefined data, assumes success always

---

## Phase 3 — Add targeted logging

If the failure layer is unclear, add temporary debug logs:

```typescript
// At the router level
console.debug('[router] received tool name:', toolName);
console.debug('[router] registered tools:', Object.keys(tools));

// At the executor level
console.debug('[<tool-name>] execute() called with:', JSON.stringify(input));
console.debug('[<tool-name>] execute() result:', JSON.stringify(result));
```

Run the failing case with `DEBUG=nova:* npm start` (or equivalent).

---

## Phase 4 — Diagnose intermittent issues

If the issue is not consistent:
- **Rate limits**: check if tool has retry/backoff logic; see `/nova-api-patterns`
- **Auth token expiry**: check if token is refreshed or re-read from env each request
- **Race condition**: check if any tool uses shared mutable state (global vars, module-level caches)
- **Environment drift**: compare `node --version` and `npm list` against expected versions

---

## Phase 5 — Fix and verify

Once root cause is identified:
1. Make the minimal fix
2. Add a test that would have caught this: `src/tools/<tool-name>/<tool-name>.test.ts`
3. Run: `npm test -- --testPathPattern=<tool-name>`
4. Remove any temporary debug logs added in Phase 3
5. Summarize the root cause and fix in one sentence for the commit message

---

## Common Nova failure patterns (quick reference)

| Symptom | Likely cause |
|---|---|
| Tool not found | Not registered in router, or name mismatch |
| Empty/undefined output | `execute()` returned `success: true` but no `data` |
| Always fails on first call | Missing env var / API key not loaded |
| Fails after N calls | Rate limit, no retry logic |
| Works locally, fails in prod | Hardcoded localhost URL, or missing env var in prod |
| Type error at runtime | Input shape mismatch between router and tool |
