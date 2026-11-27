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

variable "aurora_acu_max" {
  description = "Capacidad máxima de Aurora Serverless v2 en ACU (el plan gratuito permite hasta 4)"
  type        = number
  default     = 2
}

variable "aurora_segundos_hasta_pausa" {
  description = "Segundos sin conexiones tras los que Aurora se pausa (0 ACU)"
  type        = number
  default     = 300
}
