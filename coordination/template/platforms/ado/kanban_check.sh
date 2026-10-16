#!/usr/bin/env bash
#
# kanban_check.sh — deterministic board-orientation report for Azure DevOps Server.
#
# Emits the STEP0/SYNC/GATES/QUEUE/CANDIDATES report that `process/kanban-check.md`
# specifies, computed from the ADO REST API rather than inferred.  Everything here is
# a predicate over work-item/PR JSON; nothing here classifies a human's intent.
# Classification (decision vs change request vs question vs ambiguous), the HRQ
# consolidation category match, and every mutation stay with the orchestrating session.
#
# SCOPE IS ONE EPIC (or Feature).  Data Science holds ~22.8k work items, so a
# whole-project read is impossible; the board is a scope's Hierarchy-Forward subtree.
#
# READ-ONLY.  The transport is pinned read-only (ADO_READONLY=1), so every mutation
# helper refuses before it builds a request.  The only git commands run are read verbs
# (fetch, status, worktree list, branch, ls-remote); the script also runs text tools
# (jq, awk, sed, wc) that touch nothing but their own stdin.  Nothing here changes a
# tracked file, a branch, a work item, or a PR.
#
# Usage: process/kanban_check.sh --scope <Epic|Feature id> [--operator NAME] [--no-fetch] [--comments full|brief]
#
# The status machine (see docs/coordination-ado/PLAN.md) is read from System.State plus
# the `human-review` tag, because two board columns map to one state:
#   New            + agent-work   -> Todo
#   Active                      -> Agent working
#   Resolved, no tag            -> Awaiting code review
#   Resolved + human-review     -> Awaiting human action
#   Closed                      -> Done
# `agent-work` is also the "Responsible = AI agent" carrier; a custom Responsible
# field would need process customization (admin) and is not assumed here.
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=ado_api.sh
. "$DIR/ado_api.sh"

export ADO_READONLY=1

REPO_ID="${REPO_ID:-b65b2ef6-085b-4e36-af32-ea4046a7639e}"   # WaveformExtractionGUI
TAG_AGENT="agent-work"
TAG_HUMAN="human-review"
STALE_HOURS=24
IDLE_DAYS=7
MARKER='^(Processed|Claiming|Claim|Agent):'

SCOPE=""
OPERATOR=""
DO_FETCH=1
COMMENT_MODE="brief"
while [ $# -gt 0 ]; do
  case "$1" in
    --scope)    SCOPE="${2:-}"; shift 2 ;;
    --operator) OPERATOR="${2:-}"; shift 2 ;;
    --no-fetch) DO_FETCH=0; shift ;;
    --comments)
      case "${2:-}" in
        brief|full) COMMENT_MODE="$2" ;;
        *) echo "--comments takes 'brief' or 'full', got: ${2:-<missing>}" >&2; exit 2 ;;
      esac
      shift 2 ;;
    -h|--help) sed -n '2,35p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$SCOPE" ] || { echo "kanban_check.sh: --scope <Epic|Feature id> is required (the board is a subtree)" >&2; exit 2; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

[ -n "$OPERATOR" ] || OPERATOR="$(ado_get "_apis/connectionData" "1.0" | jq -r '.authenticatedUser.providerDisplayName')"

# ---------------------------------------------------------------- fetch state
if [ "$DO_FETCH" -eq 1 ]; then git fetch origin main -q || true; fi

# No `| head -1`: under `set -euo pipefail`, head closing the pipe early sends
# SIGPIPE to git and pipefail propagates 141 -- and it fires exactly on a dirty tree,
# when orientation matters most.  Parameter expansion touches no pipe.
BRANCH_STATUS="$(git status --short --branch)"
BRANCH_LINE="${BRANCH_STATUS%%$'\n'*}"
DIRTY="$(printf '%s\n' "$BRANCH_STATUS" | tail -n +2 | grep -c . || true)"
WORKTREES="$(git worktree list | wc -l | tr -d ' ')"
EXTRA_BRANCHES="$(git branch --format='%(refname:short)' | grep -vx 'main' || true)"

# The scope's subtree is the board.
SUBTREE_IDS="$(ado_subtree "$SCOPE" | tr '\n' ' ')"
[ -n "$SUBTREE_IDS" ] || { echo "kanban_check.sh: scope $SCOPE has no readable subtree" >&2; exit 2; }
ado_workitems $SUBTREE_IDS > "$TMP/items.json"
ado_prs "$REPO_ID" > "$TMP/prs.json"

# The PR list is the only unbounded fetch ($top=1000 in ado_api.sh); a full page is
# ambiguous ("exactly 1000" vs "at least 1000"), so warn rather than abort.
PR_COUNT="$(jq '.value | length' "$TMP/prs.json" 2>/dev/null || echo 0)"
LIMITS=""
[ "$PR_COUNT" -lt 1000 ] || LIMITS="PR list may be short — $PR_COUNT returned at the \$top=1000 cap; raise it in process/ado_api.sh"

# PR -> linked work-item ids (the ADO analogue of closingIssuesReferences).
{
  while read -r pr; do
    wi="$(ado_pr_workitems "$REPO_ID" "$pr" | jq -c '[.value[].id]')"
    jq -cn --argjson pr "$pr" --argjson wi "$wi" '{pr:$pr, wi:$wi}'
  done < <(jq -r '.value[].pullRequestId' "$TMP/prs.json")
} | jq -s '.' > "$TMP/pr_links.json" || echo '[]' > "$TMP/pr_links.json"

# Comments for every card, keyed by id.  N calls, but the subtree is tens of items.
{
  while read -r id; do
    ado_comments "$id" | jq -c --argjson id "$id" '{id:$id, comments:(.comments//[])}'
  done < <(jq -r '.value[].id' "$TMP/items.json")
} | jq -s 'map({key:(.id|tostring), value:.comments}) | from_entries' > "$TMP/comments.json" || echo '{}' > "$TMP/comments.json"

git ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##' > "$TMP/remote_branches.txt"

git show origin/main:HUMAN-REVIEW-QUEUE.md > "$TMP/hrq.md" 2>/dev/null || : > "$TMP/hrq.md"

# ------------------------------------------------------------------- HRQ parse
awk '
  /^## / {
    if (num != "") print_item()
    line = $0; sub(/^## /, "", line)
    num = line; sub(/\..*/, "", num)
    title = line; sub(/^[0-9]+\.[[:space:]]*/, "", title)
    open = 0; refs = ""; next
  }
  /^- \[ \]/ { open = 1 }
  { while (match($0, /#[0-9]+/)) {
      r = substr($0, RSTART, RLENGTH)
      if (index(refs, r " ") == 0) refs = refs r " "
      $0 = substr($0, RSTART + RLENGTH)
    } }
  END { if (num != "") print_item() }
  function print_item() {
    if (num ~ /^[0-9]+$/) printf "%s\t%d\t%s\t%s\n", num, open, (refs == "" ? "-" : refs), title
  }
' "$TMP/hrq.md" > "$TMP/hrq_items.tsv"

# ------------------------------------------------------------------- report
echo "=== KANBAN-CHECK REPORT ==="

printf 'STEP0: %s | dirty=%s | worktrees=%s | operator=%s | scope=%s\n' \
  "$BRANCH_LINE" "$DIRTY" "$WORKTREES" "$OPERATOR" "$SCOPE"
if [ -n "$EXTRA_BRANCHES" ]; then
  printf '  local branches beyond main: %s\n' "$(echo "$EXTRA_BRANCHES" | tr '\n' ' ')"
fi
if [ "$WORKTREES" -gt 1 ]; then
  git worktree list | tail -n +2 | sed 's/^/  extra worktree: /'
fi

# SYNC ------------------------------------------------------------------------
echo "SYNC:"
jq -r --slurpfile comments "$TMP/comments.json" --slurpfile links "$TMP/pr_links.json" \
      --arg agent "$TAG_AGENT" --arg human "$TAG_HUMAN" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def cardstatus($f):
    (tags($f)) as $t | ($f["System.State"] // "") as $s
    | if ($t | test($human)) then "Awaiting human action"
      elif $s == "Closed" then "Done"
      elif $s == "Resolved" then "Awaiting code review"
      elif $s == "Active" then "Agent working"
      elif $s == "New" then "Todo" else $s end;
  def assignee($f):
    ($f["System.AssignedTo"] // "") | if type == "object" then (.displayName // "") else . end;
  ($links[0] // []) as $L
  | [ .value[] | select(.fields["System.WorkItemType"] == "User Story")
      | . as $w | .fields as $f
      | ($f["System.Id"]) as $id
      | ($L[] | select(.wi | index($id)) | .pr) as $pr
      | ($pr // null) as $prid
      | if ($prid == null) then empty
        else "  #\($id) linked PR \($prid) — card status: \(cardstatus($f))" end ]
  | if length == 0 then "  cards and PRs: no cross-links found in this subtree" else .[] end
' "$TMP/items.json"

# Stale claims: Agent working, newest agent marker older than STALE_HOURS, no active
# PR referencing the card, no remote branch `issue-<id>`.
jq -r --slurpfile comments "$TMP/comments.json" --slurpfile prs "$TMP/prs.json" \
      --rawfile branches "$TMP/remote_branches.txt" --arg marker "$MARKER" --argjson stale "$STALE_HOURS" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def cardstatus($f):
    (tags($f)) as $t | ($f["System.State"] // "") as $s
    | if ($t | test("human-review")) then "Awaiting human action"
      elif $s == "Closed" then "Done" elif $s == "Resolved" then "Awaiting code review"
      elif $s == "Active" then "Agent working" elif $s == "New" then "Todo" else $s end;
  [ .value[] | .fields as $f | select(cardstatus($f) == "Agent working")
      | ($f["System.Id"]) as $id
      | (($comments[0][$id|tostring] // []) | map(select(.text | test($marker))) | last) as $lastmark
      | (if $lastmark == null then 1e9
         else ((now - ($lastmark.createdDate | fromdateiso8601)) / 3600) end) as $age
      | ([$prs[0].value[] | select(.status == "active")
          | select(((.sourceRefName // "") | test("issue-\($id)($|[^0-9])")))] | length) as $openprs
      | (($branches | split("\n") | map(select(test("^issue-\($id)($|[^0-9])")))) | length) as $rbr
      | (($age|floor)|tostring) as $ageh
      | if ($age > $stale and $openprs == 0 and $rbr == 0)
        then "  STALE CLAIM #\($id) — newest marker \(if $lastmark == null then "none" else $ageh + "h old" end), no active PR, no issue-\($id) branch → verify nothing landed, then re-queue to Todo"
        elif ($openprs > 0) then "  #\($id) Agent working, \($openprs) active PR(s) — not stale"
        elif ($rbr > 0) then "  #\($id) Agent working, marker \($ageh)h old, issue-\($id) branch on remote — not stale"
        elif ($age <= $stale) then "  #\($id) Agent working, marker \($ageh)h old (under the \($stale)h threshold) — not stale"
        else "  #\($id) Agent working — not stale" end ]
  | if length == 0 then "  no Agent-working cards" else .[] end
' "$TMP/items.json"

echo "  HRQ open items (card-category consolidation is the orchestrator call):"
while IFS=$'\t' read -r num open refs title; do
  [ "$open" = "1" ] || continue
  if [ -z "$refs" ] || [ "$refs" = "-" ]; then
    printf '    item %s — NO CARD REF — %s\n' "$num" "$title"
  else
    printf '    item %s — refs %s— %s\n' "$num" "$refs" "$title"
  fi
done < "$TMP/hrq_items.tsv"

# GATES -----------------------------------------------------------------------
echo "GATES:"
jq -r --slurpfile comments "$TMP/comments.json" --arg human "$TAG_HUMAN" --argjson stale "$STALE_HOURS" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def inprog: test("^Processed:\\s*\\(in progress");
  def superseded: test("\\(superseded");
  [ .value[] | .fields as $f
      | select(($f["System.State"] // "") == "Closed")
      | select((tags($f)) | test($human))
      | .id as $id
      | ($comments[0][$id|tostring] // []) as $c
      | [$c[] | select((.text // "") | test("^Processed:"))] as $pc
      | select([ $pc[] | select(((.text | inprog) | not) and ((.text | superseded) | not)) ] | length == 0)
      | ([ $pc[] | select((.text | inprog) and ((.text | superseded) | not)) ] | last) as $claim
      | if $claim == null then "  UNPROCESSED closed gate #\($id) — \($f["System.Title"])"
        else ((now - ($claim.createdDate | fromdateiso8601)) / 3600 | floor) as $h
          | if $h > $stale
            then "  ABANDONED claim on closed gate #\($id) — in-progress marker \($h)h old, never finalized → supersede and process"
            else "  closed gate #\($id) claimed \($h)h ago, in progress — skip" end
        end ]
  | if length == 0 then "  closed human-review gates without a finalized Processed:: none" else .[] end
' "$TMP/items.json"

# Open Awaiting-human-action cards: anything after the last agent marker, verbatim.
jq -r --slurpfile comments "$TMP/comments.json" --arg marker "$MARKER" --arg human "$TAG_HUMAN" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def cardstatus($f):
    (tags($f)) as $t | ($f["System.State"] // "") as $s
    | if ($t | test($human)) then "Awaiting human action"
      elif $s == "Closed" then "Done" elif $s == "Resolved" then "Awaiting code review"
      elif $s == "Active" then "Agent working" elif $s == "New" then "Todo" else $s end;
  [ .value[] | .fields as $f | select(cardstatus($f) == "Awaiting human action") | .id as $id
      | ($comments[0][$id|tostring] // []) as $c
      | ([$c[] | .text | test($marker)] | to_entries | map(select(.value)) | last | .key // -1) as $h
      | if ($c | length) == 0 then "  #\($id) NO COMMENTS — card carries no ask yet"
        elif (($c | length) > ($h + 1))
        then "  #\($id) POST-HORIZON comment(s) — orchestrator must classify:\n"
             + ([$c[($h+1):][] | "    ┌ \(.createdDate)\n" + ((.text // "") | split("\n") | map("    │ " + .) | join("\n"))] | join("\n"))
        else "  #\($id) clean — last comment carries an agent marker" end ]
  | if length == 0 then "  no Awaiting-human-action cards" else .[] end
' "$TMP/items.json"

# QUEUE -----------------------------------------------------------------------
echo "QUEUE:"
jq -r --arg op "$OPERATOR" --slurpfile comments "$TMP/comments.json" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def assignee($f):
    ($f["System.AssignedTo"] // "") | if type == "object" then (.displayName // "") else . end;
  def ask($c): ($c // []) | (.[0].text // "") | split("\n") | map(select(test("\\S"))) | (.[0] // "")
    | gsub("\\*\\*"; "") | gsub("^#+ +"; "") | gsub("\\s+"; " ")
    | if length > 160 then (.[0:159] + "…") else . end;
  [ .value[] | .fields as $f
      | select((tags($f)) | test("human-review"))
      | select(assignee($f) == $op)
      | .id as $id
      | "  #\($id) — \($f["System.Title"])" + (ask($comments[0][$id|tostring]) as $a | if $a == "" then "" else "\n        ask: \($a)" end) ]
  | if length == 0 then "  none in \($op)'"'"'s lane" else .[] end
' "$TMP/items.json"

# CANDIDATES ------------------------------------------------------------------
echo "CANDIDATES:"
jq -r --arg op "$OPERATOR" --arg agent "$TAG_AGENT" --arg human "$TAG_HUMAN" --arg mode "$COMMENT_MODE" --slurpfile comments "$TMP/comments.json" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def assignee($f):
    ($f["System.AssignedTo"] // "") | if type == "object" then (.displayName // "") else . end;
  def cardstatus($f):
    (tags($f)) as $t | ($f["System.State"] // "") as $s
    | if ($t | test($human)) then "Awaiting human action"
      elif $s == "Closed" then "Done" elif $s == "Resolved" then "Awaiting code review"
      elif $s == "Active" then "Agent working" elif $s == "New" then "Todo" else $s end;
  [ .value[] | .fields as $f
      | select(cardstatus($f) == "Todo")
      | select((tags($f)) | test($agent))
      | select(assignee($f) == $op)
      | {n: $f["System.Id"], t: $f["System.Title"]} ]
  | sort_by(.n)
  | if length == 0 then ["  none in \($op)'"'"'s lane — poach check required"] else
      [ .[] | . as $c | ($comments[0][$c.n|tostring] // []) as $cm
        | "  #\($c.n) — \($c.t)"
          + (if ($cm | length) == 0 then ""
             elif $mode == "brief" then
               "\n" + ([$cm[] | "      · " + ((.text | split("\n") | map(select(length>0)) | first // "") | .[0:150])] | join("\n"))
             else
               "\n" + ([$cm[] | "      ┌ \(.createdDate)\n" + ((.text // "") | split("\n") | map("      │ " + .) | join("\n"))] | join("\n"))
             end) ]
    end | .[]
' "$TMP/items.json"

jq -r --arg op "$OPERATOR" --arg agent "$TAG_AGENT" --arg human "$TAG_HUMAN" '
  def tags($f): ($f["System.Tags"] // "") | ascii_downcase;
  def assignee($f):
    ($f["System.AssignedTo"] // "") | if type == "object" then (.displayName // "") else . end;
  def cardstatus($f):
    (tags($f)) as $t | ($f["System.State"] // "") as $s
    | if ($t | test($human)) then "Awaiting human action"
      elif $s == "Closed" then "Done" elif $s == "Resolved" then "Awaiting code review"
      elif $s == "Active" then "Agent working" elif $s == "New" then "Todo" else $s end;
  ([.value[] | .fields as $f | select(cardstatus($f) == "Todo") | select((tags($f)) | test($agent)) | select(assignee($f) == $op)] | length) as $mine
  | if $mine > 0 then empty else
      ([.value[] | .fields as $f | select(cardstatus($f) == "Todo") | select((tags($f)) | test($agent))
        | {n: $f["System.Id"], t: $f["System.Title"], a: assignee($f)}]
       | sort_by(.n)
       | map("  POACHABLE #\(.n) — \(.t) (assignee: \(.a))")
       | if length == 0 then ["  board drained — no agent-work Todo in this subtree"] else . end | .[])
    end
' "$TMP/items.json"

[ -z "$LIMITS" ] || printf 'LIMITS: %s\n' "$LIMITS"
echo "=== END KANBAN-CHECK REPORT ==="
