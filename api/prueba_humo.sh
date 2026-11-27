#!/usr/bin/env bash
# Prueba de humo de la API desplegada: llama a cada ruta, comprueba el código HTTP y muestra
# un extracto de las respuestas. La usa el workflow de despliegue tras aplicar Terraform.
#
# Uso: bash api/prueba_humo.sh https://<id>.lambda-url.eu-west-3.on.aws
set -euo pipefail

url=${1:?indica la URL de la API}
url=${url%/}
respuesta=$(mktemp)

# pedir <ruta> <código esperado>: falla si la API responde con otro código.
# Un 503 indica que Aurora se está reanudando tras una pausa: se espera y se repite.
pedir() {
  local ruta=$1 esperado=$2 codigo intento
  for intento in 1 2 3 4; do
    codigo=$(curl -sS -o "$respuesta" -w '%{http_code}' --max-time 70 "$url$ruta")
    [ "$codigo" = "503" ] || break
    echo "     503 en $ruta (Aurora reanudándose), intento $intento; nueva petición en 15 s"
    sleep 15
  done
  if [ "$codigo" != "$esperado" ]; then
    echo "ERROR: $ruta devolvió $codigo (se esperaba $esperado)"
    cat "$respuesta"; echo
    exit 1
  fi
  echo "OK   $codigo  $ruta"
}

echo "API: $url"
pedir /health 200

pedir /resumen 200
jq -c '{fondos, documentos, gestoras, ultima_actualizacion, calidad}' "$respuesta"
jq -r '"     SRI: " + (.distribucion_sri | map("\(.sri)→\(.fondos)") | join("  "))' "$respuesta"

pedir /gestoras 200
jq -r '.[] | "     \(.fuente): \(.fondos) fondos, SRI medio \(.sri_medio), gastos corrientes medios \(.gastos_corrientes_medio) %"' "$respuesta"

pedir /fondos 200
echo "     $(jq length "$respuesta") fondos"
isin=$(jq -r '.[0].isin' "$respuesta")

pedir "/fondos?fuente=azvalor&orden=gastos" 200
jq -r '.[] | "     \(.isin)  SRI \(.sri)  gastos \(.gastos_corrientes_pct) %  \(.nombre_producto) \(.nombre_clase // "")"' "$respuesta"

pedir "/fondos?sri_max=2&texto=renta" 200
echo "     $(jq length "$respuesta") fondos de SRI ≤ 2 con «renta» en el nombre"

pedir "/fondos/$isin" 200
jq -c '{isin, nombre_producto, sri, gastos_corrientes_pct, validaciones,
        evidencias_verificadas: ([.verificacion_evidencias[] | select(.)] | length),
        versiones: (.historial | length)}' "$respuesta"

# Errores esperados: ISIN inexistente, ISIN mal formado, filtros incoherentes
pedir /fondos/ES0000000000 404
pedir /fondos/ES01 422
pedir "/fondos?sri_min=5&sri_max=2" 422

# El PDF original: redirección a un enlace temporal de S3 que devuelve un PDF
pedir "/fondos/$isin/kid" 307
curl -sS -L --max-time 30 -o "$respuesta" "$url/fondos/$isin/kid"
[ "$(head -c 5 "$respuesta")" = "%PDF-" ] || { echo "ERROR: el enlace del KID no devuelve un PDF"; exit 1; }
echo "     el enlace temporal devuelve el PDF del KID"

pedir /docs 200
pedir /openapi.json 200

echo "Prueba de humo superada"
