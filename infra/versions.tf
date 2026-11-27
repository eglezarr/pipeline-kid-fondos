terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Estado remoto en el bucket creado en el arranque (infra/bootstrap).
  # Bucket y región se pasan en terraform init (-backend-config) desde el workflow.
  backend "s3" {
    key          = "principal/terraform.tfstate"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Proyecto = var.proyecto
      Gestion  = "terraform"
    }
  }
}
