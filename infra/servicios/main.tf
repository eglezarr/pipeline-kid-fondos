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

  # Etapas del pipeline desplegadas como funciones Lambda con imagen Docker.
  # `variables`: variables de entorno propias de la etapa (además de BUCKET_DATOS).
  etapas = {
    descarga = {
      descripcion = "Etapa 1: captura de los KID de una gestora y manifiesto"
      memoria     = 512
      timeout     = 300
      variables   = {}
    }
    markdown = {
      descripcion = "Etapa 2: conversion de los KID de PDF a Markdown (con OCR)"
      memoria     = 3008 # mas memoria = mas CPU para el OCR (3008 MB es el maximo en cuentas nuevas)
      timeout     = 900
      variables   = {}
    }
    extraccion = {
      descripcion = "Etapa 3: extraccion de los datos del KID con Bedrock (salida estructurada)"
      memoria     = 512
      timeout     = 900
      variables = {
        MODELO_BEDROCK          = var.modelo_bedrock
        EXTRACCION_CONCURRENCIA = "4"
      }
    }
    carga = {
      descripcion = "Etapa 4: carga de los datos extraidos en PostgreSQL (Aurora, RDS Data API)"
      memoria     = 256
      timeout     = 600
      variables = {
        AURORA_CLUSTER_ARN = data.aws_rds_cluster.fondos.arn
        AURORA_SECRETO_ARN = data.aws_rds_cluster.fondos.master_user_secret[0].secret_arn
        AURORA_BASE_DATOS  = data.aws_rds_cluster.fondos.database_name
      }
    }
  }
}

data "aws_rds_cluster" "fondos" {
  cluster_identifier = "${local.prefijo}-bd"
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
