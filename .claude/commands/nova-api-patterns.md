Nova conventions for calling external APIs. Apply these patterns in every tool that makes HTTP requests.

Context from $ARGUMENTS (if any): $ARGUMENTS

---

## Core wrapper: `novaFetch`

All external HTTP calls go through a single wrapper at `src/lib/api.ts`. Never call `fetch` directly from tool code.

```typescript
// src/lib/api.ts

export interface NovaFetchOptions extends RequestInit {
  retries?: number;       // default: 3
  retryDelay?: number;    // base ms between retries, default: 500
  timeoutMs?: number;     // default: 10000 (10s)
}

export class NovaApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: string,
  ) {
    super(message);
    this.name = 'NovaApiError';
  }
}

export async function novaFetch(
  url: string,
  options: NovaFetchOptions = {},
): Promise<Response> {
  const { retries = 3, retryDelay = 500, timeoutMs = 10_000, ...fetchOptions } = options;

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        signal: controller.signal,
      });

      // Rate limited — retry after Retry-After header or exponential backoff
      if (response.status === 429) {
        const retryAfter = Number(response.headers.get('Retry-After') ?? 0) * 1000;
        const wait = retryAfter || retryDelay * 2 ** attempt;
        if (attempt < retries) {
          await sleep(wait);
          continue;
        }
      }

      // Server errors (5xx) — retry
      if (response.status >= 500 && attempt < retries) {
        await sleep(retryDelay * 2 ** attempt);
        continue;
      }

      // Client errors (4xx except 429) — do NOT retry, throw immediately
      if (!response.ok) {
        const body = await response.text();
        throw new NovaApiError(
          `API request failed: ${response.status} ${response.statusText}`,
          response.status,
          body,
        );
      }

      return response;
    } catch (err) {
      if (err instanceof NovaApiError) throw err;
      // Network error or timeout — retry
      if (attempt < retries) {
        await sleep(retryDelay * 2 ** attempt);
        continue;
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }
  }

  throw new Error(`Request failed after ${retries} retries: ${url}`);
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}
```

---

## Auth handling

### Rule: never hardcode credentials

All API keys and tokens come from environment variables. Read them once when the client module loads.

```typescript
// src/tools/weather/client.ts

const API_KEY = process.env.WEATHER_API_KEY;
if (!API_KEY) throw new Error('WEATHER_API_KEY env var is not set');
```

### Naming convention for env vars

```
NOVA_<SERVICE>_API_KEY      ← for simple API key auth
NOVA_<SERVICE>_CLIENT_ID    ← for OAuth client credentials
NOVA_<SERVICE>_CLIENT_SECRET
NOVA_<SERVICE>_TOKEN        ← for static bearer tokens
```

Document every required env var in `.env.example` at the project root.

### Auth header patterns

```typescript
// API key in header
headers: { 'X-API-Key': API_KEY }

// Bearer token
headers: { Authorization: `Bearer ${TOKEN}` }

// API key in query string (when required by the API)
const url = new URL(BASE_URL);
url.searchParams.set('apikey', API_KEY);
```

### OAuth / token refresh

If an API uses short-lived tokens, create a `TokenManager` in `src/lib/auth/<service>.ts`:

```typescript
class TokenManager {
  private token: string | null = null;
  private expiresAt = 0;

  async getToken(): Promise<string> {
    if (this.token && Date.now() < this.expiresAt - 60_000) {
      return this.token; // still valid with 60s buffer
    }
    const { access_token, expires_in } = await fetchNewToken();
    this.token = access_token;
    this.expiresAt = Date.now() + expires_in * 1000;
    return this.token;
  }
}

export const tokenManager = new TokenManager(); // singleton
```

---

## Rate limit conventions

### Rule: respect `Retry-After` first, then use exponential backoff

The `novaFetch` wrapper handles this automatically for 429 responses. Tool code does not need to implement its own retry loop.

### Rule: for APIs with known rate limits, add a per-tool budget

For APIs with strict quotas (e.g., 10 req/sec), use a simple token bucket in the client:

```typescript
// src/tools/<service>/client.ts
import { RateLimiter } from '../../lib/rate-limiter';

const limiter = new RateLimiter({ requestsPerSecond: 10 });

export async function callApi(endpoint: string) {
  await limiter.acquire();
  return novaFetch(`${BASE_URL}${endpoint}`, { ... });
}
```

Implement `src/lib/rate-limiter.ts` as a token bucket or leaky bucket — do not use `sleep` loops.

---

## Error handling in tool code

Catch `NovaApiError` separately from generic errors so you can give the user a specific message:

```typescript
import { novaFetch, NovaApiError } from '../../lib/api';

async execute(input: Input): Promise<Output> {
  try {
    const response = await novaFetch(url, options);
    const data = await response.json();
    return { success: true, data };
  } catch (err) {
    if (err instanceof NovaApiError) {
      if (err.status === 401) return { success: false, error: 'Invalid API key. Check NOVA_<SERVICE>_API_KEY.' };
      if (err.status === 403) return { success: false, error: 'Access denied by the API.' };
      if (err.status === 404) return { success: false, error: 'Resource not found.' };
      return { success: false, error: `API error ${err.status}: ${err.body}` };
    }
    const message = err instanceof Error ? err.message : String(err);
    return { success: false, error: message };
  }
}
```

---

## Checklist for any new API integration

- [ ] All credentials in env vars, documented in `.env.example`
- [ ] HTTP calls go through `novaFetch`, not raw `fetch`
- [ ] No retry logic in tool code (handled by wrapper)
- [ ] `NovaApiError` caught and mapped to user-friendly messages
- [ ] Auth header pattern matches API requirements
- [ ] For OAuth: `TokenManager` singleton with 60s refresh buffer
- [ ] For rate-limited APIs: `RateLimiter` in client, not sleep loops
- [ ] Timeout set appropriately (default 10s; increase only for slow APIs like file uploads)
