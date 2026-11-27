variable "region" {
  description = "Región de AWS del proyecto"
  type        = string
  default     = "eu-west-3"
}

variable "repositorio" {
  description = "Repositorio de GitHub (propietario/nombre) autorizado a desplegar"
  type        = string
  default     = "eglezarr/pipeline-kid-fondos"
}

variable "id_propietario" {
  description = "ID numérico de la cuenta de GitHub propietaria del repositorio (público)"
  type        = string
  default     = "237296710"
}

variable "id_repositorio" {
  description = "ID numérico del repositorio de GitHub (público)"
  type        = string
  default     = "1474536826"
}

variable "rama" {
  description = "Rama del repositorio autorizada a desplegar"
  type        = string
  default     = "main"
}

variable "crear_proveedor_oidc" {
  description = "Crear el proveedor OIDC de GitHub (false si ya existe en la cuenta)"
  type        = bool
  default     = true
}
