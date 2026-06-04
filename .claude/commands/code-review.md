---
description: Code review — local uncommitted changes or GitHub PR (pass PR number/URL for PR mode)
argument-hint: "[pr-number | pr-url | blank for local review]"
---

# Code Review

**Input**: $ARGUMENTS

## Mode Selection

If `$ARGUMENTS` contains a PR number, PR URL, or `--pr`:
→ Jump to **PR Review Mode** below.

Otherwise:
→ Use **Local Review Mode**.

---

## Local Review Mode

Comprehensive security and quality review of uncommitted changes.

### Phase 1 — GATHER

```bash
git diff --name-only HEAD
```

If no changed files, stop: "Nothing to review."

### Phase 2 — REVIEW

Read each changed file in full. Check for:

**Security Issues (CRITICAL):**
- Hardcoded credentials, API keys, tokens
- SQL injection vulnerabilities
- XSS vulnerabilities
- Missing input validation
- Insecure dependencies
- Path traversal risks

**Code Quality (HIGH):**
- Functions > 50 lines
- Files > 800 lines
- Nesting depth > 4 levels
- Missing error handling
- console.log statements
- TODO/FIXME comments

**Best Practices (MEDIUM):**
- Mutation patterns (use immutable instead)
- Missing tests for new code
- Accessibility issues (a11y)

### Phase 3 — REPORT

Generate report with:
- Severity: CRITICAL, HIGH, MEDIUM, LOW
- File location and line numbers
- Issue description
- Suggested fix

Block commit if CRITICAL or HIGH issues found.

---

## PR Review Mode

Comprehensive GitHub PR review.

### Phase 1 — FETCH

Parse input to determine PR:

| Input | Action |
|---|---|
| Number (e.g. `42`) | Use as PR number |
| URL (`github.com/.../pull/42`) | Extract PR number |
| Branch name | Find PR via `gh pr list --head <branch>` |

```bash
gh pr view <NUMBER> --json number,title,body,author,baseRefName,headRefName,changedFiles,additions,deletions
gh pr diff <NUMBER>
```

### Phase 2 — CONTEXT

1. **Project rules** — Read `CLAUDE.md` and any contributing guidelines
2. **PR intent** — Parse PR description for goals, linked issues
3. **Changed files** — List all modified files and categorize by type

### Phase 3 — REVIEW

Read each changed file **in full** (not just diff hunks).

Apply the review checklist:

| Category | What to Check |
|---|---|
| **Correctness** | Logic errors, off-by-ones, null handling, edge cases |
| **Type Safety** | Type mismatches, unsafe casts, `any` usage |
| **Pattern Compliance** | Matches project conventions (naming, structure, imports) |
| **Security** | Injection, auth gaps, secret exposure, XSS |
| **Performance** | N+1 queries, unbounded loops, memory leaks |
| **Completeness** | Missing tests, missing error handling |
| **Maintainability** | Dead code, magic numbers, deep nesting |

Severity levels:

| Severity | Meaning | Action |
|---|---|---|
| **CRITICAL** | Security vulnerability or data loss risk | Must fix before merge |
| **HIGH** | Bug or logic error | Should fix before merge |
| **MEDIUM** | Code quality issue | Fix recommended |
| **LOW** | Style nit | Optional |

### Phase 4 — VALIDATE

Run available validation commands based on project type:

```bash
# TypeScript projects
npx tsc --noEmit 2>/dev/null
npm run lint 2>/dev/null
npm test 2>/dev/null
```

### Phase 5 — DECIDE

| Condition | Decision |
|---|---|
| Zero CRITICAL/HIGH issues, validation passes | **APPROVE** |
| Only MEDIUM/LOW issues | **APPROVE** with comments |
| Any HIGH issues or validation failures | **REQUEST CHANGES** |
| Any CRITICAL issues | **BLOCK** |

### Phase 6 — PUBLISH

```bash
# If APPROVE
gh pr review <NUMBER> --approve --body "<summary>"

# If REQUEST CHANGES
gh pr review <NUMBER> --request-changes --body "<summary with required fixes>"
```

### Phase 7 — OUTPUT

```
PR #<NUMBER>: <TITLE>
Decision: <APPROVE|REQUEST_CHANGES|BLOCK>
Issues: <critical> critical, <high> high, <medium> medium, <low> low
Validation: <pass>/<total> checks passed
```
