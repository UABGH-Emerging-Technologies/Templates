#!/usr/bin/env bash
#
# board.sh — the ADO implementation of the coordination verb vocabulary.
#
# process/next.md speaks in coordination statuses and these verbs; everything
# ADO-shaped (states, tags, REST paths, api-versions) lives here and in ado_api.sh.
# A session calls `process/board.sh <verb>` and never composes a REST call itself.
#
#   orient   --scope <id> [--comments brief|full]   the read-only report (kanban_check.sh)
#   show     <id>                                  work-item fields
#   comments <id>                                  comment list (JSON)
#   create   --type Feature|Story --parent <id> --title <t> --body-file <f> [--tag <t>] [--assign <a>]
#   status   <id> <coord-status>                    set the coordination status
#   tag      <id> <tag> [--remove]
#   assign   <id> <human>
#   comment  <id> --body-file <f>                   post a comment; prints its id
#   claim    <id> --nonce <n>                       check -> comment -> verify; exit!=0 if lost
#   pr       --draft --branch <b> --title <t> --body-file <f> [--work-item <id>]
#
# Coordination status -> native state + tag:
#   Unshaped              Feature: New
#   Todo                  User Story: New + tag agent-work
#   Agent-working         User Story: Active
#   Awaiting-code-review  User Story: Resolved, no human-review
#   Awaiting-human-action User Story: Resolved + tag human-review
#   Done                  User Story: Closed
#
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/ado_api.sh"
CONF="$DIR/../board.conf"
[ -f "$CONF" ] && . "$CONF"
: "${BOARD_REPO_ID:=b65b2ef6-085b-4e36-af32-ea4046a7639e}"
: "${BOARD_OPERATOR:=}"

board__operator() {
  if [ -n "$BOARD_OPERATOR" ]; then printf '%s' "$BOARD_OPERATOR"; return; fi
  ado_get "_apis/connectionData" "1.0" | jq -r '.authenticatedUser.providerDisplayName'
}

board__wi() { printf '%s/_apis/wit/workitems/%s' "$(ado__proj)" "$1"; }
board__patch() { ado_patch "$(board__wi "$1")" "$2"; }

board__tags() {  # <id> -> current tags (comma-separated; empty if none)
  ado_get "$(board__wi "$1")?fields=System.Tags" | jq -r '.fields["System.Tags"] // ""'
}

board__comments() { ado_comments "$1" | jq '.comments // []'; }

board__post_comment() {  # <id> <text> -> comment id
  local payload; payload="$(jq -cn --arg t "$2" '{text:$t}')"
  ado_post "$(ado__proj)/_apis/wit/workItems/$1/comments" "$payload" "$ADO_COMMENTS_API" \
    | ado__check | jq -r '.id'
}

board__witype() { case "$1" in Story | "User Story") echo "User Story" ;; *) echo "$1" ;; esac; }

board_tag() {  # <id> <tag> [--remove]
  local id="$1" tag="$2" remove="${3:-}" cur new
  cur="$(board__tags "$id")"
  if [ "$remove" = "--remove" ]; then
    new="$(printf '%s' "$cur" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | grep -vx "$tag" | paste -sd, -)"
  else
    case ",${cur}," in *",$tag,"*) new="$cur" ;; *) new="${cur:+$cur,}$tag" ;; esac
  fi
  board__patch "$id" "$(jq -cn --arg v "$new" '[{op:"add",path:"/fields/System.Tags",value:$v}]')" >/dev/null
  printf '%s\n' "$new"
}

board_status() {  # <id> <coord-status>
  local id="$1" want="$2" state
  case "$want" in
    Unshaped) state=New ;;
    Todo) state=New ;;
    Agent-working) state=Active ;;
    Awaiting-code-review) state=Resolved ;;
    Awaiting-human-action) state=Resolved ;;
    Done) state=Closed ;;
    *) echo "status: unknown coordination status '$want'" >&2; return 2 ;;
  esac
  board__patch "$id" "$(jq -cn --arg v "$state" '[{op:"add",path:"/fields/System.State",value:$v}]')" >/dev/null
  case "$want" in
    Todo) board_tag "$id" agent-work >/dev/null ;;
    Awaiting-human-action) board_tag "$id" human-review >/dev/null ;;
    Awaiting-code-review) board_tag "$id" human-review --remove >/dev/null ;;
  esac
  printf '%s\n' "$want"
}

board_claim() {  # <id> <nonce> -> 0 if won, 1 if lost
  local id="$1" nonce="$2" op marker live cid winner
  op="$(board__operator)"
  marker="Claiming: ${op} · ${nonce}"
  live="$(board__comments "$id" | jq -r '[.[] | select((.text // "") | test("^(Claiming|Processed):")) | select((.text // "") | test("\\\\(superseded") | not)] | last | .id // empty')"
  if [ -n "$live" ]; then echo "lost: live claim ${live} present" >&2; return 1; fi
  cid="$(board__post_comment "$id" "$marker")"
  winner="$(board__comments "$id" | jq -r '[.[] | select((.text // "") | test("^(Claiming|Processed):"))] | map(.id) | min // empty')"
  if [ "$winner" = "$cid" ]; then printf '%s\n' "$cid"; return 0; fi
  ado_patch "$(ado__proj)/_apis/wit/workItems/$id/comments/$cid" \
    "$(jq -cn --arg t "$marker (superseded)" '{text:$t}')" "$ADO_COMMENTS_API" "application/json" >/dev/null
  echo "lost: claim $cid, winner $winner" >&2; return 1
}

cmd="${1:-}"; shift || true

case "$cmd" in
  orient) exec "$DIR/kanban_check.sh" "$@" ;;

  show) ado_get "$(board__wi "$1")?fields=$ADO_WI_FIELDS" | ado__check | jq . ;;

  comments) board__comments "$1" ;;

  create)
    type=""; parent=""; title=""; bodyfile=""; tags=""; assign=""
    while [ $# -gt 0 ]; do case "$1" in
      --type) type="$2"; shift 2 ;;
      --parent) parent="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      --body-file) bodyfile="$2"; shift 2 ;;
      --tag) tags="$2"; shift 2 ;;
      --assign) assign="$2"; shift 2 ;;
      *) echo "create: unknown flag $1" >&2; exit 2 ;;
    esac; done
    [ -n "$type" ] && [ -n "$parent" ] && [ -n "$title" ] || { echo "create needs --type --parent --title" >&2; exit 2; }
    body="$(cat "${bodyfile:-/dev/null}" 2>/dev/null || echo "")"
    parent_url="${ADO_BASE%/}/${ADO_PROJECT// /%20}/_apis/wit/workItems/$parent"
    patch="$(jq -cn --arg t "$title" --arg b "$body" --arg a "${BOARD_AREA:-}" --arg tg "$tags" --arg assignee "${assign:-}" --arg url "$parent_url" '
      [{op:"add",path:"/fields/System.Title",value:$t}]
      + (if $b  == "" then [] else [{op:"add",path:"/fields/System.Description",value:$b}] end)
      + (if $a  == "" then [] else [{op:"add",path:"/fields/System.AreaPath",value:$a}] end)
      + (if $tg == "" then [] else [{op:"add",path:"/fields/System.Tags",value:$tg}] end)
      + (if $assignee == "" then [] else [{op:"add",path:"/fields/System.AssignedTo",value:$assignee}] end)
      + [{op:"add",path:"/relations/-",value:{rel:"System.LinkTypes.Hierarchy-Reverse",url:$url}}]')"
    wtype="$(board__witype "$type" | sed 's/ /%20/g')"
    ado_post "$(ado__proj)/_apis/wit/workitems/\$$wtype" "$patch" "$ADO_API" "application/json-patch+json" | ado__check \
      | jq '{id: .id, url: ._links.html.href}'
    ;;

  status) board_status "$1" "$2" ;;

  tag)
    if [ "${3:-}" = "--remove" ]; then board_tag "$1" "$2" --remove; else board_tag "$1" "$2"; fi
    ;;

  assign)
    board__patch "$1" "$(jq -cn --arg v "$2" '[{op:"add",path:"/fields/System.AssignedTo",value:$v}]')" >/dev/null
    printf '%s\n' "$2"
    ;;

  comment)
    id="$1"; shift; bodyfile=""
    while [ $# -gt 0 ]; do case "$1" in --body-file) bodyfile="$2"; shift 2 ;; *) shift ;; esac; done
    board__post_comment "$id" "$(cat "$bodyfile")"
    ;;

  claim)
    id="$1"; shift; nonce=""
    while [ $# -gt 0 ]; do case "$1" in --nonce) nonce="$2"; shift 2 ;; *) shift ;; esac; done
    [ -n "$nonce" ] || { echo "claim needs --nonce" >&2; exit 2; }
    board_claim "$id" "$nonce"
    ;;

  pr)
    branch=""; title=""; bodyfile=""; draft=0
    while [ $# -gt 0 ]; do case "$1" in
      --draft) draft=1; shift ;;
      --branch) branch="$2"; shift 2 ;;
      --title) title="$2"; shift 2 ;;
      --body-file) bodyfile="$2"; shift 2 ;;
      --work-item) shift 2 ;;
      *) shift ;;
    esac; done
    payload="$(jq -cn --arg s "refs/heads/$branch" --arg t "$title" \
      --arg d "$(cat "${bodyfile:-/dev/null}" 2>/dev/null || echo "")" --argjson dr "$draft" \
      '{sourceRefName:$s,targetRefName:"refs/heads/main",title:$t,description:$d,isDraft:($dr==1)}')"
    ado_post "$(ado__proj)/_apis/git/repositories/$BOARD_REPO_ID/pullrequests" "$payload" | ado__check \
      | jq '{id: .pullRequestId, url: ._links.html.href, isDraft}'
    ;;

  "" | -h | --help) sed -n '2,31p' "$0" ;;

  *) echo "board.sh: unknown verb '$cmd'" >&2; exit 2 ;;
esac
