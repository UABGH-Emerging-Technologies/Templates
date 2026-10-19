#!/usr/bin/env bash
# Render every PlantUML source beside this script to a PNG via the UMLBot API.
#
#   docs/diagrams/render.sh
#
# The render endpoint is unauthenticated; the LLM /generate endpoints are not
# used here. Override the endpoint with UMLBOT_RENDER_URL.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENDPOINT="${UMLBOT_RENDER_URL:-http://10.23.16.220/umlbot/v01/render}"

python3 - "$DIR" "$ENDPOINT" <<'PY'
import base64, json, os, sys, urllib.error, urllib.request

directory, endpoint = sys.argv[1], sys.argv[2]
failures = []

for name in sorted(os.listdir(directory)):
    if not name.endswith(".puml"):
        continue
    stem = name[: -len(".puml")]
    src = os.path.join(directory, name)
    out = os.path.join(directory, stem + ".png")
    body = json.dumps({"plantuml_code": open(src, encoding="utf-8").read()}).encode()
    req = urllib.request.Request(
        endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode())
        if payload.get("status") != "ok" or not payload.get("image_base64"):
            raise RuntimeError(payload.get("message") or "no image returned")
        raw = base64.b64decode(payload["image_base64"])
        with open(out, "wb") as handle:
            handle.write(raw)
        print(f"{stem:36s} -> ok {len(raw)} bytes")
    except (urllib.error.URLError, RuntimeError) as exc:
        failures.append(stem)
        print(f"{stem:36s} -> FAILED: {exc}")

if failures:
    sys.exit(f"render failed for: {', '.join(failures)}")
print("all diagrams rendered")
PY
