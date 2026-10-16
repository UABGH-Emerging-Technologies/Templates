#!/usr/bin/env bash
#
# ado_api.sh — Azure DevOps Server (on-prem) REST transport.
#
# SOURCE this file; do not execute it.  It is the single place the coordination
# scripts speak to ADO, so `kanban_check.sh` and the `next` flow share one dialect
# of auth, api-version and URL shaping instead of each growing its own curl.
#
# Why REST and not the CLI: `az devops` / `az boards` / `az repos` are cloud-only
# and reject this host outright (the CLI's organization-URL canonicaliser returns
# nothing and its connection refuses "works only with Azure DevOps Services").
# There is no command-swap path -- the port is a REST rewrite with a PAT.
#
# Auth is `Authorization: Basic base64(":" + $ADO_PAT)`.  The PAT is read from the
# environment, never written to disk, and never echoed.  Mint one with the
# `vso.work_write`, `vso.code_write` and `vso.project` scopes (collection-scoped)
# and export it as ADO_PAT (this repo keeps it in ~/.profile).
#
# api-version is pinned to 6.0 -- a wrong version is the top on-prem failure mode.
# The one exception is the work-item comments API, still preview on this server: it
# needs 6.0-preview (6.0 returns HTTP 400; verified 2026-10-15).
#
# READ-ONLY BY DEFAULT is expressed by ADO_READONLY=1, which makes every mutation
# helper refuse before it builds a request -- that is how the orientation pass
# guarantees it cannot write.
#
# Low-level primitives (print the raw response body):
#   ado_get    <path> [api-version]           GET
#   ado_query  <path> <json> [api-version]    POST used for READS (WIQL)
#   ado_post   <path> <json> [api-version]    POST mutation   (guarded)
#   ado_patch  <path> <json> [api-version]    PATCH mutation  (guarded)
#
# Domain helpers:
#   ado_wiql          <query>            WIQL -> one work-item id per line
#   ado_subtree       <epic-id>           the Epic's Hierarchy-Forward subtree ids
#   ado_workitems     <id...>            batch work items (JSON)
#   ado_comments      <id> [top]         work-item comments (JSON)
#   ado_prs           <repo-id> [status] pull requests (JSON)
#   ado_pr_workitems  <repo-id> <pr-id>  work items linked to a PR (JSON)
#
set -u

: "${ADO_BASE:=https://anes-vstf.anesthesiology.uab.edu/tfs/DefaultCollection}"
: "${ADO_PROJECT:=Data Science}"
: "${ADO_API:=6.0}"
: "${ADO_COMMENTS_API:=6.0-preview}"
: "${ADO_READONLY:=0}"

# The batch fetch asks for exactly the fields the report reads.  System.BoardColumn
# is included because it exists on User Story (verified) and carries the split-column
# position, though the script keys on System.State + System.Tags, not board position.
ADO_WI_FIELDS="System.Id,System.WorkItemType,System.Title,System.State,System.Tags,System.AssignedTo,System.AreaPath,System.BoardColumn,System.CreatedDate,System.ChangedDate"

ado__err() { echo "ado_api.sh: $*" >&2; return 2; }

ado__auth() {
  [ -n "${ADO_PAT:-}" ] || { ado__err "ADO_PAT is not set (source ~/.profile or export it)"; return 2; }
  printf 'Authorization: Basic %s' "$(printf ':%s' "$ADO_PAT" | base64 -w0)"
}

# "Data Science" -> "Data%20Science"; only spaces need encoding in these paths.
ado__proj() { printf '%s' "${ADO_PROJECT// /%20}"; }

ado__url() { printf '%s/%s' "${ADO_BASE%/}" "${1#/}"; }

ado__request() {  # <method> <path> <body|''> <api-version> [content-type]
  local method="$1" path="$2" body="$3" ver="$4" ctype="${5:-application/json}" sep='?' url
  case "$path" in *\?*) sep='&' ;; esac
  url="$(ado__url "$path")${sep}api-version=${ver}"
  if [ -n "$body" ]; then
    curl -sS -X "$method" -H "$(ado__auth)" -H "Content-Type: ${ctype}" -d "$body" "$url"
  else
    curl -sS -X "$method" -H "$(ado__auth)" "$url"
  fi
}

ado_get()   { ado__request GET  "$1" ""     "${2:-$ADO_API}"; }
ado_query() { ado__request POST "$1" "$2"   "${3:-$ADO_API}"; }

ado__guard_write() {  # <method> <path>
  [ "${ADO_READONLY:-0}" = "1" ] || return 0
  ado__err "refusing ${1} ${2} (ADO_READONLY=1)"
}

# Content type defaults differ by verb: PATCH to a work item is always a JSON-patch
# (application/json-patch+json); POST is a comment/PR (application/json) unless the
# caller overrides it (work-item creation also needs json-patch+json).
ado_post()  { ado__guard_write POST  "$1" || return $?; ado__request POST  "$1" "$2" "${3:-$ADO_API}" "${4:-application/json}"; }
ado_patch() { ado__guard_write PATCH "$1" || return $?; ado__request PATCH "$1" "$2" "${3:-$ADO_API}" "${4:-application/json-patch+json}"; }

# A failed ADO call returns a JSON object carrying "$id"/"message" instead of the
# expected shape.  Failing loudly here beats a caller silently treating an error as
# "no rows" -- an empty board and an auth failure must never look alike.
ado__check() {
  python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except Exception:
    sys.stderr.write("ado_api.sh: non-JSON response: " + raw[:200] + "\n"); sys.exit(1)
if isinstance(d, dict) and "value" not in d and ("$id" in d or "message" in d):
    sys.stderr.write("ado_api.sh: API error: " + json.dumps(d)[:300] + "\n"); sys.exit(1)
sys.stdout.write(raw)
'
}

ado_wiql() {  # <query> -> one work-item id per line
  local q="$1" body
  body="$(python3 -c 'import json,sys; print(json.dumps({"query": sys.argv[1]}))' "$q")"
  ado_query "$(ado__proj)/_apis/wit/wiql" "$body" | python3 -c '
import json, sys
d = json.load(sys.stdin)
if not isinstance(d, dict) or "$id" in d or "message" in d:
    sys.stderr.write("ado_wiql: " + json.dumps(d)[:300] + "\n"); sys.exit(1)
for w in d.get("workItems", []):
    print(w["id"])
for r in d.get("workItemRelations", []):
    t = r.get("target") or {}
    if t.get("id") is not None:
        print(t["id"])
'
}

# The subtree of a scope Epic (or Feature): the source item plus every descendant.
# `MODE(Recursive)` is required -- `MODE(MustContain)` returns only DIRECT children,
# which silently drops grandchildren (a User Story under a Feature under the Epic;
# verified 2026-10-15: MustContain gave Epic->Feature only, Recursive gave the
# full Epic->Feature->User Story chain).  The source appears as a rel-less first
# relation and each descendant as a Hierarchy-Forward relation, so both are collected.
ado_subtree() {  # <epic-id>
  ado_wiql "SELECT [System.Id] FROM WorkItemLinks WHERE ([Source].[System.Id] = $1) AND ([System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward') MODE(Recursive)"
}

# ADO caps a work-item batch at 200 ids per request; chunk and merge.
ado_workitems() {  # <id...> -> JSON
  local -a ids=("$@") i chunk
  [ "${#ids[@]}" -gt 0 ] || { printf '{"count":0,"value":[]}'; return 0; }
  for ((i = 0; i < ${#ids[@]}; i += 200)); do
    chunk="$(IFS=,; echo "${ids[*]:i:200}")"
    ado_get "$(ado__proj)/_apis/wit/workitems?ids=$chunk&fields=$ADO_WI_FIELDS&errorPolicy=omit" | ado__check
  done | jq -s '{count: (map(.value | length) | add // 0), value: (map(.value) | add // [])}'
}

ado_comments() {  # <id> [top] -> JSON
  ado_get "$(ado__proj)/_apis/wit/workItems/$1/comments?\$top=${2:-200}" "$ADO_COMMENTS_API" | ado__check
}

ado_prs() {  # <repo-id> [status] -> JSON
  ado_get "$(ado__proj)/_apis/git/repositories/$1/pullrequests?searchCriteria.status=${2:-all}&\$top=1000" | ado__check
}

ado_pr_workitems() {  # <repo-id> <pr-id> -> JSON
  ado_get "$(ado__proj)/_apis/git/repositories/$1/pullrequests/$2/workitems" | ado__check
}
