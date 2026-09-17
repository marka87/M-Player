#!/bin/bash
# Backward-compatibility trampoline for CI / legacy calls
bash "$(dirname "$0")/scripts/build_linux.sh" "$@"

