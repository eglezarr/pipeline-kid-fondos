# Arranque de la cuenta: conexión entre GitHub Actions y AWS mediante OIDC.
#
# Se aplica una sola vez, con credenciales de administrador, desde CloudShell
# (ver arrancar.sh). A partir de aquí, el resto de la infraestructura (infra/)
# la despliega GitHub Actions asumiendo el rol que se crea en este fichero.
#
# El bucket del estado de Terraform lo crea arrancar.sh antes de ejecutar
# Terraform, porque tiene que existir para poder guardar el estado en él.

terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Configuración parcial: bucket y región se pasan en terraform init (-backend-config)
  backend "s3" {
    key          = "bootstrap/terraform.tfstate"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Proyecto = "pipeline-kid-fondos"
      Gestion  = "terraform-bootstrap"
    }
  }
}

data "aws_caller_identity" "actual" {}

locals {
  host_oidc_github = "token.actions.githubusercontent.com"

  # Si el proveedor OIDC ya existía en la cuenta, se referencia por su ARN
  arn_proveedor_oidc = (
    var.crear_proveedor_oidc
    ? aws_iam_openid_connect_provider.github[0].arn
    : "arn:aws:iam::${data.aws_caller_identity.actual.account_id}:oidc-provider/${local.host_oidc_github}"
  )

  # Sujetos (claim "sub" del token de GitHub) autorizados a asumir el rol
  propietario         = split("/", var.repositorio)[0]
  nombre_repo         = split("/", var.repositorio)[1]
  sujetos_autorizados = [
    "repo:${var.repositorio}:ref:refs/heads/${var.rama}",
    "repo:${local.propietario}@${var.id_propietario}/${local.nombre_repo}@${var.id_repositorio}:ref:refs/heads/${var.rama}",
  ]
}

# Proveedor de identidad: AWS confía en los tokens que emite GitHub Actions
resource "aws_iam_openid_connect_provider" "github" {
  count = var.crear_proveedor_oidc ? 1 : 0

  url            = "https://${local.host_oidc_github}"
  client_id_list = ["sts.amazonaws.com"]
}

# Política de confianza: solo los workflows de la rama principal de este repositorio
# pueden asumir el rol. Es la condición que impide que otro repositorio lo use.
data "aws_iam_policy_document" "confianza_github" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.arn_proveedor_oidc]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.host_oidc_github}:aud"
      values   = ["sts.amazonaws.com"]
    }

    # GitHub emite el "sub" con identificadores inmutables en los repositorios creados
    # desde julio de 2026 (propietario@id/repo@id). Se aceptan ambos formatos.
    condition {
      test     = "StringEquals"
      variable = "${local.host_oidc_github}:sub"
      values   = local.sujetos_autorizados
    }
  }
}

resource "aws_iam_role" "despliegue_github" {
  name                 = "pipeline-kid-github-deploy"
  description          = "Rol que asume GitHub Actions (OIDC) para desplegar pipeline-kid-fondos"
  assume_role_policy   = data.aws_iam_policy_document.confianza_github.json
  max_session_duration = 3600
}

# Permisos amplios por simplicidad: el acceso queda acotado por la política de
# confianza (un único repositorio y rama). Decisión documentada en el README.
resource "aws_iam_role_policy_attachment" "despliegue_github_admin" {
  role       = aws_iam_role.despliegue_github.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}
