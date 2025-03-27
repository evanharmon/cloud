################ IPV4 EKS MANAGED NODE GROUPS ################ 
######## TODOs
# Should I be using pod identity or IRSA as a best practice?
# cloudwatch log group should be managed separately - so the logs don't auto delete or at least so that's an option
######## TODOs

# NOTE: this takes about 10 minutes for the EKS cluster, then 5+ minutes for managed node group
module "eks" {
  source = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  vpc_id = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_name = local.name
  cluster_version = local.cluster_version

  # Ensures AWS manages addons lifecycle, updates, security patches
  # this is the default
  bootstrap_self_managed_addons = false
  cluster_addons = {
    coredns = {}
    eks-pod-identity-agent = {}
    kube-proxy = {}
    vpc-cni = {
      # https://aws-ia.github.io/terraform-aws-eks-blueprints/snippets/ipv4-prefix-delegation/
      before_compute = true # must be updated BEFORE any ec2 instances are created
      most_recent = true # ensure access to latest settings provided
      configuration_values = jsonencode({
        enableNetworkPolicy = "true"
        env = {
          ENABLE_PREFIX_DELEGATION = "true"  # Recommended for IPv4 efficiency
          WARM_PREFIX_TARGET = "1"
        }
      })
    }
  }

  ################ AUTH ################ 
  # Defaults to true: OIDC is necessary for things like Teleport Cloud, etc.
  enable_irsa = true

  # Optional: Adds the current caller identity as an administrator via cluster access entry
  enable_cluster_creator_admin_permissions = true
  # don't bother with aws auth configmap just use access entries
  authentication_mode = "API"
  cluster_endpoint_public_access = true
  # DON'T SET THE BELOW - It breaks the AWS console and more!!
  # cluster_endpoint_public_access_cidrs = ["71.81.217.110/32"]
  ################ AUTH ################ 

  eks_managed_node_group_defaults = {
    instance_types = ["m6i.large"]
  }

  eks_managed_node_groups = {
    example = {
      ami_type       = "BOTTLEROCKET_x86_64"
      instance_types = ["m6i.large"]

      min_size = 1
      max_size = 2
      # This value is ignored after the initial creation
      desired_size = 1

      # This is not required - demonstrates how to pass additional configuration
      # Ref https://bottlerocket.dev/en/os/1.19.x/api/settings/
      bootstrap_extra_args = <<-EOT
        # The admin host container provides SSH access and runs with "superpowers".
        # It is disabled by default, but can be disabled explicitly.
        [settings.host-containers.admin]
        enabled = false

        # The control host container provides out-of-band access via SSM.
        # It is enabled by default, and can be disabled if you do not expect to use SSM.
        # This could leave you with no way to access the API and change settings on an existing node!
        [settings.host-containers.control]
        enabled = true

        # extra args added
        [settings.kernel]
        lockdown = "integrity"
      EOT
    }
  }

  cloudwatch_log_group_retention_in_days = 1
}
