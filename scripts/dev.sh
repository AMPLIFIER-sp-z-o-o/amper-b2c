#!/bin/bash
# The dev supervisor now lives in dev.mjs — a single resilient implementation that restarts a
# crashed server (Django / Vite) INDEPENDENTLY instead of tearing the whole env down, and does a
# clean process-TREE kill on exit (no orphaned python/node, no bound ports). This wrapper stays so
# `./scripts/dev.sh` keeps working; it just delegates. `exec` hands signals straight to node so
# Ctrl-C shuts everything down cleanly.
exec node "$(dirname "$0")/dev.mjs"
