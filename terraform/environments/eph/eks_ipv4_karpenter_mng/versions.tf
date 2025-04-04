terraform { 

  cloud { 
    organization = "eph-core" 

    workspaces { 
      name = "cloud-aws-eph-eks-ipv4-karpenter-mng" 
    } 
  } 

  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "~> 5.0"
    }
    helm = {
      source = "hashicorp/helm"
      version = ">= 2.9"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.0.2"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.10"
    }
  }

  required_version = ">= 1.0"
}
