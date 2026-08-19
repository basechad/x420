#!/bin/sh
# Install the x420 git hooks.
#
# Copies into .git/hooks rather than setting core.hooksPath, so no git config is modified.
# Re-run after cloning — .git/hooks is not version controlled, which is why the source of
# truth lives here in scripts/hooks/.

set -e

ROOT="$(git rev-parse --show-toplevel)"
install -m 755 "$ROOT/scripts/hooks/pre-commit" "$ROOT/.git/hooks/pre-commit"
echo "installed: .git/hooks/pre-commit"
