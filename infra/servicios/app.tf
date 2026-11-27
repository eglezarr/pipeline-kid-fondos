# Aplicación web: Streamlit en Amazon ECS Express Mode.
# Express Mode crea y gestiona por nosotros el balanceador de carga con HTTPS, el grupo de
# destino, los grupos de seguridad y el autoescalado, sobre contenedores Fargate en la VPC por
# defecto. La aplicación solo habla con la API pública, así que no necesita permisos sobre los
# datos: no tiene rol de tarea.
#
# Coste: a diferencia de Lambda, el servicio cobra por hora mientras existe (Fargate, balanceador
# e IP públicas). Se fija una sola tarea pequeña y se elimina con `terraform destroy` al terminar.

data "aws_ecr_repository" "app" {
  name = "${local.prefijo}-app"
}

data "aws_ecr_image" "app" {
  repository_name = data.aws_ecr_repository.app.name
  most_recent     = true
}

resource "aws_ecs_cluster" "app" {
  name = local.prefijo
}

# Rol de ejecución: ECS lo usa para descargar la imagen de ECR y enviar los logs a CloudWatch
data "aws_iam_policy_document" "confianza_tareas_ecs" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app_ejecucion" {
  name               = "${local.prefijo}-app-ejecucion"
  description        = "Descarga de la imagen y logs de la aplicacion web"
  assume_role_policy = data.aws_iam_policy_document.confianza_tareas_ecs.json
}

data "aws_iam_policy" "ejecucion_tareas_ecs" {
  name = "AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy_attachment" "app_ejecucion" {
  role       = aws_iam_role.app_ejecucion.name
  policy_arn = data.aws_iam_policy.ejecucion_tareas_ecs.arn
}

# Rol de infraestructura: ECS Express lo usa para crear el balanceador, la red y el autoescalado
data "aws_iam_policy_document" "confianza_ecs" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app_infraestructura" {
  name               = "${local.prefijo}-app-infraestructura"
  description        = "Recursos gestionados por ECS Express Mode para la aplicacion web"
  assume_role_policy = data.aws_iam_policy_document.confianza_ecs.json
}

data "aws_iam_policy" "infraestructura_ecs_express" {
  name = "AmazonECSInfrastructureRoleforExpressGatewayServices"
}

resource "aws_iam_role_policy_attachment" "app_infraestructura" {
  role       = aws_iam_role.app_infraestructura.name
  policy_arn = data.aws_iam_policy.infraestructura_ecs_express.arn
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/ecs/${local.prefijo}-app"
  retention_in_days = var.dias_retencion_logs
}

resource "aws_ecs_express_gateway_service" "app" {
  service_name            = "${local.prefijo}-app"
  cluster                 = aws_ecs_cluster.app.name
  execution_role_arn      = aws_iam_role.app_ejecucion.arn
  infrastructure_role_arn = aws_iam_role.app_infraestructura.arn
  cpu                     = "512"  # 0,5 vCPU
  memory                  = "1024" # 1 GB
  # Ruta de salud de Streamlit: el balanceador la consulta para saber si la tarea está lista
  health_check_path = "/_stcore/health"
  # Terraform espera a que el servicio esté sano: si la aplicación no arranca, el despliegue falla
  wait_for_steady_state = true

  primary_container {
    image          = "${data.aws_ecr_repository.app.repository_url}@${data.aws_ecr_image.app.id}"
    container_port = 8501

    aws_logs_configuration {
      log_group         = aws_cloudwatch_log_group.app.name
      log_stream_prefix = "streamlit"
    }

    environment {
      name  = "API_URL"
      value = aws_lambda_function_url.api.function_url
    }
  }

  # Una sola tarea: limita el coste (la aplicación tiene poco tráfico). La métrica y el objetivo
  # son los valores por defecto de AWS; se declaran para que Terraform no detecte diferencias.
  scaling_target {
    min_task_count            = 1
    max_task_count            = 1
    auto_scaling_metric       = "AVERAGE_CPU"
    auto_scaling_target_value = 60
  }

  # Los permisos deben existir hasta que el servicio se haya borrado del todo
  depends_on = [
    aws_iam_role_policy_attachment.app_ejecucion,
    aws_iam_role_policy_attachment.app_infraestructura,
  ]
}
