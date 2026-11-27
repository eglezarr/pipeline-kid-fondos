#!/usr/bin/env bash
# Invoca una función Lambda de forma síncrona, muestra el final de su log y guarda la respuesta.
# Termina con error si la función ha fallado (la respuesta contiene errorMessage).
#
# Uso: scripts/invocar_lambda.sh <función> <fichero-evento.json> <fichero-respuesta.json>

set -euo pipefail

funcion="$1"
evento="$2"
respuesta="$3"

aws lambda invoke --function-name "$funcion" \
  --cli-binary-format raw-in-base64-out \
  --payload "file://${evento}" \
  --cli-read-timeout 900 --log-type Tail \
  --query LogResult --output text "$respuesta" | base64 -d
echo
echo "== Respuesta de ${funcion}"
jq . "$respuesta"
if jq -e 'type == "object" and has("errorMessage")' "$respuesta" > /dev/null; then
  exit 1
fi
