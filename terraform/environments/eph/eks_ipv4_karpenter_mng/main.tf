provider "aws" {
  region = var.region
  # TODO: replace with an assumed_role
  profile = "eph-music-dev"

  default_tags {
    tags = var.tags
  }
}

# ECR auth must be in us-east-1
provider "aws" {
  alias = "ecr"
  region = "us-east-1"
  # TODO: replace with an assumed_role
  profile = "eph-music-dev"
}

provider "helm" {
  kubernetes {
    host = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      # AWS cli must be installed
      args = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.this.token
}

provider "kubectl" {
  apply_retry_count      = 10
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
  load_config_file       = false
  token                  = data.aws_eks_cluster_auth.this.token
}

################################################################################
# COMMON DATA / LOCALS
################################################################################

data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

data "aws_ecrpublic_authorization_token" "token" {
  provider = aws.ecr
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
  num_azs = var.num_azs

  cluster_version = var.cluster_version
  vpc_cidr = var.vpc_cidr
  # 2 AZ's to be cheap
  azs = slice(data.aws_availability_zones.available.names, 0, var.num_azs)
}
