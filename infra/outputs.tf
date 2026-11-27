output "bucket_datos" {
  description = "Bucket de datos del pipeline"
  value       = aws_s3_bucket.datos.bucket
}

output "repositorios_ecr" {
  description = "URL de cada repositorio de imágenes"
  value       = { for nombre, repo in aws_ecr_repository.imagenes : nombre => repo.repository_url }
}

output "aurora_cluster_arn" {
  description = "ARN del clúster de Aurora (para la Data API)"
  value       = aws_rds_cluster.fondos.arn
}

output "aurora_secreto_arn" {
  description = "ARN del secreto con las credenciales de Aurora (para la Data API)"
  value       = aws_rds_cluster.fondos.master_user_secret[0].secret_arn
}

output "aurora_base_datos" {
  description = "Nombre de la base de datos"
  value       = aws_rds_cluster.fondos.database_name
}
