variable "region" {
  description = "Región de AWS del proyecto"
  type        = string
  default     = "eu-west-3"
}

variable "proyecto" {
  description = "Nombre del proyecto (etiqueta de todos los recursos)"
  type        = string
  default     = "pipeline-kid-fondos"
}

variable "dias_retencion_logs" {
  description = "Días que se conservan los logs de CloudWatch de las funciones"
  type        = number
  default     = 14
}
