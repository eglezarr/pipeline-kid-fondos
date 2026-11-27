data "aws_caller_identity" "actual" {}

locals {
  prefijo = "pipeline-kid"

  # Sufijo anónimo y estable para los nombres que deben ser únicos en todo AWS
  # (buckets): hash del ID de la cuenta, sin exponer el ID en el nombre.
  sufijo = substr(sha256(data.aws_caller_identity.actual.account_id), 0, 8)
}
