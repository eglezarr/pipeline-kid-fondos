# API HTTP de consulta: FastAPI en una función Lambda (imagen Docker) expuesta con una
# Function URL pública. Es de solo lectura: consulta Aurora mediante la Data API y genera
# enlaces temporales a los PDF de S3. Es, junto con la aplicación web, la única vía de acceso
# a los datos.

data "aws_ecr_repository" "api" {
  name = "${local.prefijo}-api"
}

data "aws_ecr_image" "api" {
  repository_name = data.aws_ecr_repository.api.name
  most_recent     = true
}

data "aws_iam_policy_document" "api" {
  # Solo consultas sueltas: la API no abre transacciones
  statement {
    sid       = "DataApiConsultas"
    actions   = ["rds-data:ExecuteStatement"]
    resources = [data.aws_rds_cluster.fondos.arn]
  }

  statement {
    sid       = "LeerCredencialesBaseDatos"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [data.aws_rds_cluster.fondos.master_user_secret[0].secret_arn]
  }

  # Los enlaces temporales a los PDF se firman con las credenciales de la función
  statement {
    sid       = "EnlacesTemporalesKID"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.datos.arn}/download/*"]
  }
}

resource "aws_iam_role" "api" {
  name               = "${local.prefijo}-api-lambda"
  description        = "API HTTP de consulta de los KID"
  assume_role_policy = data.aws_iam_policy_document.confianza_lambda.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "api" {
  name   = "acceso-datos"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.prefijo}-api"
  retention_in_days = var.dias_retencion_logs
}

resource "aws_lambda_function" "api" {
  function_name = "${local.prefijo}-api"
  description   = "API HTTP de consulta de los KID (FastAPI)"
  package_type  = "Image"
  image_uri     = "${data.aws_ecr_repository.api.repository_url}@${data.aws_ecr_image.api.id}"
  role          = aws_iam_role.api.arn
  architectures = ["x86_64"]
  memory_size   = 512
  # Margen para la primera petición tras una pausa de Aurora (la API reintenta unos 40 s)
  timeout = 60

  environment {
    variables = {
      BUCKET_DATOS       = data.aws_s3_bucket.datos.bucket
      AURORA_CLUSTER_ARN = data.aws_rds_cluster.fondos.arn
      AURORA_SECRETO_ARN = data.aws_rds_cluster.fondos.master_user_secret[0].secret_arn
      AURORA_BASE_DATOS  = data.aws_rds_cluster.fondos.database_name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.api,
    aws_iam_role_policy_attachment.api_logs,
    aws_iam_role_policy.api,
  ]
}

# URL HTTPS pública. Con autorización NONE, el proveedor añade los permisos de invocación
# pública (lambda:InvokeFunctionUrl y lambda:InvokeFunction vía Function URL).
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"
}
