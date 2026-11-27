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

# Etapa 2: leer los PDF de download/ y escribir el Markdown en markdown/
data "aws_iam_policy_document" "markdown" {
  statement {
    sid       = "ComprobarBucket"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.datos.arn]
  }

  statement {
    sid       = "LeerDescargas"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.datos.arn}/download/*"]
  }

  statement {
    sid       = "EscribirMarkdown"
    actions   = ["s3:PutObject"]
    resources = ["${data.aws_s3_bucket.datos.arn}/markdown/*"]
  }
}

# Etapa 3: leer el Markdown y el manifiesto, invocar el modelo y escribir en extraction/
data "aws_iam_policy_document" "extraccion" {
  statement {
    sid       = "ComprobarBucket"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.datos.arn]
  }

  statement {
    sid     = "LeerMarkdownYManifiesto"
    actions = ["s3:GetObject"]
    resources = [
      "${data.aws_s3_bucket.datos.arn}/markdown/*",
      "${data.aws_s3_bucket.datos.arn}/download/*",
    ]
  }

  statement {
    sid       = "EscribirExtraccion"
    actions   = ["s3:PutObject"]
    resources = ["${data.aws_s3_bucket.datos.arn}/extraction/*"]
  }

  # Un perfil de inferencia global reparte las peticiones entre regiones: hacen falta permisos
  # sobre el perfil y sobre el modelo fundacional en cualquier región
  statement {
    sid     = "InvocarModelo"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:*:${data.aws_caller_identity.actual.account_id}:inference-profile/*",
      "arn:aws:bedrock:*::foundation-model/*",
    ]
  }
}

# Etapa 4: leer los JSON de extraction/ y escribir en Aurora mediante la Data API
data "aws_iam_policy_document" "carga" {
  statement {
    sid       = "ComprobarBucket"
    actions   = ["s3:ListBucket"]
    resources = [data.aws_s3_bucket.datos.arn]
  }

  statement {
    sid       = "LeerExtraccion"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.datos.arn}/extraction/*"]
  }

  statement {
    sid = "DataApi"
    actions = [
      "rds-data:ExecuteStatement",
      "rds-data:BeginTransaction",
      "rds-data:CommitTransaction",
      "rds-data:RollbackTransaction",
    ]
    resources = [data.aws_rds_cluster.fondos.arn]
  }

  # La Data API usa las credenciales guardadas en Secrets Manager en nombre de la función
  statement {
    sid       = "LeerCredencialesBaseDatos"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_rds_cluster.fondos.master_user_secret[0].secret_arn]
  }
}

locals {
  politicas_etapas = {
    descarga   = data.aws_iam_policy_document.descarga.json
    markdown   = data.aws_iam_policy_document.markdown.json
    extraccion = data.aws_iam_policy_document.extraccion.json
    carga      = data.aws_iam_policy_document.carga.json
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
    variables = merge(
      { BUCKET_DATOS = data.aws_s3_bucket.datos.bucket },
      each.value.variables,
    )
  }

  depends_on = [
    aws_cloudwatch_log_group.etapas,
    aws_iam_role_policy_attachment.etapas_logs,
    aws_iam_role_policy.etapas,
  ]
}
