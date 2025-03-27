terraform { 

  cloud { 
    organization = "eph-core" 

    workspaces { 
      name = "cloud-aws-eph-ipv4-eks-managed" 
    } 
  } 

  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  required_version = ">= 1.0"
}