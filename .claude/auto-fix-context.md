# Claude Auto-Fix Context

This file is read by the Claude auto-fix agent when CI fails on a `feat/*` branch.
It contains project-specific patterns, known SonarQube quirks, and test conventions
that are not obvious from the code alone.

Also read `CLAUDE.md` in the repo root for the full stack and coding philosophy.

---

## SonarQube Known Quirks

### S7924 — CSS Contrast (most common false failure)
SonarQube treats `rgba(r,g,b,alpha)` as fully opaque `rgb(r,g,b)` when computing
contrast ratios. It ignores the alpha channel entirely.

**Symptom:** CSS contrast violation on a color that looks fine in the browser.

**Fix:** Replace any semi-transparent background paired with same-hue text with
solid opaque equivalents. Examples:
```css
/* BEFORE — fails SonarQube even though it looks fine in browser */
background: rgba(220, 38, 38, 0.15);
color: #991b1b;

/* AFTER — opaque background SonarQube can evaluate correctly */
background: #fef2f2;
color: #991b1b;
```

Solid background replacements for common tints (light mode → dark mode):
- Red:    `rgba(220,38,38,0.15)`  → `#fef2f2`  /  `rgba(220,38,38,0.25)`  → `#3d1212`
- Amber:  `rgba(217,119,6,0.15)`  → `#fff7ed`  /  `rgba(217,119,6,0.25)`  → `#422006`
- Blue:   `rgba(37,99,235,0.15)`  → `#eff6ff`  /  `rgba(37,99,235,0.25)`  → `#1e3a8a`
- Hover states with `rgba` background + same-hue text → use the light mode tint above

### S5869 — Duplicate/Ambiguous Regex Character Class
Triggered when a hyphen inside `[...]` is positioned ambiguously (looks like a range).

**Symptom:** `re.sub(r"[A-Za-z0-9_.:-]+", ...)` flagged at the `:-` sequence.

**Fix:** Escape the hyphen: `[A-Za-z0-9_.\-:]+` or move it to the start/end of the class.

### S1854 — Useless Assignment
Variable assigned but never used. Common after a refactor removes callers.

**Fix:** Delete the assignment, or if it was a destructured parameter that should
be used, restore the call.

### S6481 — Context Provider Re-Creates Value Every Render
React context value object created inline re-renders all consumers on every render.

**Fix:** Wrap the value in `useMemo`:
```tsx
const value = useMemo(() => ({ open, setOpen }), [open, setOpen]);
<MyContext.Provider value={value}>
```

### S107 — Too Many Parameters (>4)
Function has more than 4 parameters. Usually flagged on utility functions.

**Fix:** Group related params into an options object — BUT only do this if the
function is not part of the AI editing feature set (those are handled separately
in PR #1459 and should not be touched).

---

## Test Conventions

### Backend (pytest)

- Tests live in `backend/tests/`
- Run with: `PYTHONPATH=. pytest tests/`
- Mock GitHub API calls — never make live requests in tests
- When mocking `_assert_session_owns_user`, patch it as `@patch("repos._assert_session_owns_user")`
- Mock repo objects must include ALL fields the endpoint accesses:
  ```python
  {
      "id": 1,
      "name": "repo-name",
      "full_name": "owner/repo-name",
      "private": False,
      "owner": {"login": "owner", "type": "User"},
  }
  ```
- When a function signature changes (parameter added/removed), update both the
  function definition AND all callers AND all test call sites
- `assert_called_once_with(...)` must exactly match the actual call signature —
  if a parameter was removed, remove it from the assertion too

### Frontend (Vitest)

- Tests live alongside source files as `*.test.tsx` / `*.test.ts`
- Run with: `npm run test:coverage` from `frontend/`
- Mock API modules at the top of the test file with `vi.mock('./api/...')`
- Component test IDs use `data-testid` attributes — check the component source
  for the exact testid string before asserting
- When a component prop is renamed or removed, update all test render calls
- `useMemo` is required for React context values in tests (S6481)

---

## Common Post-Refactor Breakage Patterns

These are the most frequent reasons CI fails after a code change:

1. **Parameter removed from a function** → tests still pass the old parameter as
   a keyword arg → `TypeError: unexpected keyword argument`
   - Fix: remove the kwarg from the test call and from `assert_called_once_with`

2. **Parameter added to a function** → callers and tests don't pass it
   - Fix: add it with a sensible default or update all call sites

3. **Import removed** → test file still imports the deleted export
   - Fix: remove the import from the test

4. **Mock missing a field** → backend endpoint accesses `repo["id"]` but mock
   only has `{"name": "...", "full_name": "..."}` → `KeyError`
   - Fix: add the missing field to the mock object

5. **CSS rgba + same-hue text** → SonarQube S7924 false failure (see above)
   - Fix: replace rgba background with solid opaque hex

---

## What NOT to Do

- Do not touch `backend/auth.py`, `backend/rate_limiter.py`,
  `backend/marketplace_webhooks.py` unless the failure is explicitly in those files
- Do not refactor working code while fixing a test
- Do not add error handling or fallbacks not required by the failure
- Do not modify AI editing features (`aiWorkflowUtils.ts`, related hooks/tests) —
  those are managed separately in PR #1459
- Do not open PRs — just commit and push; the pipeline re-runs automatically
