# IPV4
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = local.name
  cidr = local.vpc_cidr

  # Best practice
  # /19 to make sure we have LOTS of IPs
  # cidr ranges to support more than 3 AZs / subnets
  azs = local.azs
  # Example:
  # private_subnets = ["10.0.96.0/19", "10.0.128.0/19", "10.0.160.0/19"]
  # public_subnets = ["10.0.0.0/19", "10.0.32.0/19", "10.0.64.0/19"]
  private_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, local.num_azs, k + local.num_azs)]
  public_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, local.num_azs, k)]

  manage_default_network_acl    = true
  default_network_acl_tags      = { Name = "${local.name}-default" }
  manage_default_route_table    = true
  default_route_table_tags      = { Name = "${local.name}-default" }
  manage_default_security_group = true
  default_security_group_tags   = { Name = "${local.name}-default" }

  enable_nat_gateway = true
  single_nat_gateway = true
  # required and defaults to true in this module
  enable_dns_hostnames = true
  enable_dns_support   = true

  # tag for kubernetes ELB integration
  private_subnet_tags = {
    "kubernetes.io/cluster/${local.name}" = "shared"
    "kubernetes.io/role/internal-elb" = 1
    "karpenter.sh/discovery" = local.name
  }

  public_subnet_tags = {
    "kubernetes.io/cluster/${local.name}" = "shared"
    "kubernetes.io/role/elb" = 1
  }
}
