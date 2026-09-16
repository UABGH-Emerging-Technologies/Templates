#!/usr/bin/env bash
#
# kanban_check.sh — deterministic board-orientation report.
#
# Emits the STEP0/SYNC/GATES/QUEUE/CANDIDATES report that `process/kanban-check.md`
# specifies, computed rather than inferred. Everything in here is a predicate over
# board/issue/PR JSON; nothing in here classifies a human's intent. Classification
# (decision vs change request vs question vs ambiguous), the HRQ consolidation
# category match, and every mutation stay with the orchestrating session.
#
# READ-ONLY. The only git and gh commands run are read verbs (the script also runs
# ordinary text tools — jq, awk, sed, wc — which touch nothing but their own stdin):
#   gh api user | gh project item-list | gh project view | gh project field-list
#   gh issue list | gh pr list
#   git fetch origin main -q | git status | git worktree list | git branch | git ls-remote
# No `gh project item-edit/item-add/item-create`, no `gh issue|pr` mutation, no
# `gh api -X POST|PATCH|PUT|DELETE`, no `git fetch --prune` (pruning rewrites the local
# ref store and changes what the caller's own hygiene check sees afterwards — 2026-08-24).
#
# The precise invariant is NO WORKING-TREE WRITES AND NO REMOTE MUTATIONS -- not "no
# writes at all". `git fetch` updates .git/FETCH_HEAD and may add objects, and `gh`
# maintains its own caches; both are local bookkeeping this script cannot avoid while
# still reporting fresh state. Nothing it does changes a tracked file, a branch, an
# issue, a PR, or the board.
#
# Usage: process/kanban_check.sh [--operator LOGIN] [--no-fetch] [--comments full|brief]
#
# TEMPLATE COPY: the three constants below carry <TOKEN> placeholders that
# `process/board-setup.md` step 5 fills in. The guard beneath them refuses to run
# while any remain, because a half-substituted script is the one failure mode that
# cannot be seen in its output -- it would report some other project's board in
# this project's orientation, and a wrong-data run looks exactly like a good one.
#
set -euo pipefail

REPO="<REPO_SLUG>"          # owner/repo, e.g. acme/widget
OWNER="<BOARD_OWNER>"       # org or user that owns the project board
PROJECT="<BOARD_NUMBER>"    # the project board number
ISSUE_LIMIT=300
PR_LIMIT=300
BOARD_LIMIT=200
STALE_HOURS=24
IDLE_DAYS=7
# Documented agent markers are Processed:/Claiming:/Agent:. `Claim:` is tolerated
# because near-miss spellings do occur in a real record, and rejecting one would
# manufacture a false "unacknowledged human input" finding. Widen this pattern
# rather than hand-editing history if your project grows another variant.
MARKER='^(Processed|Claiming|Claim|Agent):'

case "$REPO$OWNER$PROJECT" in
  *'<'*|*'>'*)
    echo "kanban_check.sh still carries template placeholders (REPO/OWNER/PROJECT)." >&2
    echo "Fill them with this project's repo slug, board owner and board number" >&2
    echo "-- see process/board-setup.md step 5 -- before running orientation." >&2
    exit 2 ;;
esac

OPERATOR=""
DO_FETCH=1
COMMENT_MODE="brief"

while [ $# -gt 0 ]; do
  case "$1" in
    --operator) OPERATOR="$2"; shift 2 ;;
    --no-fetch) DO_FETCH=0; shift ;;
    --comments)
      case "${2:-}" in
        brief|full) COMMENT_MODE="$2" ;;
        *) echo "--comments takes 'brief' or 'full', got: ${2:-<missing>}" >&2; exit 2 ;;
      esac
      shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -n "$OPERATOR" ] || OPERATOR="$(gh api user --jq .login)"

# ---------------------------------------------------------------- fetch state
if [ "$DO_FETCH" -eq 1 ]; then git fetch origin main -q; fi

# No `| head -1` here: under `set -euo pipefail`, head closing the pipe early
# sends SIGPIPE to git, pipefail propagates 141, and the script dies before it
# reports anything.  It only fires when git is still writing when head exits --
# i.e. on a dirty tree, which is precisely when orientation matters.  Taking the
# first line by parameter expansion touches no pipe at all.
BRANCH_STATUS="$(git status --short --branch)"
BRANCH_LINE="${BRANCH_STATUS%%$'\n'*}"
DIRTY="$(git status --porcelain | wc -l | tr -d ' ')"
WORKTREES="$(git worktree list | wc -l | tr -d ' ')"
EXTRA_BRANCHES="$(git branch --format='%(refname:short)' | grep -vx 'main' || true)"

# --query filters server-side, so it shrinks what --limit must cover (a jq filter cannot:
# --limit truncates at fetch). Every pass below reads only non-Done cards, and closed gates
# deliberately come from the issue API instead, so nothing needs the Done rows.
gh project item-list "$PROJECT" --owner "$OWNER" --query "-status:Done" --limit "$BOARD_LIMIT" --format json \
  | jq -e '.totalCount as $t | (.items|length) as $n
      | if $t == $n then . else error("BOARD TRUNCATED: \($n) of \($t) — raise BOARD_LIMIT") end' \
  > "$TMP/board.json"

# gh issue list / pr list have no totalCount (asking for it errors), so the guard is
# returned-vs-limit: equality is indistinguishable from "at least limit", so treat it
# as truncation and fail toward suspicion.
gh issue list -R "$REPO" --state all --limit "$ISSUE_LIMIT" \
  --json number,title,state,labels,comments,updatedAt,body > "$TMP/issues.json"
n=$(jq 'length' "$TMP/issues.json")
[ "$n" -lt "$ISSUE_LIMIT" ] || { echo "ISSUES TRUNCATED at $ISSUE_LIMIT — raise ISSUE_LIMIT" >&2; exit 1; }

# closingIssuesReferences IS the "linked development" section the spec names: it
# covers PRs linked through the sidebar as well as by closing keyword, so a PR
# linked only in the UI is no longer reported as an untracked orphan.
gh pr list -R "$REPO" --state all --limit "$PR_LIMIT" \
  --json number,title,state,isDraft,url,body,headRefName,mergedAt,closingIssuesReferences > "$TMP/prs.json"
n=$(jq 'length' "$TMP/prs.json")
[ "$n" -lt "$PR_LIMIT" ] || { echo "PRS TRUNCATED at $PR_LIMIT — raise PR_LIMIT" >&2; exit 1; }

git ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##' > "$TMP/remote_branches.txt"

# Status field + option ids, read live rather than hardcoded: the spec asks SYNC to
# carry the exact command, and regenerating option ids is a known hazard here
# (renaming a single-select option reissues every id).  Read verbs only.
# Every lookup below is best-effort and MUST NOT be able to end the run: the ids
# only decorate SYNC with a ready-to-paste command, while the report itself is the
# point.  Without `|| true` a token lacking `project` scope (or a restricted
# sandbox) makes `gh project view` fail, pipefail propagates, and `set -e` kills
# the whole orientation report over an optional convenience line.
PROJECT_ID="$(gh project view "$PROJECT" --owner "$OWNER" --format json 2>/dev/null | jq -r '.id // empty' || true)"
gh project field-list "$PROJECT" --owner "$OWNER" --format json 2>/dev/null \
  | jq -r '(.fields[] | select(.name == "Status")) // empty' > "$TMP/status_field.json" || true
STATUS_FIELD_ID="$(jq -r '.id // empty' "$TMP/status_field.json" 2>/dev/null)"
DONE_OPTION_ID="$(jq -r '(.options[]? | select(.name == "Done") | .id) // empty' "$TMP/status_field.json" 2>/dev/null)"
git show origin/main:HUMAN-REVIEW-QUEUE.md > "$TMP/hrq.md" 2>/dev/null || : > "$TMP/hrq.md"

# ------------------------------------------------------------------- HRQ parse
# An item is "## N. <title>"; it is open if it carries an unchecked "- [ ]" box.
# Card references are any #NNN appearing in the item body.
awk '
  /^## / {
    if (num != "") print_item()
    line = $0
    sub(/^## /, "", line)
    num = line; sub(/\..*/, "", num)
    title = line; sub(/^[0-9]+\.[[:space:]]*/, "", title)
    open = 0; refs = ""
    next
  }
  /^- \[ \]/ { open = 1 }
  { while (match($0, /#[0-9]+/)) {
      r = substr($0, RSTART, RLENGTH)
      if (index(refs, r " ") == 0) refs = refs r " "
      $0 = substr($0, RSTART + RLENGTH)
    } }
  END { if (num != "") print_item() }
  function print_item() {
    if (num ~ /^[0-9]+$/) {
      # "-" placeholder: tab is an IFS whitespace char, so consecutive tabs collapse
      # into one delimiter in `read` and every later field shifts left.
      printf "%s\t%d\t%s\t%s\n", num, open, (refs == "" ? "-" : refs), title
    }
  }
' "$TMP/hrq.md" > "$TMP/hrq_items.tsv"

# ------------------------------------------------------------------- report
echo "=== KANBAN-CHECK REPORT ==="

# STEP0 -----------------------------------------------------------------------
printf 'STEP0: %s | dirty=%s | worktrees=%s | operator=%s\n' \
  "$BRANCH_LINE" "$DIRTY" "$WORKTREES" "$OPERATOR"
if [ -n "$EXTRA_BRANCHES" ]; then
  printf '  local branches beyond main: %s\n' "$(echo "$EXTRA_BRANCHES" | tr '\n' ' ')"
fi
if [ "$WORKTREES" -gt 1 ]; then
  git worktree list | tail -n +2 | sed 's/^/  extra worktree: /'
fi

# SYNC ------------------------------------------------------------------------
echo "SYNC:"
jq -r --slurpfile issues "$TMP/issues.json" --slurpfile prs "$TMP/prs.json" \
      --arg pid "$PROJECT_ID" --arg fid "$STATUS_FIELD_ID" --arg done "$DONE_OPTION_ID" '
  # The exact command, not just the intent — but only where the action is
  # determinate.  "PR closed unmerged" needs a human to say what was meant, so it
  # stays intent-only rather than shipping a command that might be the wrong one.
  def setdone($item):
    if ($pid == "" or $fid == "" or $done == "") then ""
    else "\n        gh project item-edit --project-id \($pid) --id \($item) --field-id \($fid) --single-select-option-id \($done)"
    end;
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | ($prs[0]   | map({key:(.number|tostring), value:.}) | from_entries) as $P
  | [ .items[]
      | select(.status != "Done")
      | . as $it
      | .content.number as $n
      | select($n != null)
      | ($I[$n|tostring]) as $i | ($P[$n|tostring]) as $p
      | if   ($i != null and $i.state == "CLOSED") then "  #\($n) issue CLOSED but Status=\($it.status) → set Done" + setdone($it.id)
        elif ($p != null and $p.mergedAt != null)  then "  #\($n) PR MERGED but Status=\($it.status) → set Done" + setdone($it.id)
        elif ($p != null and $p.state == "CLOSED") then "  #\($n) PR CLOSED unmerged but Status=\($it.status) → confirm intent (no command: the right move depends on why it closed)"
        else empty end ]
  | if length == 0 then "  closed/merged vs Status: consistent" else .[] end
' "$TMP/board.json"

jq -r --slurpfile board "$TMP/board.json" '
  ([$board[0].items[] | select(.content.number != null) | .content.number]) as $carded
  | ([$board[0].items[] | select(.status == "Awaiting code review") | .content.number]) as $inreview
  | [ .[]
      | select(.state == "OPEN" and (.isDraft | not))
      | . as $pr
      | ((.body // "") | [scan("(?i)(?:closes|fixes|resolves)\\s+#([0-9]+)")] | flatten | map(tonumber)) as $closes
      | ((.headRefName // "") | [scan("issue-([0-9]+)")] | flatten | map(tonumber)) as $branchref
      | ([(.closingIssuesReferences // [])[] | .number]) as $devlinked
      | (($closes + $branchref + $devlinked) | unique) as $linked
      | select(($carded | index($pr.number)) == null)
      | select([ $linked[] | select(($inreview | index(.)) != null) ] | length == 0)
      | "  untracked open PR #\($pr.number) — \($pr.title) (links: \(if ($linked|length)==0 then "none found" else ($linked|tostring) end))" ]
  | if length == 0 then "  open non-draft PRs: all tracked" else .[] end
' "$TMP/prs.json"

# Stale work claims: Agent working, newest agent-marker older than STALE_HOURS,
# no open PR referencing it, no remote branch for it.
jq -r --slurpfile issues "$TMP/issues.json" --slurpfile prs "$TMP/prs.json" \
      --rawfile branches "$TMP/remote_branches.txt" \
      --arg marker "$MARKER" --argjson stale "$STALE_HOURS" '
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | [ .items[] | select(.status == "Agent working") | .content.number as $n | select($n != null)
      | ($I[$n|tostring]) as $i
      | (if $i == null then null else
          ([$i.comments[] | select(.body | test($marker))] | last) end) as $lastmark
      | (if $lastmark == null then 1e9
         else ((now - ($lastmark.createdAt | fromdateiso8601)) / 3600) end) as $age
      | ([$prs[0][] | select(.state == "OPEN") | select(((.body // "") + " " + (.headRefName // "")) | test("#\($n)\\b|issue-\($n)\\b"))] | length) as $openprs
      # Branch match follows the repo convention `issue-<n>[-slug]`. A bare substring
      # match (the number bounded by non-digits) also hits dates, ports and other
      # tracker ids, and it fails toward UNDER-reporting: a false hit suppresses a
      # genuine stale claim, which is the expensive direction.
      | (($branches | split("\n") | map(select(test("^issue-\($n)($|[^0-9])")))) | length) as $rbr
      | (($age|floor)|tostring) as $ageh
      # Each branch states only what it actually tested. The earlier version printed
      # "remote branch present" for every not-stale case that was not PR-caused,
      # including the common one (claim simply younger than the threshold) where no
      # branch had been checked at all — a fabricated justification.
      | if ($age > $stale and $openprs == 0 and $rbr == 0)
        then "  STALE CLAIM #\($n) — newest marker \(if $lastmark == null then "none" else $ageh + "h old" end), no open PR, no issue-\($n) branch → verify nothing landed, then re-queue to Todo"
        elif ($openprs > 0) then "  #\($n) Agent working, \($openprs) open PR(s) — not stale"
        elif ($rbr > 0) then "  #\($n) Agent working, marker \($ageh)h old, issue-\($n) branch on remote — not stale"
        elif ($age <= $stale) then "  #\($n) Agent working, marker \($ageh)h old (under the \($stale)h threshold) — not stale"
        else "  #\($n) Agent working — not stale" end ]
  | if length == 0 then "  no Agent-working cards" else .[] end
' "$TMP/board.json"

# HRQ: open items and their card references. Category consolidation is NOT decided here.
echo "  HRQ open items (card-category consolidation is the orchestrator call):"
while IFS=$'\t' read -r num open refs title; do
  [ "$open" = "1" ] || continue
  # Linkage runs both ways: the HRQ item may name a card, or a card's title/body may
  # name the item ("HRQ #5", "HRQ item 5", "HRQ 5"). Check both before calling it an orphan.
  back=$(jq -r --arg n "$num" '[.[]|select(.state=="OPEN")
      |select(((.title // "") + " " + (.body // "")) | test("HRQ\\s*(item\\s*)?#?" + $n + "\\b"))
      |"#\(.number)"]|join(" ")' "$TMP/issues.json")
  [ "$refs" = "-" ] && refs=""
  all_refs=$(printf '%s %s' "$refs" "$back" | tr ' ' '\n' | grep -v '^$' | awk '!seen[$0]++' | tr '\n' ' ')
  if [ -z "$all_refs" ]; then
    printf '    item %s — NO CARD REF (either direction) — %s\n' "$num" "$title"
  else
    printf '    item %s — refs %s— %s\n' "$num" "$all_refs" "$title"
  fi
done < "$TMP/hrq_items.tsv"

# Checked-off HRQ items that still reference an OPEN human-review card. Refs include
# incidental mentions, so this is narrowed to open cards carrying the human-review
# label — still advisory, not a verdict.
echo "  HRQ checked-off items still pointing at an open human-review card:"
hrq_found=0
while IFS=$'\t' read -r num open refs title; do
  [ "$open" = "0" ] || continue
  [ "$refs" != "-" ] || continue
  for r in $refs; do
    rn="${r#\#}"
    st=$(jq -r --argjson n "$rn" '[.[]|select(.number==$n)|select(.state=="OPEN")|select([.labels[].name]|index("human-review"))|.title]|first // empty' "$TMP/issues.json")
    if [ -n "$st" ]; then
      printf '    item %s (checked off) -> #%s still OPEN: %s\n' "$num" "$rn" "$st"
      hrq_found=1
    fi
  done
done < "$TMP/hrq_items.tsv"
[ "$hrq_found" = "1" ] || echo "    none"

# GATES -----------------------------------------------------------------------
echo "GATES:"
jq -r --arg marker "$MARKER" '
  [ .[] | select(.state == "CLOSED")
        | select([.labels[].name] | index("human-review"))
        | select([.comments[].body | test("^Processed:")] | any | not)
        | "  UNPROCESSED closed gate #\(.number) — \(.title)" ]
  | if length == 0 then "  closed human-review gates missing Processed:: none" else .[] end
' "$TMP/issues.json"

# Open Awaiting-human-action cards: anything after the last agent marker, verbatim.
jq -r --slurpfile issues "$TMP/issues.json" --arg marker "$MARKER" '
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | [ .items[] | select(.status == "Awaiting human action") | .content.number as $n | select($n != null)
      | ($I[$n|tostring]) as $i
      | if $i == null then "  #\($n) NOT CHECKABLE — no issue record fetched (PR-typed card, or outside the issue fetch window); read this card by hand" else
        ([$i.comments[] | .body | test($marker)] | to_entries | map(select(.value)) | last | .key // -1) as $h
      | if (($i.comments | length) > ($h + 1))
        then "  #\($n) POST-HORIZON comment(s) — unmarked, orchestrator must classify (decision / change request / question / ambiguous):\n"
             + ([$i.comments[($h+1):][] | "    ┌ \(.createdAt)\n" + (.body | split("\n") | map("    │ " + .) | join("\n"))] | join("\n"))
        else "  #\($n) clean — last comment carries an agent marker" end end ]
  | if length == 0 then "  no Awaiting-human-action cards" else .[] end
' "$TMP/board.json"

# QUEUE -----------------------------------------------------------------------
echo "QUEUE:"
# The ask, not just the title: kanban-check.md specifies "#number — one-line
# ask" and next.md step 3 wants title + ask, because a queue is drained by
# knowing what is being ASKED, which a title routinely does not say.  The repo
# rule "the first line of a card body is the ask" is what makes this mechanical;
# a card that breaks the rule degrades to its title rather than misreporting.
jq -r --arg op "$OPERATOR" --slurpfile issues "$TMP/issues.json" '
  def ask($b):
    ($b // "") | split("\n") | map(select(test("\\S")))
    | (.[0] // "")
    | gsub("\\*\\*"; "") | gsub("^#+ +"; "") | gsub("\\s+"; " ")
    | if (length > 160) then (.[0:159] + "…") else . end;
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | [ .items[] | select(.status == "Awaiting human action") | select(((.assignees // []) | index($op)) != null)
      | select(.content.number != null)
      | .content.number as $n
      | ask($I[$n|tostring].body) as $a
      | (($I[$n|tostring].title) // .title) as $t
      | "  #\($n) — \($t)" + (if $a == "" then "" else "\n        ask: \($a)" end) ]
  | if length == 0 then "  none in \($op)'"'"'s lane" else .[] end
' "$TMP/board.json"
jq -r --arg op "$OPERATOR" --argjson idle "$IDLE_DAYS" --slurpfile issues "$TMP/issues.json" '
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | [ .items[] | select(.status == "Awaiting human action") | select(((.assignees // []) | index($op)) == null)
      | .content.number as $n | ($I[$n|tostring]) as $i
      | if $i == null then "  #\($n) NOT CHECKABLE for idle age — no issue record fetched" else
        ((now - ($i.updatedAt | fromdateiso8601)) / 86400) as $days
      | if $days >= $idle then "  stale in another lane (\($days|floor)d): #\($n) — \(($i.title) // .title)" else empty end end ]
  | if length == 0 then "  other lanes: none idle >= \($idle)d" else .[] end
' "$TMP/board.json"

# CANDIDATES ------------------------------------------------------------------
echo "CANDIDATES:"
jq -r --arg op "$OPERATOR" --arg mode "$COMMENT_MODE" --slurpfile issues "$TMP/issues.json" '
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | [ .items[] | select(.status == "Todo" and .responsible == "AI agent")
      | select(((.assignees // []) | index($op)) != null)
      | select(.content.number != null)
      | {n: .content.number, t: .title} ]
  | sort_by(.n)
  | if length == 0 then ["  none in \($op)'"'"'s lane — poach check required"] else
      [ .[] | . as $c | ($I[$c.n|tostring]) as $i
        | "  #\($c.n) — \(($i.title) // $c.t)"
          + (if ($i == null or ($i.comments | length) == 0) then ""
             elif $mode == "brief" then
               "\n" + ([$i.comments[] | "      · " + ((.body | split("\n") | map(select(length>0)) | first // "") | .[0:150])] | join("\n"))
             else
               "\n" + ([$i.comments[] | "      ┌ \(.createdAt)\n" + (.body | split("\n") | map("      │ " + .) | join("\n"))] | join("\n"))
             end) ]
    end
  | .[]
' "$TMP/board.json"

# Poachable candidates when the lane is empty.
jq -r --arg op "$OPERATOR" --slurpfile issues "$TMP/issues.json" '
  ($issues[0] | map({key:(.number|tostring), value:.}) | from_entries) as $I
  | ([.items[] | select(.status == "Todo" and .responsible == "AI agent")
     | select(((.assignees // []) | index($op)) != null)] | length) as $mine
  | if $mine > 0 then empty else
      ([.items[] | select(.status == "Todo" and .responsible == "AI agent")
        | select(.content.number != null)
        | {n: .content.number, t: (($I[.content.number|tostring].title) // .title), a: ((.assignees // []) | join(","))}]
       | sort_by(.n)
       | map("  POACHABLE #\(.n) — \(.t) (assignee: \(.a))")
       | if length == 0 then ["  board drained — no agent-work Todo anywhere"] else . end | .[])
    end
' "$TMP/board.json"

echo "=== END KANBAN-CHECK REPORT ==="
