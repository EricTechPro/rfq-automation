---
name: learning
description: Extract anti-patterns from bug fixes, scan the entire codebase for all instances, fix them, and create lasting prevention mechanisms (utilities, decorators, conventions) so the bug class never recurs.
---

# Learning Loop

Automate the full cycle: extract anti-pattern from a bug fix → find all instances across the codebase → fix them → create a lasting prevention mechanism so the bug class never recurs.

## When to Use This Skill

- **After fixing a bug** — Apply the same fix everywhere it occurs
- **After noticing a repeated pattern** — Standardize it codebase-wide
- **After creating a utility/decorator** — Find all places that should adopt it
- **When a code review reveals a systemic issue** — Fix the root cause, not just the symptom

### Real Examples This Skill Would Catch in This Codebase

| Anti-Pattern | Prevention Created | Files Affected |
|---|---|---|
| Bare `except:` or `except Exception:` swallowing scraper errors | `safe_scrape()` context manager utility | scrapers/, core.py |
| Browser not closed on exception path | `async with browser_context()` wrapper | scrapers/dibbs.py, scrapers/wbparts.py |
| Missing `handle_consent_banner()` before DIBBS scraping | Lint check + CLAUDE.md convention | scrapers/dibbs.py, scrapers/dibbs_date.py |
| Raw string NSN not validated before use | `validate_nsn()` decorator/guard | core.py, cli.py, api.py |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `scope` | `full` | `full` (all 5 phases), `scan-only` (phases 1-2), `prevent-only` (phases 4-5) |
| `auto-commit` | `true` | Create commits after fix and prevention phases |
| `skip-confirm` | `false` | Skip user checkpoints (not recommended) |

## Architecture

```
ORCHESTRATOR (main session - manages state only)
│
├── Phase 1: ANALYZE (inline)
│   └── Extract anti-pattern from conversation + git diff
│
├── Phase 2: SCAN (3 parallel sub-agents, fresh 200k context each)
│   ├── feature-dev:code-explorer → scrapers/ (DIBBS, WBParts, date scrapers)
│   ├── feature-dev:code-explorer → services/ & utils/ (Firecrawl, helpers)
│   └── feature-dev:code-explorer → core.py, cli.py, api.py, app.py (interfaces)
│
│   └── USER CHECKPOINT: confirm scan results
│
├── Phase 3: FIX (single sub-agent, fresh 200k context)
│   └── general-purpose → edit files, run tests
│
├── Phase 4: PREVENT (decision tree + sub-agent)
│   ├── Strategy A: Create utility/abstraction (best) — decorator, context manager, helper function
│   ├── Strategy B: Type constraint — Pydantic validator, runtime check
│   ├── Strategy C: Add CLAUDE.md convention with Do/Don't table
│   ├── Strategy D: Update existing pattern in project docs
│   └── Strategy E: Add to test suite as regression test
│   └── USER CHECKPOINT: confirm strategy before implementing
│
└── Phase 5: SUMMARY (inline)
    └── Report what was done

STATE FILE: .learning/state.json
```

---

## Workflow

### Step 0: Initialize State

Create/update the state file at `.learning/state.json`:

```json
{
  "phase": "analyze",
  "status": "in_progress",
  "startedAt": "2026-02-08T10:00:00Z",
  "branchName": "feature/example",
  "antiPattern": null,
  "scanResults": [],
  "fixedFiles": [],
  "preventionStrategy": null,
  "preventionDetails": null,
  "commits": [],
  "parameters": {
    "scope": "full",
    "autoCommit": true,
    "skipConfirm": false
  }
}
```

**Resume support:** If `.learning/state.json` already exists and `status` is `in_progress`, ask the user:

```
AskUserQuestion:
  question: "Found an incomplete learning session. Resume where you left off?"
  header: "Resume?"
  options:
    - label: "Resume"
      description: "Continue from phase: {state.phase}"
    - label: "Start fresh"
      description: "Discard previous session and start over"
```

If resuming, skip to the phase indicated by `state.phase`.

### Phase 1: ANALYZE (Inline)

Extract the anti-pattern from the current conversation context and recent git changes.

#### Step 1.1: Gather Context

```bash
# Get recent diff (uncommitted + last commit)
git diff --no-color
git diff HEAD~1 --no-color
git log --oneline -5
```

#### Step 1.2: Extract Anti-Pattern

Analyze the conversation history and git diff to identify:

1. **What was the bug/issue?** — The specific problem that was fixed
2. **What was the anti-pattern?** — The code pattern that caused the bug
3. **What is the correct pattern?** — The replacement code pattern
4. **What is the search signature?** — Grep-able patterns to find other instances

Structure the extraction as:

```json
{
  "bugDescription": "Browser instance leaked when scraper threw an exception",
  "antiPattern": {
    "description": "Browser launched without try/finally cleanup, relying on happy-path close",
    "codeExample": "browser = await playwright.chromium.launch()\npage = await browser.new_page()\nawait page.goto(url)\n# ... scraping logic ...\nawait browser.close()",
    "searchPatterns": [
      "await playwright\\.chromium\\.launch",
      "browser\\.close\\(\\)",
      "await browser\\.new_page"
    ]
  },
  "correctPattern": {
    "description": "Use async context manager or try/finally to guarantee browser cleanup",
    "codeExample": "async with async_playwright() as p:\n    browser = await p.chromium.launch()\n    try:\n        page = await browser.new_page()\n        # ... scraping logic ...\n    finally:\n        await browser.close()"
  }
}
```

#### Step 1.3: Confirm Anti-Pattern (unless skip-confirm)

Present the extracted anti-pattern to the user for validation:

```
AskUserQuestion:
  question: "I identified this anti-pattern from your recent fix. Is this correct?"
  header: "Anti-pattern"
  options:
    - label: "Correct, proceed (Recommended)"
      description: "{antiPattern.description}"
    - label: "Needs adjustment"
      description: "Let me refine the pattern before scanning"
```

If "Needs adjustment", ask the user to describe the pattern more precisely, then re-extract.

Update state:
```json
{
  "phase": "scan",
  "antiPattern": { ... }
}
```

**If `scope` is `prevent-only`:** Skip to Phase 4.

---

### Phase 2: SCAN (3 Parallel Sub-Agents)

Find all instances of the anti-pattern across the codebase.

#### Step 2.1: Spawn 3 Scanner Agents IN PARALLEL

Use the Task tool to spawn all 3 scanners simultaneously with `run_in_background: true`.

Each scanner receives:
1. The anti-pattern description, code example, and search patterns
2. The correct pattern for reference
3. Their specific scan scope
4. Instructions to return JSON findings

**All scanners must return findings in this format:**
```json
[{
  "file": "scrapers/dibbs.py",
  "line": 45,
  "matchedCode": "browser = await playwright.chromium.launch()",
  "context": "DIBBS scraper launch without try/finally",
  "confidence": "high|medium|low",
  "suggestedFix": "Wrap in try/finally with browser.close() in finally block"
}]
```

**MAX 30 findings per scanner. Focus on high-confidence matches.**

##### Scanner 1: Scrapers
```
Sub-agent: feature-dev:code-explorer

You are scanning for instances of an anti-pattern across web scraper modules.

## Anti-Pattern to Find
**Description:** {antiPattern.description}
**Code Example (BAD):**
```
{antiPattern.codeExample}
```

**Correct Pattern (GOOD):**
```
{correctPattern.codeExample}
```

## Search Patterns (Regex)
{antiPattern.searchPatterns as list}

## Scan Scope
Search these files thoroughly:
- `scrapers/dibbs.py` — DIBBS scraper (Playwright + DoD consent banner)
- `scrapers/dibbs_date.py` — Date-based NSN listing scraper
- `scrapers/wbparts.py` — WBParts scraper (Playwright)
- Any other files in `scrapers/`

## Instructions
1. Use Grep with each search pattern against the scan scope
2. For each match, read surrounding context (5-10 lines) to confirm it's a real instance
3. Skip the file that was ALREADY FIXED in the original bug fix
4. Rate confidence:
   - **high**: Exact match of the anti-pattern
   - **medium**: Similar pattern that likely has the same issue
   - **low**: Structurally similar but might be intentional
5. Suggest the specific fix for each instance

Return findings as JSON array. MAX 30 findings.
Do NOT return false positives — when in doubt, mark as "low" confidence.
```

##### Scanner 2: Services & Utilities
```
Sub-agent: feature-dev:code-explorer

You are scanning for instances of an anti-pattern across service and utility modules.

## Anti-Pattern to Find
**Description:** {antiPattern.description}
**Code Example (BAD):**
```
{antiPattern.codeExample}
```

**Correct Pattern (GOOD):**
```
{correctPattern.codeExample}
```

## Search Patterns (Regex)
{antiPattern.searchPatterns as list}

## Scan Scope
Search these files thoroughly:
- `services/firecrawl.py` — Firecrawl API client (search + extract)
- `utils/helpers.py` — NSN formatting, file I/O, timestamps
- Any other files in `services/` or `utils/`

## Instructions
1. Use Grep with each search pattern against the scan scope
2. For each match, read surrounding context (5-10 lines) to confirm it's a real instance
3. Skip the file that was ALREADY FIXED in the original bug fix
4. Rate confidence:
   - **high**: Exact match of the anti-pattern
   - **medium**: Similar pattern that likely has the same issue
   - **low**: Structurally similar but might be intentional
5. Suggest the specific fix for each instance

Return findings as JSON array. MAX 30 findings.
Do NOT return false positives — when in doubt, mark as "low" confidence.
```

##### Scanner 3: Interfaces & Core Logic
```
Sub-agent: feature-dev:code-explorer

You are scanning for instances of an anti-pattern across the application interfaces and core logic.

## Anti-Pattern to Find
**Description:** {antiPattern.description}
**Code Example (BAD):**
```
{antiPattern.codeExample}
```

**Correct Pattern (GOOD):**
```
{correctPattern.codeExample}
```

## Search Patterns (Regex)
{antiPattern.searchPatterns as list}

## Scan Scope
Search these files thoroughly:
- `core.py` — Shared business logic (scrape_nsn, scrape_batch, result flattening)
- `cli.py` — Batch processor with resume capability
- `api.py` — FastAPI REST endpoints (Phase 2 date-based scraping)
- `app.py` — Streamlit UI
- `models.py` — Pydantic models
- `config.py` — Config loader
- `main.py` — Unified entry point

## Instructions
1. Use Grep with each search pattern against the scan scope
2. For each match, read surrounding context (5-10 lines) to confirm it's a real instance
3. Skip the file that was ALREADY FIXED in the original bug fix
4. Rate confidence:
   - **high**: Exact match of the anti-pattern
   - **medium**: Similar pattern that likely has the same issue
   - **low**: Structurally similar but might be intentional
5. Suggest the specific fix for each instance

Return findings as JSON array. MAX 30 findings.
Do NOT return false positives — when in doubt, mark as "low" confidence.
```

#### Step 2.2: Collect and Aggregate Results

After all agents complete:

1. **Use TaskOutput** to retrieve results from each agent
2. **Parse JSON findings** from each response
3. **Handle errors** — If an agent fails, log it and continue with others
4. **Deduplicate** — Remove findings pointing to the same file:line
5. **Sort by confidence** — high first, then medium, then low
6. **Filter out already-fixed file** — Remove any findings in the file from the original fix

#### Step 2.3: User Checkpoint (unless skip-confirm)

Present scan results grouped by confidence:

```markdown
## Scan Results

Found **{total}** instances of the anti-pattern across the codebase:

### High Confidence ({count})
| File | Line | Matched Code |
|------|------|-------------|
| {file} | {line} | `{matchedCode}` |

### Medium Confidence ({count})
| File | Line | Matched Code |
|------|------|-------------|
| {file} | {line} | `{matchedCode}` |

### Low Confidence ({count})
| File | Line | Matched Code |
|------|------|-------------|
| {file} | {line} | `{matchedCode}` |
```

Then ask:

```
AskUserQuestion:
  question: "Which instances should be fixed?"
  header: "Fix scope"
  options:
    - label: "High confidence only (Recommended)"
      description: "Fix {highCount} instances with exact pattern matches"
    - label: "High + Medium"
      description: "Fix {highCount + mediumCount} instances"
    - label: "All instances"
      description: "Fix all {total} instances including low confidence"
    - label: "None — skip to prevention"
      description: "Don't fix existing instances, just create prevention mechanism"
```

Update state:
```json
{
  "phase": "fix",
  "scanResults": [...],
  "approvedScope": "high|high+medium|all|none"
}
```

**If `scope` is `scan-only`:** Stop here. Present results and exit.

---

### Phase 3: FIX (Single Sub-Agent)

Apply the correct pattern to all approved instances.

#### Step 3.1: Generate Fix Prompt

Create a comprehensive fix prompt for the approved instances:

```markdown
# Anti-Pattern Fix — Apply Across Codebase

You are fixing instances of an anti-pattern found across the codebase. Work through each file systematically.

## Anti-Pattern
**Description:** {antiPattern.description}
**BAD:**
```
{antiPattern.codeExample}
```

**GOOD:**
```
{correctPattern.codeExample}
```

## Instructions
1. Read each file before making changes
2. Apply the correct pattern to each instance
3. Ensure imports are added/updated as needed
4. Do NOT change any other code in the files
5. After all fixes, run: `python3 test_scraper.py`

## Instances to Fix

### File: {file1}
**Line {line}:** `{matchedCode}`
**Context:** {context}
**Fix:** {suggestedFix}

### File: {file2}
...

## Verification
After completing all fixes, run:
```bash
python3 test_scraper.py
```
Report any errors encountered.
```

#### Step 3.2: Spawn Fix Agent

```
Sub-agent: general-purpose
run_in_background: false

{The fix prompt generated in Step 3.1}
```

#### Step 3.3: Commit Changes (if auto-commit enabled)

If `auto-commit: true` and fixes were made:

```bash
git add {list of fixed files by name}
git commit -m "fix: replace {antiPattern short name} across codebase ({count} instances)

Applied correct pattern to all instances found by /learning scan.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

Update state:
```json
{
  "phase": "prevent",
  "fixedFiles": [...],
  "commits": ["abc1234"]
}
```

---

### Phase 4: PREVENT (Decision Tree + Sub-Agent)

Create a lasting mechanism so the anti-pattern never recurs.

#### Step 4.1: Choose Prevention Strategy

Evaluate the anti-pattern against this decision tree (in priority order):

**Strategy A: Create utility/abstraction** (BEST — code-level prevention)
- Use when: The correct pattern can be encapsulated in a reusable function, decorator, or context manager
- Examples: `async_browser_context()`, `safe_scrape()`, `rate_limited()` decorator, `validate_nsn()` guard
- Creates: New file in `utils/` or addition to `utils/helpers.py`

**Strategy B: Type constraint or runtime check**
- Use when: The anti-pattern can be caught by Pydantic validators or runtime assertions
- Examples: Pydantic field validators, `@validate_call` decorator, custom Pydantic types
- Creates: Validator in `models.py` or new validation utility

**Strategy C: Add CLAUDE.md convention with Do/Don't table**
- Use when: The pattern is a coding convention that can't be enforced by code
- Examples: Browser cleanup patterns, Firecrawl rate limiting conventions, error handling standards
- Creates: New section in CLAUDE.md

**Strategy D: Update existing pattern documentation**
- Use when: Existing documentation should cover this pattern
- Creates: Addition to CLAUDE.md or project docs

**Strategy E: Add regression test**
- Use when: The anti-pattern can be detected by a test
- Examples: Test that verifies all browser launches have corresponding close calls, test that validates NSN format
- Creates: New test in `test_scraper.py` or new test file

#### Step 4.2: User Checkpoint (unless skip-confirm)

Present the chosen strategy:

```
AskUserQuestion:
  question: "How should we prevent this anti-pattern from recurring?"
  header: "Prevention"
  options:
    - label: "Strategy {X}: {description} (Recommended)"
      description: "{Details of what will be created/modified}"
    - label: "Strategy {Y}: {description}"
      description: "{Details of what will be created/modified}"
    - label: "Skip prevention"
      description: "Fixes are enough, no prevention mechanism needed"
```

#### Step 4.3: Implement Prevention

Based on the chosen strategy, spawn a sub-agent to implement it.

##### Strategy A: Create Utility/Abstraction

```
Sub-agent: general-purpose
run_in_background: false

Create a reusable {utility function|decorator|context manager} that encapsulates the correct pattern and makes the anti-pattern unnecessary.

## Anti-Pattern Being Prevented
**BAD:** {antiPattern.codeExample}
**GOOD:** {correctPattern.codeExample}

## What to Create
- File: {suggested file path}
- Name: {suggested name}
- Purpose: {one-line description}

## Requirements
1. Follow existing patterns in the codebase (check similar files in the target directory)
2. Use proper type hints
3. The utility should make it HARDER to use the anti-pattern than the correct pattern
4. After creating, run: `python3 test_scraper.py`

## Also Update
- Add a CLAUDE.md convention entry documenting the utility (use the Do/Don't table format)
```

##### Strategy C: CLAUDE.md Convention

Add a new convention section to CLAUDE.md using this template:

```markdown
### {Convention Name}

**REQUIRED: {One imperative sentence stating the rule}.**

| Do | Don't |
|----|-------|
| `{correct pattern}` | `{anti-pattern}` |

{1-2 sentence explanation of why this matters.}
```

**Placement rules for CLAUDE.md:**
- Find the most relevant existing section (e.g., "Scraper Notes", "Architecture")
- Add the new convention WITHIN that section, not as a new top-level section
- If no existing section fits, add under a new subsection of the closest match

#### Step 4.4: Commit Prevention (if auto-commit enabled)

If `auto-commit: true` and prevention was created:

```bash
git add {list of created/modified files by name}
git commit -m "docs: add {prevention name} to prevent {anti-pattern short name}

Prevention mechanism created by /learning skill.

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

Use `feat:` prefix instead of `docs:` if Strategy A or B (code was created).

Update state:
```json
{
  "phase": "summary",
  "preventionStrategy": "A|B|C|D|E",
  "preventionDetails": {
    "strategy": "A",
    "filesCreated": ["utils/browser_context.py"],
    "filesModified": ["CLAUDE.md"],
    "description": "Created async_browser_context() utility"
  },
  "commits": ["abc1234", "def5678"]
}
```

---

### Phase 5: SUMMARY (Inline)

Present the final report:

```markdown
# Learning Complete

## Anti-Pattern
**{antiPattern.description}**

## Scan Results
| Confidence | Found | Fixed |
|------------|-------|-------|
| High | {count} | {count} |
| Medium | {count} | {count} |
| Low | {count} | {count} |
| **Total** | **{total}** | **{totalFixed}** |

## Files Fixed
{list of files with brief description of change}

## Prevention
**Strategy {X}: {description}**
{What was created/modified}

## Commits
- `{hash1}` — fix: replace {pattern} across codebase ({count} instances)
- `{hash2}` — feat: add {prevention} to prevent {pattern}

## Convention Added
{The CLAUDE.md section or guide entry that was added, if applicable}
```

Update state:
```json
{
  "phase": "complete",
  "status": "completed",
  "completedAt": "2026-02-08T10:15:00Z"
}
```

---

## State File Reference

**Location:** `.learning/state.json`

```json
{
  "phase": "analyze|scan|fix|prevent|summary|complete",
  "status": "in_progress|completed|blocked",
  "startedAt": "2026-02-08T10:00:00Z",
  "completedAt": null,
  "branchName": "feature/example",
  "parameters": {
    "scope": "full",
    "autoCommit": true,
    "skipConfirm": false
  },
  "antiPattern": {
    "bugDescription": "...",
    "description": "...",
    "codeExample": "...",
    "searchPatterns": ["..."],
    "correctPattern": {
      "description": "...",
      "codeExample": "..."
    }
  },
  "scanResults": [
    {
      "file": "scrapers/dibbs.py",
      "line": 45,
      "matchedCode": "...",
      "context": "...",
      "confidence": "high",
      "suggestedFix": "...",
      "scanner": "scrapers|services|interfaces"
    }
  ],
  "approvedScope": "high|high+medium|all|none",
  "fixedFiles": ["scrapers/dibbs.py", "scrapers/wbparts.py"],
  "preventionStrategy": "A|B|C|D|E",
  "preventionDetails": {
    "strategy": "A",
    "filesCreated": [],
    "filesModified": [],
    "description": "..."
  },
  "commits": ["abc1234", "def5678"]
}
```

---

## Execution Instructions

When this skill is invoked:

### 1. Parse Parameters
```
/learning                           # defaults: scope=full, auto-commit=true, skip-confirm=false
/learning scope=scan-only           # only analyze + scan, don't fix or prevent
/learning scope=prevent-only        # skip scan/fix, just create prevention for known pattern
/learning auto-commit=false         # don't auto-commit
/learning skip-confirm=true         # skip user checkpoints
```

### 2. Initialize
- Create `.learning/` directory if needed
- Initialize or load `state.json`
- Check if resuming a previous run

### 3. Run Phases
```
Phase 1: Analyze conversation + git diff → extract anti-pattern
Phase 2: Spawn 3 scanners IN PARALLEL → find all instances
  └── USER CHECKPOINT: confirm scope
Phase 3: Spawn fix agent → apply correct pattern
  └── Commit fixes
Phase 4: Choose prevention strategy → implement
  └── USER CHECKPOINT: confirm strategy
  └── Commit prevention
Phase 5: Present summary report
```

### 4. Scope Shortcuts

| Scope | Phases Run |
|-------|-----------|
| `full` | 1 → 2 → 3 → 4 → 5 |
| `scan-only` | 1 → 2 (stops after presenting results) |
| `prevent-only` | 1 → 4 → 5 (user describes pattern, skip scan/fix) |

---

## Error Handling

### Scanner Agent Failure
- Log the failure
- Continue with results from other scanners
- Note in summary which scope was not scanned

### Fix Agent Failure
- Save fix prompt to `.learning/failed-fix-prompt.md`
- Ask user if they want to retry or fix manually
- Do NOT commit partial fixes

### Test Failure After Fixes
- Do NOT commit
- Spawn debug sub-agent to analyze failure
- If fixable, apply fix and retry tests
- After 2 consecutive failures, present the issue to the user

### No Instances Found
- Normal outcome — the anti-pattern was isolated to the original fix
- Skip Phase 3, proceed to Phase 4 (prevention still valuable)
- Note in summary that no other instances exist

### Prevention Already Exists
- If the utility/convention already exists (e.g., the original fix created it)
- Skip to Phase 5
- Note in summary that prevention was already in place

---

## Tips

1. **Run immediately after a bug fix** — The conversation context has the full story
2. **Start with defaults** — `scope=full` catches everything
3. **Review scan results carefully** — Low confidence matches may be false positives
4. **Prefer Strategy A** — Code-level prevention (utilities, decorators, context managers) is more durable than documentation
5. **Check the state file** — `.learning/state.json` tracks progress if interrupted
6. **Python-specific prevention patterns**: decorators for cross-cutting concerns, context managers for resource cleanup, Pydantic validators for data validation
