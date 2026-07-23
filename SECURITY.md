# Security Policy

## Reporting a vulnerability

Please use a private [GitHub security advisory](https://github.com/guasi18587278913/creator-breakout-finder/security/advisories/new) instead of opening a public issue. Do not include live API keys, access tokens, or private account data in any report.

## API key boundary

Creator Breakout Finder follows a bring-your-own-key model:

- no TikHub key is bundled in the repository or frontend;
- `TIKHUB_API_KEY` is read by the server process from the local environment;
- `.env` and Streamlit secrets are ignored by Git;
- provider errors shown to users are sanitized;
- raw provider responses are normalized in memory and are not persisted.

If a key is ever committed or shown publicly, revoke it at the provider immediately. Removing it from the latest commit is not enough because it can remain in Git history.

## Public deployment

The included app is designed for local research. Before exposing a deployment that contains a server-side API key, add authentication, per-user quotas, rate limiting, request logging that excludes credentials, and provider spend alerts.
