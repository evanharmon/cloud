"""
TODOs - move in file and save as comments to reflect work / best practices:
# pre-generate `AmazonEKSAutoClusterRole` once per AWS account
# pre-generate `AmazonEKSAutoNodeRole` once per AWS account

SGS:
# use `eks-cluster-sg-` prefix for custom security groups
# this avoids adding perms to cluster role to manage additional SG group naming conventions

NodeClass/Pools:
# disable default nodeClass / nodePool and create my own with cheaper instances
# create new general-purpose-arm to use ARM64 with tg4's?
# create new general-purpose-amd64 to use non-arm64 t3's?

"""
