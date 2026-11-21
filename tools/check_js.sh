#!/usr/bin/env bash
# Syntax of every JavaScript file of the project (#341), without running it: node --check.
# The graph modules (references/static/references/graph/) are ES modules: given on the
# standard input with --input-type=module, since a .js file alone is read as CommonJS.
# The other files are classic scripts (static/js/, loaded with <script defer>; the
# benchmark scripts, evaluated in the page by tools/graph_bench/). Vendored files are left
# out. Every file is checked, then the script fails if one of them has an error.
set -u
cd "$(dirname "$0")/.."

# A syntax error must fail the check: otherwise the check itself is broken.
if echo "export const broken = ;" | node --input-type=module --check 2>/dev/null; then
    echo "node --check accepted a syntax error" >&2
    exit 1
fi

status=0
while read -r file; do
    case "$file" in
        references/static/references/graph/*) node --input-type=module --check < "$file" ;;
        *) node --check "$file" ;;
    esac || { echo "Syntax error: $file" >&2; status=1; }
done < <(git ls-files '*.js' ':!:**/vendor/**')
echo "$(git ls-files '*.js' ':!:**/vendor/**' | wc -l) files checked"
exit $status
