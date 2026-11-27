# Base de datos: Aurora PostgreSQL Serverless v2 con RDS Data API.
#
# - Serverless v2 con mínimo de 0 ACU: tras unos minutos sin conexiones se pausa
#   y en reposo solo se paga el almacenamiento. Se reanuda sola con la primera
#   petición (tarda unos segundos).
# - Data API: las Lambdas consultan la base de datos por HTTPS con su rol de IAM,
#   sin conectarse a la VPC ni gestionar conexiones.
# - Contraseña gestionada por AWS en Secrets Manager: no aparece en el código
#   ni en el estado de Terraform.

# Versión de Aurora PostgreSQL que AWS ofrece por defecto en la región
data "aws_rds_engine_version" "postgresql" {
  engine       = "aurora-postgresql"
  default_only = true
}

resource "aws_rds_cluster" "fondos" {
  cluster_identifier = "${local.prefijo}-bd"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = data.aws_rds_engine_version.postgresql.version_actual

  database_name               = "fondos"
  master_username             = "pipeline_admin"
  manage_master_user_password = true
  enable_http_endpoint        = true # RDS Data API

  storage_encrypted       = true
  backup_retention_period = 1
  skip_final_snapshot     = true
  deletion_protection     = false
  apply_immediately       = true

  serverlessv2_scaling_configuration {
    min_capacity             = 0
    max_capacity             = var.aurora_acu_max
    seconds_until_auto_pause = var.aurora_segundos_hasta_pausa
  }
}

resource "aws_rds_cluster_instance" "fondos" {
  identifier          = "${local.prefijo}-bd-1"
  cluster_identifier  = aws_rds_cluster.fondos.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.fondos.engine
  engine_version      = aws_rds_cluster.fondos.engine_version
  publicly_accessible = false
}
