output "funciones_etapas" {
  description = "Nombre de la función Lambda de cada etapa"
  value       = { for etapa, funcion in aws_lambda_function.etapas : etapa => funcion.function_name }
}

output "imagenes_desplegadas" {
  description = "Digest de la imagen desplegada en cada etapa"
  value       = { for etapa, imagen in data.aws_ecr_image.etapas : etapa => imagen.id }
}

output "maquina_estados_pipeline" {
  description = "ARN de la máquina de estados del pipeline"
  value       = aws_sfn_state_machine.pipeline.arn
}

output "horario_pipeline" {
  description = "Horario de la ejecución programada"
  value       = "${aws_scheduler_schedule.pipeline_mensual.schedule_expression} (${aws_scheduler_schedule.pipeline_mensual.schedule_expression_timezone}), ${aws_scheduler_schedule.pipeline_mensual.state}"
}

output "url_api" {
  description = "URL pública de la API (documentación en /docs)"
  value       = aws_lambda_function_url.api.function_url
}
