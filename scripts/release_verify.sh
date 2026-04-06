#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Clean build =="
rm -rf dist build ./*.egg-info
python3 -m build
python3 -m twine check dist/*

WHEEL="$(ls -1 dist/omniclaw-*.whl | tail -n 1)"
VERSION="$(basename "$WHEEL")"
VERSION="${VERSION#omniclaw-}"
VERSION="${VERSION%-py3-none-any.whl}"
echo "== Verify built wheel =="
python3 scripts/verify_release_artifact.py "$WHEEL"

cat <<EOF

Built wheel verified:
  $WHEEL

Next steps:
1. Upload:
   python3 -m twine upload dist/*
2. Verify the published artifact:
   python3 scripts/verify_release_artifact.py --download-version $VERSION

EOF
