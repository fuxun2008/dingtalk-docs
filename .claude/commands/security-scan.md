---
description: Run security scan against the current project for secrets, vulnerabilities, and unsafe patterns.
argument-hint: "[path] (default: current directory)"
---

# Security Scan

Run a comprehensive security scan against the current project.

**Input**: `$ARGUMENTS` — optional target path (defaults to current directory).

## Phase 1 — Secret Detection

Search for hardcoded secrets and credentials:

```bash
# API keys and tokens
grep -rn "sk-\|api[_-]key\|secret[_-]key\|access[_-]token\|private[_-]key" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" --include="*.env*" . 2>/dev/null

# Common secret patterns
grep -rn "password\s*=\s*['\"]" --include="*.ts" --include="*.js" --include="*.json" . 2>/dev/null

# AWS/Cloud credentials
grep -rn "AKIA\|aws_secret" --include="*.ts" --include="*.js" --include="*.env*" . 2>/dev/null
```

## Phase 2 — Dependency Vulnerabilities

```bash
# npm audit
npm audit --json 2>/dev/null || pnpm audit --json 2>/dev/null

# Check for outdated packages with known vulnerabilities
npm outdated 2>/dev/null
```

## Phase 3 — Code Pattern Analysis

Check each source file for:

| Category | Pattern | Severity |
|---|---|---|
| **XSS** | `dangerouslySetInnerHTML`, unescaped user input in DOM | CRITICAL |
| **Injection** | String concatenation in queries/commands | CRITICAL |
| **Auth** | Missing authentication checks on routes | HIGH |
| **CSRF** | Forms without CSRF tokens | HIGH |
| **Path Traversal** | Unsanitized file path operations | HIGH |
| **Exposure** | Sensitive data in console.log or error messages | MEDIUM |
| **Insecure** | HTTP URLs (not HTTPS) for API calls | MEDIUM |
| **Eval** | `eval()`, `Function()`, `setTimeout(string)` | HIGH |

## Phase 4 — Permission & Configuration

Check for:
- `.env` files committed to git (should be in `.gitignore`)
- Overly permissive CORS settings
- Debug mode enabled in production configs
- Missing security headers

## Phase 5 — Report

```
SECURITY SCAN REPORT
════════════════════════════════════

Target: <path>
Files scanned: <count>

CRITICAL: <count>
HIGH:     <count>
MEDIUM:   <count>
LOW:      <count>

────────────────────────────────────
FINDINGS:

[CRITICAL] Hardcoded API key
  File: src/config.ts:15
  Fix: Move to environment variable

[HIGH] XSS vulnerability
  File: src/components/Comment.tsx:42
  Fix: Sanitize user input before rendering

────────────────────────────────────
RECOMMENDATIONS:
1. ...
2. ...
```

## Severity Definitions

| Level | Meaning |
|---|---|
| **CRITICAL** | Exploitable vulnerability, data exposure, hardcoded secrets |
| **HIGH** | Security weakness likely to be exploitable |
| **MEDIUM** | Defense-in-depth issue, not immediately exploitable |
| **LOW** | Best practice suggestion |
