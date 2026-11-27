#!/usr/bin/env bash
# Arranque de la cuenta de AWS para el proyecto. Se ejecuta UNA sola vez en
# AWS CloudShell (ya autenticado con el usuario administrador):
#
#   git clone https://github.com/eglezarr/pipeline-kid-fondos.git
#   bash pipeline-kid-fondos/infra/bootstrap/arrancar.sh
#
# Qué hace:
#   1. Instala Terraform si no está disponible.
#   2. Crea el bucket privado donde Terraform guarda su estado (si no existe).
#   3. Aplica la configuración de esta carpeta: proveedor OIDC de GitHub y rol
#      de despliegue. Terraform muestra el plan y pide confirmación ("yes").
#   4. Muestra el ARN del rol, que se guarda como secreto AWS_ROLE_ARN en GitHub.
#
# Es idempotente: si se vuelve a ejecutar, no duplica nada.

set -euo pipefail

REGION="eu-west-3"
cd "$(dirname "$0")"

echo "== Identidad"
aws sts get-caller-identity --query Arn --output text
CUENTA=$(aws sts get-caller-identity --query Account --output text)

# Sufijo anónimo y estable (no expone el ID de la cuenta en los nombres)
SUFIJO=$(printf '%s' "$CUENTA" | sha256sum | cut -c1-8)
BUCKET_ESTADO="pipeline-kid-tfstate-${SUFIJO}"

echo "== Terraform"
if ! command -v terraform >/dev/null 2>&1; then
  echo "Instalando Terraform..."
  sudo dnf install -y -q dnf-plugins-core
  sudo dnf config-manager --add-repo https://rpm.releases.hashicorp.com/AmazonLinux/hashicorp.repo
  sudo dnf install -y -q terraform
fi
terraform version | head -1

echo "== Bucket del estado: ${BUCKET_ESTADO}"
if aws s3api head-bucket --bucket "$BUCKET_ESTADO" 2>/dev/null; then
  echo "Ya existe."
else
  aws s3api create-bucket --bucket "$BUCKET_ESTADO" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET_ESTADO" \
    --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  # Versionado: permite recuperar una versión anterior del estado si se corrompe
  aws s3api put-bucket-versioning --bucket "$BUCKET_ESTADO" \
    --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption --bucket "$BUCKET_ESTADO" \
    --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  echo "Creado (privado, versionado y cifrado)."
fi

# Los proveedores de Terraform ocupan cientos de MB: se guardan en /tmp para no
# llenar el espacio persistente de CloudShell (1 GB)
export TF_DATA_DIR="/tmp/pipeline-kid-bootstrap"

echo "== Terraform init"
terraform init -input=false -reconfigure \
  -backend-config="bucket=${BUCKET_ESTADO}" \
  -backend-config="region=${REGION}"

echo "== Proveedor OIDC de GitHub"
# Si este Terraform ya lo gestiona (está en su estado), se mantiene. Solo se
# reutiliza sin gestionarlo cuando existía en la cuenta antes del arranque.
if terraform state list 2>/dev/null | grep -q '^aws_iam_openid_connect_provider.github'; then
  echo "Gestionado por este Terraform: se mantiene."
  CREAR_OIDC=true
else
  EXISTENTE=$(aws iam list-open-id-connect-providers \
    --query "OpenIDConnectProviderList[?ends_with(Arn, 'token.actions.githubusercontent.com')].Arn" \
    --output text)
  if [ -n "$EXISTENTE" ]; then
    echo "Ya existía en la cuenta: se reutiliza sin gestionarlo."
    CREAR_OIDC=false
  else
    echo "No existe: lo crea Terraform."
    CREAR_OIDC=true
  fi
fi

echo "== Terraform apply: revisa el plan; si indica algo en \"to destroy\", responde no"
terraform apply -var "crear_proveedor_oidc=${CREAR_OIDC}"

echo
echo "== Listo. Guarda este valor como secreto AWS_ROLE_ARN en GitHub:"
terraform output -raw rol_despliegue_arn
echo
