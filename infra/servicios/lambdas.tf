# Funciones Lambda de las etapas del pipeline.
# Cada etapa tiene su propio rol con los permisos mínimos que necesita (principio de mínimo
# privilegio), además del permiso estándar para escribir sus logs en CloudWatch.

data "aws_iam_policy_document" "confianza_lambda" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Etapa 1: comprobar el bucket y escribir en download/
data "aws_iam_policy_document" "descarga" {
  statement {
    sid       = "ComprobarBucket"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.datos.arn]
  }

  statement {
    sid       = "EscribirDescargas"
    actions   = ["s3:PutObject"]
    resources = ["${data.aws_s3_bucket.datos.arn}/download/*"]
  }
}

locals {
  politicas_etapas = {
    descarga = data.aws_iam_policy_document.descarga.json
  }
}

resource "aws_iam_role" "etapas" {
  for_each = local.etapas

  name               = "${local.prefijo}-${each.key}-lambda"
  description        = each.value.descripcion
  assume_role_policy = data.aws_iam_policy_document.confianza_lambda.json
}

resource "aws_iam_role_policy_attachment" "etapas_logs" {
  for_each = local.etapas

  role       = aws_iam_role.etapas[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "etapas" {
  for_each = local.etapas

  name   = "acceso-datos"
  role   = aws_iam_role.etapas[each.key].id
  policy = local.politicas_etapas[each.key]
}

resource "aws_cloudwatch_log_group" "etapas" {
  for_each = local.etapas

  name              = "/aws/lambda/${local.prefijo}-${each.key}"
  retention_in_days = var.dias_retencion_logs
}

resource "aws_lambda_function" "etapas" {
  for_each = local.etapas

  function_name = "${local.prefijo}-${each.key}"
  description   = each.value.descripcion
  package_type  = "Image"
  image_uri     = "${data.aws_ecr_repository.etapas[each.key].repository_url}@${data.aws_ecr_image.etapas[each.key].id}"
  role          = aws_iam_role.etapas[each.key].arn
  architectures = ["x86_64"]
  memory_size   = each.value.memoria
  timeout       = each.value.timeout

  environment {
    variables = {
      BUCKET_DATOS = data.aws_s3_bucket.datos.bucket
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.etapas,
    aws_iam_role_policy_attachment.etapas_logs,
    aws_iam_role_policy.etapas,
  ]
}
