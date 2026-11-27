output "rol_despliegue_arn" {
  description = "ARN del rol que asume GitHub Actions (se guarda como secreto AWS_ROLE_ARN en GitHub)"
  value       = aws_iam_role.despliegue_github.arn
}
