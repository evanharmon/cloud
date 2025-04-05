provider "aws" {
  region = var.region
  # TODO: replace with an assumed_role
  profile = "eph-music-dev"

  default_tags {
    tags = var.tags
  }
}

data "aws_availability_zones" "available" {
  # Exclude local zones
  filter {
    name = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  name = var.project_name
  region = var.region

  cluster_version = var.cluster_version
  vpc_cidr = var.vpc_cidr
  # 3 AZ's and one DJ, we be gettin' down with no delay...
  azs = slice(data.aws_availability_zones.available.names, 0, 3)
}
