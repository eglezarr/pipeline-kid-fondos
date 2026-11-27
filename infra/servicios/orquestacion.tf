# Orquestación del pipeline con Step Functions y ejecución programada con EventBridge Scheduler.
#
# La máquina de estados recibe {"gestoras": ["bestinver", "azvalor"]} y, para cada gestora (en
# paralelo), ejecuta en serie las cuatro etapas: la respuesta de cada función Lambda es la entrada
# de la siguiente. Si una etapa falla, esa gestora se marca como fallida sin detener a las demás, y
# al final la ejecución termina en error si alguna ha fallado (para que se vea en la consola).

locals {
  # Reintentos ante errores transitorios del servicio Lambda (no ante errores del código)
  reintentos_lambda = [{
    ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException", "Lambda.TooManyRequestsException"]
    IntervalSeconds = 5
    MaxAttempts     = 3
    BackoffRate     = 2
  }]

  # Cualquier error de una etapa: se guarda en $.error y la gestora pasa a GestoraFallida
  captura_errores = [{
    ErrorEquals = ["States.ALL"]
    ResultPath  = "$.error"
    Next        = "GestoraFallida"
  }]

  tarea_lambda = {
    Type       = "Task"
    Resource   = "arn:aws:states:::lambda:invoke"
    OutputPath = "$.Payload" # solo la respuesta de la función pasa al siguiente estado
    Retry      = local.reintentos_lambda
    Catch      = local.captura_errores
  }

  estados_gestora = {
    Descarga = merge(local.tarea_lambda, {
      Comment    = "Etapa 1: captura de los KID y manifiesto"
      Parameters = { FunctionName = aws_lambda_function.etapas["descarga"].arn, "Payload.$" = "$" }
      Next       = "Markdown"
    })
    Markdown = merge(local.tarea_lambda, {
      Comment    = "Etapa 2: PDF a Markdown"
      Parameters = { FunctionName = aws_lambda_function.etapas["markdown"].arn, "Payload.$" = "$" }
      Next       = "Extraccion"
    })
    Extraccion = merge(local.tarea_lambda, {
      Comment    = "Etapa 3: extraccion con Bedrock"
      Parameters = { FunctionName = aws_lambda_function.etapas["extraccion"].arn, "Payload.$" = "$" }
      Next       = "Carga"
    })
    Carga = merge(local.tarea_lambda, {
      Comment    = "Etapa 4: carga en PostgreSQL"
      Parameters = { FunctionName = aws_lambda_function.etapas["carga"].arn, "Payload.$" = "$" }
      End        = true
    })
    GestoraFallida = {
      Type       = "Pass"
      Parameters = { "gestora.$" = "$.gestora", "error.$" = "$.error" }
      End        = true
    }
  }

  definicion_pipeline = {
    Comment        = "Pipeline de KID: captura, Markdown, extraccion y carga, para cada gestora"
    StartAt        = "PorGestora"
    TimeoutSeconds = 3600
    States = {
      PorGestora = {
        Type           = "Map"
        ItemsPath      = "$.gestoras"
        ItemSelector   = { "gestora.$" = "$$.Map.Item.Value" }
        MaxConcurrency = 2
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "Descarga"
          States          = local.estados_gestora
        }
        Next = "Resultados"
      }
      Resultados = {
        Type       = "Pass"
        Comment    = "Resumen de cada gestora y lista de las que han fallado"
        Parameters = { "gestoras.$" = "$", "fallidas.$" = "$[?(@.error)]" }
        Next       = "Comprobar"
      }
      Comprobar = {
        Type    = "Choice"
        Choices = [{ Variable = "$.fallidas[0]", IsPresent = true, Next = "ConErrores" }]
        Default = "Completado"
      }
      ConErrores = {
        Type  = "Fail"
        Error = "PipelineConErrores"
        Cause = "Al menos una gestora ha fallado: revisa la salida del estado PorGestora"
      }
      Completado = { Type = "Succeed" }
    }
  }
}

data "aws_iam_policy_document" "confianza_step_functions" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "step_functions" {
  statement {
    sid     = "InvocarEtapas"
    actions = ["lambda:InvokeFunction"]
    resources = flatten([
      for funcion in aws_lambda_function.etapas : [funcion.arn, "${funcion.arn}:*"]
    ])
  }
}

resource "aws_iam_role" "step_functions" {
  name               = "${local.prefijo}-pipeline-sfn"
  description        = "Rol de la maquina de estados del pipeline: invoca las funciones de las etapas"
  assume_role_policy = data.aws_iam_policy_document.confianza_step_functions.json
}

resource "aws_iam_role_policy" "step_functions" {
  name   = "invocar-etapas"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.step_functions.json
}

resource "aws_sfn_state_machine" "pipeline" {
  name       = "${local.prefijo}-pipeline"
  role_arn   = aws_iam_role.step_functions.arn
  definition = jsonencode(local.definicion_pipeline)

  depends_on = [aws_iam_role_policy.step_functions]
}

# Ejecución mensual programada
data "aws_iam_policy_document" "confianza_scheduler" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "IniciarPipeline"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.pipeline.arn]
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.prefijo}-pipeline-scheduler"
  description        = "Rol del horario mensual: inicia una ejecucion del pipeline"
  assume_role_policy = data.aws_iam_policy_document.confianza_scheduler.json
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "iniciar-pipeline"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "pipeline_mensual" {
  name        = "${local.prefijo}-pipeline-mensual"
  description = "Ejecuta el pipeline de KID el dia 15 de cada mes a las 9:00 (hora de Madrid)"

  schedule_expression          = var.horario_pipeline
  schedule_expression_timezone = "Europe/Madrid"
  state                        = var.horario_activo ? "ENABLED" : "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ gestoras = var.gestoras })
  }
}
