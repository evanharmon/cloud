################ IPV4 EKS MANAGED NODE GROUPS ################ 
######## TODOs
# cloudwatch log group should be managed separately - so the logs don't auto delete or at least so that's an option
# TEARING THIS down leaves karpenter instances around!
# one time the destroy DID hang bc the sg was still attached to the karpenter instance
######## TODOs

# NOTE: this takes about 10 minutes for the EKS cluster, then 5+ minutes for managed node group
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_name    = local.name
  cluster_version = local.cluster_version

  # Temporary tweaks to save money / less resources to stand up
  create_cloudwatch_log_group = false
  # cloudwatch_log_group_retention_in_days = 1

  # Ensures AWS manages addons lifecycle, updates, security patches
  # this is the default
  bootstrap_self_managed_addons = false
  cluster_addons = {
    # TODO: still needs work on first up - AdmissionRequestDenied error
    coredns = {
      configuration_values = jsonencode({
        tolerations = [
          # Allow CoreDNS to run on the same nodes as the Karpenter controller
          # for use during cluster creation when Karpenter nodes do not yet exist
          {
            key    = "karpenter.sh/controller"
            value  = "true"
            effect = "NoSchedule"
          }
        ]
        # TODO: Note(evan): Setting very low to save on costs and test coredns failures
        # replicaCount = 1
        # resources = {
        #   requests = {
        #     cpu = "50m"
        #     memory = "50Mi"
        #   }
        # }
      })
    }
    kube-proxy = {
      # TODO: try this out
      # configuration_values = jsonencode({
      #   resources = {
      #     requests = {
      #       cpu    = "20m"
      #       memory = "50Mi"
      #     }
      #   }
      # })
    }
    vpc-cni = {
      service_account_role_arn = module.vpc_cni_irsa.iam_role_arn
      # https://aws-ia.github.io/terraform-aws-eks-blueprints/snippets/ipv4-prefix-delegation/
      before_compute = true # must be updated BEFORE any ec2 instances are created
      most_recent    = true # ensure access to latest settings provided
      configuration_values = jsonencode({
        enableNetworkPolicy = "true"
        env = {
          ENABLE_PREFIX_DELEGATION = "true" # Recommended for IPv4 efficiency
          WARM_PREFIX_TARGET       = "1"
        }
      })
    }
  }

  ################ AUTH ################ 
  enable_irsa = true

  # Optional: Adds the current caller identity as an administrator via cluster access entry
  enable_cluster_creator_admin_permissions = true
  # don't bother with aws auth configmap just use access entries
  authentication_mode            = "API"
  cluster_endpoint_public_access = true
  # DON'T SET THE BELOW - It breaks the AWS console and more!!
  # cluster_endpoint_public_access_cidrs = ["71.81.217.110/32"]
  ################ AUTH ################ 

  eks_managed_node_group_defaults = {
    instance_types = ["t4g.medium"]
  }

  # SECURITY: IMDSv2 is on by default and hop level set to 1
  # SECURITY: hop limit set to 1 to stop pods from inheriting role assigned to worker node
  # read this doc though - some things may break? not sure https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html#_identities_and_credentials_for_eks_pods
  # aws ec2 modify-instance-metadata-options --instance-id <value> --http-tokens required --http-put-response-hop-limit 1

  # Just for karpenter
  eks_managed_node_groups = {
    karpenter = {
      ami_type = "BOTTLEROCKET_ARM_64"
      instance_types = ["t4g.medium"]

      # Low values to save on cost and ignore HA
      min_size = 1
      max_size = 2
      # This value is ignored after the initial creation
      desired_size = 1

      # Note: I think this could be turned on org wide and it is automatically added?
      iam_role_additional_policies = {
        AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      labels = {
        # Ensure karpenter only runs on nodes it does not manage
        "karpenter.sh/controller" = "true"
      }

      taints = {
        # Pods that do not tolerate taint should run on nodes created by karpenter
        karpenter = {
          key    = "karpenter.sh/controller"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      }

      # This is not required - demonstrates how to pass additional configuration
      # Ref https://bottlerocket.dev/en/os/1.19.x/api/settings/
      bootstrap_extra_args = <<-EOT
        # The admin host container provides SSH access and runs with "superpowers".
        # It is disabled by default, but can be disabled explicitly.
        [settings.host-containers.admin]
        # SECURITY ALERT: I ENABLED SHELTIE (: LOL
        enabled = true

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

  # ONLY ONE SG should get created for ALB's and be tagged with `kubernetes.io/cluster/$CLUSTER_NAME`
  # However I end up with two and aws lb controller is working just fine
  # creates NLBS / ALBS, ingresses, etc.
  create_cluster_security_group = true

  node_security_group_tags = {
    # NOTE - if creating multiple security groups with this module, only tag the
    # security group that Karpenter should utilize with the following tag
    # (i.e. - at most, only one security group should have this tag in your account)
    "karpenter.sh/discovery" = local.name
  }
}

# TODO: failing on first stand up on one go
# NOTE: not using eks blueprints addons yet - seems more complicated with IRSA setups
# might be worth using to test / get AWS LB running successfully though!
module "eks_blueprints_addons" {
  source  = "aws-ia/eks-blueprints-addons/aws"
  version = "~> 1.21"

  cluster_name      = module.eks.cluster_name
  cluster_endpoint  = module.eks.cluster_endpoint
  cluster_version   = module.eks.cluster_version
  oidc_provider_arn = module.eks.oidc_provider_arn

  # Creates IRSA setup by default
  enable_aws_load_balancer_controller = true
  aws_load_balancer_controller = {
    chart_version = "1.12.0" # min version required to use SG for NLB feature
    set = [
      # only deploy ONE AWS LB on a node to save $$
      {
        name = "replicaCount"
        value = "1"
      },
      # Turning off these defaults to save $$ as this is a playground
      {
        name = "enableShield"
        value = "false"
      },
      {
        name = "enableWaf"
        value = "false"
      },
      {
        name = "enableWafv2"
        value = "false"
      },
      # just setting requests for now - can put in limits later
      {
        name  = "resources.requests.cpu"
        value = "100m"
      },
      {
        name  = "resources.requests.memory"
        value = "128Mi"
      },
      {
        name  = "region"
        value = "${local.region}"
      },
      # Passing vpc_id and region as IMDSv2 token hops is set to 1 right now
      {
        name  = "vpcId"
        value = "${module.vpc.vpc_id}"
      },
      {
        name  = "defaultTargetType"
        value = "ip"
      }
      # TODO: should only run on karpenter managed nodes explicitly so its clear - affinity?
      # TODO: enable cert manager and use it as well?
    ]
  }
}

# TODO: use this - apparently takes a long time to stand up though?
# module "ebs_csi_driver_irsa" {
#   source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
#   version = "~> 5.20"

#   role_name_prefix = "${module.eks.cluster_name}-ebs-csi-"

#   attach_ebs_csi_policy = true

#   oidc_providers = {
#     main = {
#       provider_arn               = module.eks.oidc_provider_arn
#       namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
#     }
#   }
# }

module "vpc_cni_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.20"

  role_name_prefix = "${module.eks.cluster_name}-vpc-cni-"

  attach_vpc_cni_policy = true
  vpc_cni_enable_ipv4   = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-node"]
    }
  }
}
