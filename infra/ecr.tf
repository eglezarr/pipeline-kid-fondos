# Repositorios de imágenes Docker: uno por cada etapa del pipeline (Lambda),
# otro para la API (Lambda) y otro para la aplicación web (ECS).
locals {
  repositorios_ecr = ["descarga", "markdown", "extraccion", "carga", "api", "app"]
}

resource "aws_ecr_repository" "imagenes" {
  for_each = toset(local.repositorios_ecr)

  name                 = "${local.prefijo}-${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # permite borrarlo con terraform destroy aunque tenga imágenes
}

# Cada despliegue sube una imagen nueva: se conservan solo las 5 más recientes
resource "aws_ecr_lifecycle_policy" "imagenes" {
  for_each = aws_ecr_repository.imagenes

  repository = each.value.name
  policy     = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar solo las 5 imagenes mas recientes"
      selection    = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
