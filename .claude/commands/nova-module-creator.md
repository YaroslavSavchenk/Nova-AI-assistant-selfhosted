You are scaffolding a new Nova tool module. Follow these steps precisely.

## Step 1 — Gather information

Ask the user for the following if not already provided in $ARGUMENTS:
- **Module name** (e.g., `weather`, `calendar`, `search`) — becomes the tool identifier
- **Description** — one sentence explaining what this tool does for the user
- **Input parameters** — names, types, and whether each is required or optional
- **External API?** — yes/no; if yes, which service and what auth method (API key, OAuth, bearer token)

## Step 2 — Determine file locations

Nova module structure (create directories as needed):
```
src/
  tools/
    <module-name>/
      index.ts          ← tool implementation
      types.ts          ← input/output type definitions
      client.ts         ← API client (only if external API involved)
  router/
    index.ts            ← tool router (register new tool here)
```

## Step 3 — Scaffold the types file

Create `src/tools/<module-name>/types.ts`:

```typescript
export interface <ModuleName>Input {
  // required parameters first
  param: string;
  // optional parameters
  optionalParam?: string;
}

export interface <ModuleName>Output {
  success: boolean;
  data?: unknown;
  error?: string;
}
```

## Step 4 — Scaffold the tool implementation

Create `src/tools/<module-name>/index.ts`:

```typescript
import type { <ModuleName>Input, <ModuleName>Output } from './types';

export const <moduleName>Tool = {
  name: '<module-name>',
  description: '<one-sentence description>',

  async execute(input: <ModuleName>Input): Promise<<ModuleName>Output> {
    try {
      // validate required inputs
      if (!input.param) {
        return { success: false, error: 'param is required' };
      }

      // core logic here

      return { success: true, data: result };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return { success: false, error: message };
    }
  },
};
```

## Step 5 — Scaffold the API client (if external API)

Create `src/tools/<module-name>/client.ts` using Nova API patterns:

```typescript
import { novaFetch } from '../../lib/api';

const BASE_URL = 'https://api.example.com';

export async function fetchData(endpoint: string, apiKey: string) {
  return novaFetch(`${BASE_URL}${endpoint}`, {
    headers: { Authorization: `Bearer ${apiKey}` },
  });
}
```

Reference `/nova-api-patterns` for retry logic, auth handling, and rate limit conventions.

## Step 6 — Register in the tool router

Open `src/router/index.ts` and add the new tool:

```typescript
import { <moduleName>Tool } from '../tools/<module-name>';

// Add to the tools map:
const tools = {
  // ... existing tools ...
  '<module-name>': <moduleName>Tool,
};
```

## Step 7 — Verify the implementation

After scaffolding, confirm:
- [ ] `types.ts` defines both input and output interfaces
- [ ] `execute()` always returns `{ success: boolean }` — never throws to the caller
- [ ] All required inputs are validated at the top of `execute()`
- [ ] Error messages are human-readable strings
- [ ] Tool is registered in `src/router/index.ts`
- [ ] If external API: `client.ts` exists and uses `novaFetch` wrapper

Then run: `npm run typecheck && npm test -- --testPathPattern=<module-name>`
