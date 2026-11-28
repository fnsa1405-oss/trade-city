#!/usr/bin/env bash
# Copia o livro (cópia consistente do SQLite) e o estado do app para o branch de dados e envia.
# Uso: salvar-mesa.sh <livro.db> <pasta-do-branch> <mensagem> [arquivos extras...]
set -u
DB="$1"; WT="$2"; MSG="$3"; shift 3
[ -f "$DB" ] || exit 0
python - "$DB" "$WT/$(basename "$DB")" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
for f in "$@"; do [ -f "$f" ] && cp "$f" "$WT/"; done
cd "$WT"
git config user.name "trade-city-mesa"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -f "$(basename "$DB")" "$@" 2>/dev/null || git add -f .
if git diff --cached --quiet; then exit 0; fi
git commit -q -m "$MSG $(date -u +%Y-%m-%dT%H:%MZ)"
for i in 1 2 3 4; do
  git push -q origin HEAD && exit 0
  sleep $((i * 5))
done
echo "não consegui enviar agora; tento no próximo salvamento"
exit 0
