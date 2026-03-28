# T-REX Session Coordination — Design Brief

## Problem

Multiple Claude Code sessions can operate on the same repo simultaneously with zero awareness of each other. This leads to:
- Branch conflicts (two sessions create branches from different bases)
- File conflicts (two sessions edit the same file concurrently)
- Logical conflicts (two sessions change the same function's behavior on different branches)
- Accidental cross-contamination (session commits to wrong branch because another session switched it)

This is a fundamental limitation of the Claude API — sessions are stateless and isolated. Anthropic has no shared state bus between active sessions.

## Current State

T-REX already provides:
- `rex_register_session(agent_id, repo, branch)` — announces a session exists
- `rex_validate_branch(repo, session_id)` — checks if branch is protected
- `rex_claim_task(session_id, task_id, description)` — claims a task
- `rex_handoff(session_id, work_done, pending_tasks)` — session end summary
- `rex_status` — view active sessions

**Gap:** No file-level coordination. Sessions don't declare what they're touching, and nothing prevents overlap.

## Proposed Extension

### New MCP Tools

#### `rex_claim_files(session_id, file_paths, branch)`
Declares intent to modify specific files on a specific branch. Stores in the session registry.

```json
{
  "session_id": "abc123",
  "branch": "fix/routing-cost",
  "files": [
    "backend/app/models/manufacturing.py",
    "backend/app/services/item_service.py"
  ],
  "claimed_at": "2026-03-22T10:00:00Z"
}
```

Returns: `{ "status": "ok" }` or `{ "status": "conflict", "conflicts": [...] }` if another active session has claimed overlapping files.

#### `rex_check_conflicts(file_path)`
Quick check before editing a file. Returns any active sessions that have claimed it.

```json
{
  "file": "backend/app/models/manufacturing.py",
  "claimed_by": [
    {
      "session_id": "xyz789",
      "branch": "feat/variant-matrix",
      "claimed_at": "2026-03-22T09:45:00Z",
      "task": "Adding is_variable column to RoutingOperationMaterial"
    }
  ]
}
```

#### `rex_release_files(session_id)`
Called at session end (or via `rex_handoff`). Releases all file claims for the session.

### Enforcement via Hooks

#### PreToolUse hook (Edit/Write)
Before any file edit, call `rex_check_conflicts(file_path)`. If conflict detected:
- **Warn** (soft gate): Print warning, let the session decide
- **Block** (hard gate): Exit 1, prevent the edit

```bash
# ~/.claude/hooks/trex-file-guard.sh
FILE_PATH="$1"
RESULT=$(curl -s "http://192.168.56.101:3000/check-conflicts?file=$FILE_PATH&session=$SESSION_ID")
if echo "$RESULT" | jq -e '.claimed_by | length > 0' > /dev/null; then
    echo "⚠️ T-REX: File $FILE_PATH is claimed by another session"
    echo "$RESULT" | jq -r '.claimed_by[] | "  Session: \(.session_id) on \(.branch) — \(.task)"'
    exit 1  # Block edit
fi
```

#### SessionStart hook
Auto-register session and check if the current branch has active sessions:

```bash
# If another session is active on this branch, warn
ACTIVE=$(curl -s "http://192.168.56.101:3000/active-sessions?branch=$BRANCH")
if [ $(echo "$ACTIVE" | jq '.sessions | length') -gt 0 ]; then
    echo "⚠️ T-REX: Another session is active on branch '$BRANCH'"
fi
```

### Session Lifecycle

```
Session starts
  → rex_register_session (existing)
  → rex_validate_branch (existing)
  → rex_claim_task (existing)

Session reads/plans
  → No file claims needed yet

Session starts editing
  → rex_claim_files(session_id, [files], branch)
  → PreToolUse hook checks conflicts on each edit

Session ends
  → rex_handoff (existing) — auto-releases file claims
  → Or explicit rex_release_files(session_id)

Session crashes/times out
  → Claims expire after configurable TTL (e.g., 2 hours)
  → Stale claims are cleaned up on next rex_status query
```

### Data Model (SQLite)

```sql
CREATE TABLE file_claims (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    branch TEXT NOT NULL,
    file_path TEXT NOT NULL,
    task_description TEXT,
    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- TTL-based expiry
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_file_claims_path ON file_claims(file_path);
CREATE INDEX idx_file_claims_session ON file_claims(session_id);
```

## What This Doesn't Solve

- **Logical conflicts** — two sessions can change different files that interact semantically. Only code review catches this.
- **Branch base drift** — session A merges to main, session B's branch is now behind. Git handles this at merge time.
- **Cross-repo coordination** — Core and ecosystem sessions can't conflict on the same files, but PRO could import a Core function that Core renames. Out of scope.

## Implementation Estimate

- T-REX MCP server: 3 new tools (~200 lines Python)
- SQLite schema: 1 new table
- Hook scripts: 2 new/modified (~50 lines bash)
- Testing: manual with 2 concurrent sessions

## Alternatives Considered

**Git worktrees per session** — isolates file system but doesn't prevent logical conflicts. Good complement, not a replacement.

**Lockfile in repo** — `.claude/active-sessions.json` checked into git. Race condition: two sessions read, both see clear, both write. Git merge conflict ensues. Fragile.

**Anthropic API change** — shared session state would be the real fix. Not something we can control. This design works around it.
