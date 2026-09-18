#!/bin/sh
set -eu
TEST_HOME=$(CDPATH='' cd -P "$(dirname "$0")" && pwd)
cd "$TEST_HOME/.."
for script in nanowrt lib/*.sh tests/run.sh; do
    sh -n "$script"
done
if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -s sh -e SC1091,SC2034 nanowrt lib/*.sh tests/run.sh
fi
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py' -v
