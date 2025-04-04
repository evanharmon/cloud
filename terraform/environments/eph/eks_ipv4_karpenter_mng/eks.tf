################ IPV4 EKS MANAGED NODE GROUPS ################ 
######## TODOs
# cloudwatch log group should be managed separately - so the logs don't auto delete or at least so that's an option
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
    # TODO: use ARM instead / tg4.medium instead
    # instance_types = ["t3.medium"]
    instance_types = ["t4g.medium"]
  }

  # Just for karpenter
  eks_managed_node_groups = {
    karpenter = {
      # TODO: use ARM instead / tg4 instead just for karpenter
      # ami_type = "BOTTLEROCKET_x86_64"
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

  # NOTE(evan): on KodeKloud LB demo - only SG eks-cluster-sg-demo-eks-855462307 has the
  # `kubernetes.io/cluster/demo-eks` tag - no others. It's not a karpenter setup though
  # oddly enough - the above SG is NOT attached to the NODE's with the ingress / service.
  # that's just a generic separate `NodeSecurityGroupIngress` SG with no tags except name

  # Testing out getting the SG's right
  # ONLY karpenter node SG should have `karpenter.sh/discovery` tag
  # ONLY ONE SG should get created for ALB's and be tagged with `kubernetes.io/cluster/$CLUSTER_NAME`
  # cluster SG group should have neither of the above tags for ALB / Karpenter?
  create_cluster_security_group = true

  # TODO: consider this setup to ensure correct SG so will work with aws-lb-controller?
  # https://karpenter.sh/docs/concepts/nodeclasses/#:~:text=*%20)%20is%20supported.-,Note,you%2C%20run%20the%20following%20commands.&text=If%20multiple%20securityGroups%20are%20printed,:%20$CLUSTER_NAME%20tag%20selector%20instead.
  # aws-lb-controller only supports a SINGLE SG having the `kubernetes.io/cluster/$CLUSTER_NAME` tag
  # and attached to a karpenter node / ENI
  # create_cluster_security_group            = false
  # create_node_security_group               = false
  # tags = {
  #   "karpenter.sh/discovery" = local.name
  # }
  # the below would get removed
  node_security_group_tags = {
    # NOTE - if creating multiple security groups with this module, only tag the
    # security group that Karpenter should utilize with the following tag
    # (i.e. - at most, only one security group should have this tag in your account)
    "karpenter.sh/discovery" = local.name
  }
}

# NOTE: not using eks blueprints addons yet - seems more complicated with IRSA setups
# might be worth using to test / get AWS LB running successfully though!
# module "eks_blueprints_addons" {
#   source  = "aws-ia/eks-blueprints-addons/aws"
#   version = "~> 1.21"

#   cluster_name      = module.eks.cluster_name
#   cluster_endpoint  = module.eks.cluster_endpoint
#   cluster_version   = module.eks.cluster_version
#   oidc_provider_arn = module.eks.oidc_provider_arn

#   enable_aws_load_balancer_controller = true
#   aws_load_balancer_controller = {
#     chart_version = "1.12.0" # min version required to use SG for NLB feature
#   }
# }

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
