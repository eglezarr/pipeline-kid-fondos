output "funciones_etapas" {
  description = "Nombre de la función Lambda de cada etapa"
  value       = { for etapa, funcion in aws_lambda_function.etapas : etapa => funcion.function_name }
}

output "imagenes_desplegadas" {
  description = "Digest de la imagen desplegada en cada etapa"
  value       = { for etapa, imagen in data.aws_ecr_image.etapas : etapa => imagen.id }
}
