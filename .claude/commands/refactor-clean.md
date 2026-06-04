---
description: Safely identify and remove dead code with verification after each change.
---

# Refactor Clean

Safely identify and remove dead code with verification at every step.

## Step 1: Detect Dead Code

Run analysis tools based on project type:

| Tool | What It Finds | Command |
|------|--------------|---------|
| knip | Unused exports, files, dependencies | `npx knip` |
| depcheck | Unused npm dependencies | `npx depcheck` |
| ts-prune | Unused TypeScript exports | `npx ts-prune` |

If no tool is available, use Grep to find exports with zero imports.

## Step 2: Categorize Findings

| Tier | Examples | Action |
|------|----------|--------|
| **SAFE** | Unused utilities, internal functions | Delete with confidence |
| **CAUTION** | Components, API routes, middleware | Verify no dynamic imports |
| **DANGER** | Config files, entry points, types | Investigate before touching |

## Step 3: Safe Deletion Loop

For each SAFE item:

1. **Run full test/build** — Establish baseline
2. **Delete the dead code** — Surgical removal
3. **Re-run test/build** — Verify nothing broke
4. **If fails** — Immediately revert and skip this item
5. **If passes** — Move to next item

## Step 4: Handle CAUTION Items

Before deleting:
- Search for dynamic imports: `import()`, `require()`
- Search for string references in configs
- Check if exported from a public package API
- Verify no external consumers

## Step 5: Consolidate Duplicates

After removing dead code, look for:
- Near-duplicate functions (>80% similar) — merge into one
- Redundant type definitions — consolidate
- Wrapper functions that add no value — inline them
- Re-exports that serve no purpose — remove indirection

## Step 6: Summary

```
Dead Code Cleanup
──────────────────────────────
Deleted:   X unused functions
           X unused files
           X unused dependencies
Skipped:   X items (tests/build failed)
Saved:     ~X lines removed
──────────────────────────────
All checks passing: PASS
```

## Rules

- **Never delete without running build/tests first**
- **One deletion at a time** — Atomic changes make rollback easy
- **Skip if uncertain** — Better to keep dead code than break production
- **Don't refactor while cleaning** — Separate concerns
