# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ |
| Older tags / forks | ❌ — please upgrade |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

1. Email the maintainers at the address listed in the repository profile / `CODEOWNERS`, **or**
2. Use GitHub **Private vulnerability reporting** (Security → Report a vulnerability), if enabled.

Include:

- Affected component (API, frontend, Premiere plugin, Docker image)
- Steps to reproduce
- Impact (data exposure, RCE, path traversal, API key leak, etc.)
- Suggested fix, if you have one

We aim to acknowledge reports within **5 business days**.

## Hardening tips for operators

- Never commit `.env` or API keys.
- Prefer `PLUGIN_ALLOWED_ROOTS` over `PLUGIN_ALLOW_ANY_LOCAL_PATH=true` in production.
- Keep Gemini / DeepSeek keys in secrets managers or Docker secrets — not in images.
- Expose API only on localhost or behind auth when running on shared machines.
- Treat uploaded media as untrusted; quarantine storage and limit disk quotas.
