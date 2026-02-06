#!/bin/bash

SCRIPT_DIR=$(cd $(dirname ${BASH_SOURCE[0]}) &>/dev/null && pwd)

PROJECT_ROOT=$(cd ${SCRIPT_DIR}/../.. &>/dev/null && pwd)

echo "Project Root: ${PROJECT_ROOT}"

cd "${PROJECT_ROOT}"
uv run exps/gem/process_data.py

exit 0