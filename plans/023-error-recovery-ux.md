# Plan 023: Error & recovery UX

> **Drift check:** `ErrorAlert.svelte`, `extraction.svelte.ts`, `api/client.ts`, dictionaries

## Status

- **Priority:** P2  
- **Effort:** M  
- **Risk:** LOW  
- **Depends on:** none (pairs well with 022)  
- **Category:** ux / correctness-of-workflow  
- **Planned at:** `86a449a`, 2026-07-16  

## Why this matters

Failures are the highest-emotion moments. Today: one banner for “videoExtractError”, generic advice, dismiss-only. Toasts disappear. No retry, no deep-link to cookies when the message mentions login, no “try as gallery” when auto failed both ways.

## Current state

- `appStore.videoExtractError` + `ErrorAlert` (dismiss only).  
- Server already returns human messages via `classify_extraction_error` / gallery messages.  
- Client may only toast in some paths.

## Scope

**In scope:**

- `ErrorAlert.svelte` → richer `ExtractErrorBanner`  
- `extraction.svelte.ts` — store last failed URL + error + optional code  
- Minimal types for `lastExtractFailure`  
- i18n for action buttons  

**Out of scope:** Changing server error codes (optional later: add machine-readable `code` field).

## Steps

### Step 1: Model last failure

On extract failure (when not silent):

```ts
// app-state or extraction controller
lastFailure: {
  url: string;
  message: string;
  mode: 'auto' | 'video' | 'gallery';
  at: number;
} | null
```

### Step 2: Banner actions

Always:

- **Dismiss**  
- **Retry** → re-run extract with same URL/mode  

Heuristics on message text (case-insensitive), until server codes exist:

- contains login / cookie / sign in / 401 / 403 → **Open cookies** (opens prefs sheet on Cookies tab if 021 landed, else opens prefs)  
- mode was video or auto → **Try as gallery**  
- mode was gallery → **Try as video**

### Step 3: Keep toast for batch item failures; banner for “final” single failures

Don’t double-spam: if banner is set, skip duplicate error toast (or toast only for batch multi).

### Step 4: Verify

Manual: invalid URL, private video message, cancel mid-flight (should not show permanent error).

`npm run check`.

## Done criteria

1. User can retry last URL one click.  
2. Cookie-related failures can open settings.  
3. Cancel/abort doesn’t leave a sticky false error.  
4. EN+FA strings for new buttons.

## STOP conditions

- Don’t parse HTML from server. Only plain text messages.  
- Don’t store cookie contents in the failure object.
