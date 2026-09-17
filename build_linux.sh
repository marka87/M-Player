#!/bin/bash
# Backward-compatibility trampoline for CI / legacy calls
exec "$(dirname "$0")/scripts/build_linux.sh" "$@"
