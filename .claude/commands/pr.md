---
description: "Create a GitHub PR from current branch — discovers templates, analyzes changes, pushes"
argument-hint: "[base-branch] (default: main/master)"
---

# Create Pull Request

**Input**: `$ARGUMENTS` — optional base branch name and/or flags (e.g., `--draft`).

**Parse `$ARGUMENTS`**:
- Extract any recognized flags (`--draft`)
- Treat remaining text as the base branch name
- Default base branch to `main` or `master` if none specified

---

## Phase 1 — VALIDATE

```bash
git branch --show-current
git status --short
git log origin/<base>..HEAD --oneline
```

| Check | Condition | Action if Failed |
|---|---|---|
| Not on base branch | Current branch != base | Stop: "Switch to a feature branch first." |
| Clean working directory | No uncommitted changes | Warn: "You have uncommitted changes." |
| Has commits ahead | log not empty | Stop: "No commits ahead. Nothing to PR." |
| No existing PR | `gh pr list --head <branch>` empty | Stop: "PR already exists." |

## Phase 2 — DISCOVER

### PR Template

Search in order:
1. `.github/PULL_REQUEST_TEMPLATE.md`
2. `.github/pull_request_template.md`
3. `docs/pull_request_template.md`

### Commit Analysis

```bash
git log origin/<base>..HEAD --format="%h %s" --reverse
```

Determine:
- **PR title**: conventional commit format (`feat: ...`, `fix: ...`)
- **Change summary**: group commits by type/area

### File Analysis

```bash
git diff origin/<base>..HEAD --stat
git diff origin/<base>..HEAD --name-only
```

## Phase 3 — PUSH

```bash
git push -u origin HEAD
```

If push fails due to divergence, suggest rebase.

## Phase 4 — CREATE

Use template if found, otherwise default format:

```markdown
## Summary
<1-2 sentence description>

## Changes
<bulleted list grouped by area>

## Testing
<how changes were tested>

## Related Issues
<linked issues or "None">
```

```bash
gh pr create \
  --title "<PR title>" \
  --base <base-branch> \
  --body "<PR body>"
```

## Phase 5 — OUTPUT

```
PR #<number>: <title>
URL: <url>
Branch: <head> → <base>
Changes: +<additions> -<deletions> across <changedFiles> files

Next steps:
  - gh pr view <number> --web   → open in browser
  - /code-review <number>       → review the PR
  - gh pr merge <number>        → merge when ready
```
