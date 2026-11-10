#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Create .venv and install the project first; see README.md."
  exit 1
fi
exec .venv/bin/python -m streamlit run streamlit_app.py "$@"
