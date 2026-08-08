# Contributing to MediaPull

## Prerequisites

- Node 18+ and npm
- Python 3.10+
- yt-dlp and gallery-dl on your PATH

## Local setup

**Client**
```bash
cd client
npm install
npm run dev
```

**Server**
```bash
cd server
pip install -r requirements.txt
cp .env.example .env   # fill in the values
uvicorn app.main:app --reload
```

## Before you submit

```bash
# client
npm run check    # type-check
npm run test     # vitest

# server
ruff check app/
pytest
```

All checks must pass. Open a PR against `main` with a short description of what changed and why. Use the PR template.

## Commit style

```
<scope>: short description
```

Examples: `feat: add X`, `fix: correct Y in Z`, `client: update A`, `server: adjust B`. Lowercase, no period at the end.

## Reporting bugs

Use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md). Include server logs or browser console output when relevant.
