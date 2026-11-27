# Bucket de datos del pipeline:
#   download/<gestora>/<AAAAMMDD>/   PDF descargados y manifiesto de la ejecución
#   markdown/<gestora>/<AAAAMMDD>/   PDF convertidos a Markdown
#   extraction/<gestora>/<AAAAMMDD>/ datos extraídos (JSON)
# Es privado: los datos solo se exponen a través de la API y la aplicación.
resource "aws_s3_bucket" "datos" {
  bucket        = "${local.prefijo}-datos-${local.sufijo}"
  force_destroy = true # permite borrarlo con terraform destroy aunque tenga objetos
}

resource "aws_s3_bucket_public_access_block" "datos" {
  bucket = aws_s3_bucket.datos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "datos" {
  bucket = aws_s3_bucket.datos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
