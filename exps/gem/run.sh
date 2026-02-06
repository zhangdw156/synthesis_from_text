#!/bin/bash

SCIPT_PATH=$(cd $(dirname ${BASH_SOURCE[0]}) &>/dev/null && pwd)
echo "${SCIPT_PATH}"
SCIPT_PATH=$(cd ${SCIPT_PATH}/../.. &>/dev/null && pwd)
echo "${SCIPT_PATH}"

uv run exps/gem/process_data.py

exit 0