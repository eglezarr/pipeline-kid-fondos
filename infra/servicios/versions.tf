terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Estado remoto en el bucket del arranque; bucket y región se pasan en terraform init
  backend "s3" {
    key          = "servicios/terraform.tfstate"
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
