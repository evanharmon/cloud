locals {
  namespace = "karpenter"
}

################################################################################
# Controller & Node IAM roles, SQS Queue, Eventbridge Rules
################################################################################
module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 20.24"

  cluster_name          = module.eks.cluster_name
  enable_v1_permissions = true

  # on by default but explicitly stating it here
  enable_spot_termination = true
  # default is false, let EC2NodeClass manage creation of instance profiles
  create_instance_profile = false

  # TODO: i'd rather use IRSA if possible
  # create_pod_identity_association = true
  enable_pod_identity = false
  # this is for pod identity - not needed
  # namespace             = local.namespace

  irsa_oidc_provider_arn          = module.eks.oidc_provider_arn
  irsa_namespace_service_accounts = ["karpenter:karpenter"]
  enable_irsa                     = true

  # TODO: node iam role for EKS still has AmazonEKS_CNI_Policy which isn't needed anymore - it's on IRSA to vpc cni
  # make sure aws-node IAM role tied to SA has this policy...
  # node_iam_role_attach_cni_policy = false
  node_iam_role_use_name_prefix = false
  # Name needs to match role name passed to the EC2NodeClass 
  node_iam_role_description = "Karpenter node iam role"

  # TODO - is this needed so karpenter instances have SSM access? again maybe could be turned on at org level instead
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}

################################################################################
# Helm charts
################################################################################
resource "helm_release" "karpenter" {
  name                = "karpenter"
  namespace           = local.namespace
  create_namespace    = true
  repository          = "oci://public.ecr.aws/karpenter"
  repository_username = data.aws_ecrpublic_authorization_token.token.user_name
  repository_password = data.aws_ecrpublic_authorization_token.token.password
  chart               = "karpenter"
  version             = "1.3.3"
  # wait                = false

  values = [
    <<-EOT
    replicas: 1
    nodeSelector:
      karpenter.sh/controller: 'true'
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
      # featureGates: not using any yet
    serviceAccount:
      annotations:
        eks.amazonaws.com/role-arn: ${module.karpenter.iam_role_arn} 
    tolerations:
      - key: CriticalAddonsOnly
        operator: Exists
      - key: karpenter.sh/controller
        operator: Exists
        effect: NoSchedule
    # no idea if this should be true
    webhook:
      enabled: false
    EOT
  ]

  lifecycle {
    ignore_changes = [
      repository_password
    ]
  }
}

resource "kubectl_manifest" "karpenter_default_ec2_node_class" {
  yaml_body = <<YAML
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: default
spec:
  amiSelectorTerms:
    # change to a non-latest tag to test upgrades
    - alias: bottlerocket@latest
  role: "${module.karpenter.node_iam_role_name}"
  subnetSelectorTerms:
    - tags:
        karpenter.sh/discovery: ${module.eks.cluster_name}
  securityGroupSelectorTerms:
    - tags:
        karpenter.sh/discovery: ${module.eks.cluster_name}
  tags:
    karpenter.sh/discovery: ${module.eks.cluster_name}
YAML
  depends_on = [ module.eks.cluster, module.karpenter ]
}

# TODO: stop using this as it's expensive - switch to arm
# resource "kubectl_manifest" "karpenter_default_node_pool" {
#   yaml_body = <<YAML
# apiVersion: karpenter.sh/v1
# kind: NodePool
# metadata:
#   name: default
# spec:
#   template:
#     spec:
#       nodeClassRef:
#         group: karpenter.k8s.aws
#         kind: EC2NodeClass
#         name: default
#       requirements:
#         - key: "karpenter.k8s.aws/instance-category"
#           operator: In
#           values: ["c", "m", "r"]
#         - key: "karpenter.k8s.aws/instance-cpu"
#           operator: In
#           values: ["4", "8", "16", "32"]
#         - key: "karpenter.k8s.aws/instance-hypervisor"
#           operator: In
#           values: ["nitro"]
#         - key: "karpenter.k8s.aws/instance-generation"
#           operator: Gt
#           values: ["2"]
#   limits:
#     cpu: 16
#   disruption:
#     # or use this if you can handle consolidation on the fly: WhenEmptyOrUnderutilized
#     consolidationPolicy: WhenEmpty
#     # adjust on the fly in k9s for testing
#     consolidateAfter: 3600s
# YAML
#   depends_on = [ module.eks.cluster, module.karpenter, kubectl_manifest.karpenter_default_ec2_node_class ]
# }

## Try the below instead
# TODO: try out as ARM instead
resource "kubectl_manifest" "karpenter_default_node_pool" {
  yaml_body = <<YAML
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: default
      kubelet:
        containerRuntime: containerd
        systemReserved:
          cpu: 100m
          memory: 100Mi
      requirements:
        - key: "karpenter.k8s.aws/instance-family"
          operator: In
          values: ["t4g"]
        - key: "karpenter.k8s.aws/instance-cpu"
          operator: In
          values: ["4"]
        - key: "karpenter.k8s.aws/instance-hypervisor"
          operator: In
          values: ["nitro"]
        - key: "karpenter.k8s.aws/instance-generation"
          operator: Gt
          values: ["2"]
        - key: kubernetes.io/arch
          operator: In
          values: ["arm64"]
  limits:
    # Tweak for costs - effectively just limiting to one node for now
    cpu: 4
  disruption:
    # or use this if you can handle consolidation on the fly: WhenEmptyOrUnderutilized
    consolidationPolicy: WhenEmpty
    consolidateAfter: 3600s
    # not using expireAfter yet for forced rolls

YAML
  depends_on = [ module.eks.cluster, module.karpenter, kubectl_manifest.karpenter_default_ec2_node_class ]
}
