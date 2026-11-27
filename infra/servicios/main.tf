# Capa de servicios: lo que se ejecuta sobre la infraestructura base (infra/).
# Se despliega después de construir las imágenes, porque cada función Lambda apunta a la
# imagen más reciente de su repositorio ECR: cuando el workflow sube una imagen nueva,
# Terraform detecta el cambio de digest y actualiza la función.
#
# Los recursos de la base (bucket, repositorios) se leen por nombre con data sources.

data "aws_caller_identity" "actual" {}

locals {
  prefijo = "pipeline-kid"
  sufijo  = substr(sha256(data.aws_caller_identity.actual.account_id), 0, 8)

  # Etapas del pipeline desplegadas como funciones Lambda con imagen Docker
  etapas = {
    descarga = {
      descripcion = "Etapa 1: captura de los KID de una gestora y manifiesto"
      memoria     = 512
      timeout     = 300
    }
  }
}

data "aws_s3_bucket" "datos" {
  bucket = "${local.prefijo}-datos-${local.sufijo}"
}

data "aws_ecr_repository" "etapas" {
  for_each = local.etapas

  name = "${local.prefijo}-${each.key}"
}

data "aws_ecr_image" "etapas" {
  for_each = local.etapas

  repository_name = data.aws_ecr_repository.etapas[each.key].name
  most_recent     = true
}
