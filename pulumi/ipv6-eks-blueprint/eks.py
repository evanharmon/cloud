"""
EKS Cluster Setup
- largely based off https://github.com/terraform-aws-modules/terraform-aws-eks/blob/master/main.tf
"""

import json

import pulumi
import pulumi_aws as aws


class Cluster(pulumi.ComponentResource):
    def __init__(
        self,
        name: str,
        admin_role_name: str,
        cluster_version: str | None,
        private_subnet_ids: list[str],
        vpc_id: str,
        opts: pulumi.ResourceOptions = None,
    ):
        super().__init__(t="eph:eks:Cluster", name=name, props=None, opts=opts)

        # TODO: I wonder if there is a way to do this on the provider
        self.current = aws.get_caller_identity()
        sso_admin_role_arn = f"arn:aws:iam::{self.current.account_id}:role/aws-reserved/sso.amazonaws.com/{admin_role_name}"
        sso_admin_assume_role_arn = (
            f"arn:aws:sts::{self.current.account_id}:assumed-role/{admin_role_name}"
        )

        """
        SECURITY GROUPS
        - putting them in here for now similar to terraform-aws-eks module
        # module.eks.aws_security_group.node[0]:
        - ALWAYS use aws.vpc.SecurityGroupIngressRule or SecurityGroupEgressRule
        - NEVER place rules directly on aws.ec2.SecurityGroupRule
        - NEVER use aws.ec2.SecurityGroupRule
        - `delete_before_replace` doesn't work on SG rules
        """

        # SECURITY GROUPS WITH ADDT'L BASE RULES

        self.node_sg = aws.ec2.SecurityGroup(
            resource_name=f"{name}-node-sg",
            name_prefix=f"{name}-",
            description="Node security group",
            vpc_id=vpc_id,
            tags={
                "Name": f"{name}-node-sg",
                f"kubernetes.io/cluster/{name}": "owned",
            },
            opts=pulumi.ResourceOptions(parent=self),
        )

        node_groups_all_ipv4_egress_sgr = aws.vpc.SecurityGroupEgressRule(
            resource_name=f"{name}-node-sgr-all-ipv4-egress",
            description="Allow all IPv4 egress allowed",
            cidr_ipv4="0.0.0.0/0",
            ip_protocol="-1",
            security_group_id=self.node_sg.id,
            tags={"Name": f"{name}-node-sgr-all-ipv4-egress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        node_groups_all_ipv6_egress_sgr = aws.vpc.SecurityGroupEgressRule(
            resource_name=f"{name}-node-sgr-all-ipv6-egress",
            description="Allow all IPv6 egress allowed",
            cidr_ipv6="::/0",
            ip_protocol="-1",
            security_group_id=self.node_sg.id,
            tags={"Name": f"{name}-node-sgr-all-ipv4-egress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # NOTE: not launching instances in public subnets - so no EKS cluster tag
        self.cluster_sg = aws.ec2.SecurityGroup(
            resource_name=f"{name}-cluster-sg",
            name_prefix=f"{name}-",
            description="Cluster security group",
            vpc_id=vpc_id,
            tags={"Name": f"{name}-cluster-sg"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # TODO: terraform-aws-eks does not have this outbound rule - try removing
        cluster_all_ipv4_egress_sgr = aws.vpc.SecurityGroupEgressRule(
            resource_name=f"{name}-cluster-sgr-all-ipv4-egress",
            description="Allow all IPv4 egress allowed",
            cidr_ipv4="0.0.0.0/0",
            ip_protocol="-1",
            security_group_id=self.cluster_sg.id,
            tags={"Name": f"{name}-cluster-sgr-all-egress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # TODO: terraform-aws-eks does not have this outbound rule - try removing
        cluster_all_ipv6_egress_sgr = aws.vpc.SecurityGroupEgressRule(
            resource_name=f"{name}-cluster-sgr-all-ipv6-egress",
            description="Allow all IPv6 egress allowed",
            cidr_ipv6="::/0",
            ip_protocol="-1",
            security_group_id=self.cluster_sg.id,
            tags={"Name": f"{name}-cluster-sgr-all-ipv6-egress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        SGs: [Cluster, Node]
        Cluster SG Rules list from TF: sg-03b2fdd6234990546
        looks like TF has inline SGs and then adds them as
        manaed dupes as well - so i'll just need one of them
        - ✅ ingress https for node sg (inline + separate)
        - TF doesn't list egress rules but i've added them as well for ipv4 / 6

        Node SG Rules list from TF: sg-07a9e3f4b9b1896f0
        looks like TF has inline SGs and then adds them as
        manaed dupes as well - so i'll just need one of them
        - ✅ egress all IPv4 (inline + separate)
        - ✅ egress all IPv6 (inline + separate)
        - ✅ ingress 4443 for cluster sg (inline + separate)
        - ✅ ingress 6443 for cluster SG (inline + separate)
        - ✅ ingress 8443 for cluster SG (inline + separate)
        - ✅ ingress 9443 for cluster SG (inline + separate)
        - ✅ ingress 443 for cluster SG (inline + separate)
        - ✅ ingress 10250 for cluster SG (inline + separate)
        - ✅ ingress self 53 udp (inline + separate)
        - ✅ ingress self 53 tcp (inline + separate)
        - ✅ ingress self 1025 - 65535 (inline + separate)
        """

        # ADDITIONAL CLUSTER SG RULES

        node_groups_https_to_cluster_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-node-sgr-https-ingress",
            description="Node groups https to cluster API",
            from_port=443,
            ip_protocol="tcp",
            referenced_security_group_id=self.node_sg.id,
            security_group_id=self.cluster_sg.id,
            to_port=443,
            tags={"Name": f"{name}-node-sgr-https-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # ADDITIONAL NODE SG RULES

        cluster_https_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-cluster-sgr-https-ingress",
            description="Cluster API https to node groups",
            from_port=443,
            ip_protocol="tcp",
            referenced_security_group_id=self.cluster_sg.id,
            security_group_id=self.node_sg.id,
            to_port=443,
            tags={"Name": f"{name}-cluster-sgr-https-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_4443_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-cluster-sgr-4443-ingress",
            description="Cluster API to node 4443/tcp webhook",
            from_port=4443,
            ip_protocol="tcp",
            referenced_security_group_id=self.cluster_sg.id,
            security_group_id=self.node_sg.id,
            to_port=4443,
            tags={"Name": f"{name}-cluster-sgr-4443-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_6443_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-cluster-sgr-6443-ingress",
            description="Cluster API to node 6443/tcp webhook",
            from_port=6443,
            ip_protocol="tcp",
            referenced_security_group_id=self.cluster_sg.id,
            security_group_id=self.node_sg.id,
            to_port=6443,
            tags={"Name": f"{name}-cluster-sgr-6443-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_8443_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-cluster-sgr-8443-ingress",
            description="Cluster API to node 8443/tcp webhook",
            from_port=8443,
            ip_protocol="tcp",
            referenced_security_group_id=self.cluster_sg.id,
            security_group_id=self.node_sg.id,
            to_port=8443,
            tags={"Name": f"{name}-cluster-sgr-8443-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_9443_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-cluster-sgr-9443-ingress",
            description="Cluster API to node 9443/tcp webhook",
            from_port=9443,
            ip_protocol="tcp",
            referenced_security_group_id=self.cluster_sg.id,
            security_group_id=self.node_sg.id,
            to_port=9443,
            tags={"Name": f"{name}-cluster-sgr-9443-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_10250_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-cluster-sgr-10250-ingress",
            description="Cluster API to node kubelets",
            from_port=10250,
            ip_protocol="tcp",
            referenced_security_group_id=self.cluster_sg.id,
            security_group_id=self.node_sg.id,
            to_port=10250,
            tags={"Name": f"{name}-cluster-sgr-10250-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_ephemeral_to_node_groups_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-node-sgr-ephemeral-ingress",
            description="Node to node ingress on ephemeral ports",
            from_port=1025,
            ip_protocol="tcp",
            referenced_security_group_id=self.node_sg.id,
            security_group_id=self.node_sg.id,
            to_port=65535,
            tags={"Name": f"{name}-node-sgr-ephemeral-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        node_groups_tcp53_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-node-sgr-53-tcp-ingress",
            description="Node to node CoreDNS tcp",
            from_port=53,
            ip_protocol="tcp",
            referenced_security_group_id=self.node_sg.id,
            security_group_id=self.node_sg.id,
            to_port=53,
            tags={"Name": f"{name}-node-sgr-53-tcp-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        node_groups_udp53_ingress_sgr = aws.vpc.SecurityGroupIngressRule(
            resource_name=f"{name}-node-sgr-53-udp-ingress",
            description="Node to node CoreDNS udp",
            from_port=53,
            ip_protocol="udp",
            referenced_security_group_id=self.node_sg.id,
            security_group_id=self.node_sg.id,
            to_port=53,
            tags={"Name": f"{name}-node-sgr-53-udp-ingress"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        CLUSTER IAM
        - ONLY inline assume_role_policy's on roles
        - ALWAYS use aws.iam.RolePolicy and aws.iam.RolePolicyAttachment for policies
        - ALWAYS name the RolePolicy / RolePolicyAttachment resources for use in depends_on
        - putting them in here for now similar to terraform-aws-eks module
        # module.eks.aws_iam_role.this[0]:
        TODO: - i did RolePolicies in most cases
        # ✅ module.eks.aws_iam_role.this[0]:
        # ✅ module.eks.aws_iam_policy.cluster_encryption[0]:
        # ✅ module.eks.aws_iam_policy.custom[0]:
        # ✅ module.eks.aws_iam_role_policy_attachment.cluster_encryption[0]:
        # ✅ module.eks.aws_iam_role_policy_attachment.custom[0]:
        # ✅ module.eks.aws_iam_role_policy_attachment.this["AmazonEKSClusterPolicy"]:
        # ✅ module.eks.aws_iam_role_policy_attachment.this["AmazonEKSVPCResourceController"]:
        """

        self.cluster_iam_role = aws.iam.Role(
            resource_name=f"{name}-cluster-iam-role",
            name_prefix=f"{name}-cluster-",
            assume_role_policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "EKSClusterAssumeRole",
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "eks.amazonaws.com",
                            },
                            "Action": ["sts:AssumeRole", "sts:TagSession"],
                        }
                    ],
                }
            ),
            force_detach_policies=True,
            tags={"Name": f"{name}-cluster-iam-role"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        cluster_custom_role_policy = aws.iam.RolePolicy(
            resource_name=f"{name}-cluster-custom",
            name_prefix=f"{name}-cluster-custom-",
            policy=json.dumps(
                {
                    "Statement": [
                        {
                            "Action": [
                                "ec2:RunInstances",
                                "ec2:CreateLaunchTemplate",
                                "ec2:CreateFleet",
                            ],
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/eks:eks-cluster-name": "${aws:PrincipalTag/eks:eks-cluster-name}"
                                },
                                "StringLike": {
                                    "aws:RequestTag/eks:kubernetes-node-class-name": "*",
                                    "aws:RequestTag/eks:kubernetes-node-pool-name": "*",
                                },
                            },
                            "Effect": "Allow",
                            "Resource": "*",
                            "Sid": "Compute",
                        },
                        {
                            "Action": [
                                "ec2:CreateVolume",
                                "ec2:CreateSnapshot",
                            ],
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/eks:eks-cluster-name": "${aws:PrincipalTag/eks:eks-cluster-name}",
                                }
                            },
                            "Effect": "Allow",
                            "Resource": [
                                "arn:aws:ec2:*:*:volume/*",
                                "arn:aws:ec2:*:*:snapshot/*",
                            ],
                            "Sid": "Storage",
                        },
                        {
                            "Action": "ec2:CreateNetworkInterface",
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/eks:eks-cluster-name": "${aws:PrincipalTag/eks:eks-cluster-name}",
                                    "aws:RequestTag/eks:kubernetes-cni-node-name": "*",
                                }
                            },
                            "Effect": "Allow",
                            "Resource": "*",
                            "Sid": "Networking",
                        },
                        {
                            "Action": [
                                "elasticloadbalancing:CreateTargetGroup",
                                "elasticloadbalancing:CreateRule",
                                "elasticloadbalancing:CreateLoadBalancer",
                                "elasticloadbalancing:CreateListener",
                                "ec2:CreateSecurityGroup",
                            ],
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/eks:eks-cluster-name": "${aws:PrincipalTag/eks:eks-cluster-name}",
                                }
                            },
                            "Effect": "Allow",
                            "Resource": "*",
                            "Sid": "LoadBalancer",
                        },
                        {
                            "Action": "shield:CreateProtection",
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/eks:eks-cluster-name": "${aws:PrincipalTag/eks:eks-cluster-name}",
                                }
                            },
                            "Effect": "Allow",
                            "Resource": "*",
                            "Sid": "ShieldProtection",
                        },
                        {
                            "Action": "shield:TagResource",
                            "Condition": {
                                "StringEquals": {
                                    "aws:RequestTag/eks:eks-cluster-name": "${aws:PrincipalTag/eks:eks-cluster-name}",
                                }
                            },
                            "Effect": "Allow",
                            "Resource": "arn:aws:shield::*:protection/*",
                            "Sid": "ShieldTagResource",
                        },
                    ],
                    "Version": "2012-10-17",
                }
            ),
            role=self.cluster_iam_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # MANAGED POLICIES

        amz_eks_cluster_policy_attach = aws.iam.RolePolicyAttachment(
            resource_name=f"{name}-amz-cluster-policy-attach",
            role=self.cluster_iam_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            opts=pulumi.ResourceOptions(parent=self),
        )

        amz_vpc_cntrlr_policy_attach = aws.iam.RolePolicyAttachment(
            resource_name=f"{name}-amz-vpc-controller-attach",
            role=self.cluster_iam_role.name,
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSVPCResourceController",
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        KMS
        - putting them in here for now similar to terraform-aws-eks module
        module.eks.module.kms.aws_kms_key.this[0]:
        """

        self.kms_key = aws.kms.Key(
            resource_name=f"{name}-kms-key",
            bypass_policy_lockout_safety_check=False,  # Be careful ever setting this to true
            description=f"{name} cluster encryption key",
            enable_key_rotation=True,
            multi_region=False,  # Turn to true for multi-region clusters use
            deletion_window_in_days=20,
            rotation_period_in_days=365,
            tags={"Name": f"{name}-kms-key"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.kms_key_policy = aws.kms.KeyPolicy(
            resource_name=f"{name}-kms-key-policy",
            key_id=self.kms_key.id,
            policy=pulumi.Output.json_dumps(
                {
                    "Version": "2012-10-17",
                    "Id": f"{name}-key-policy",
                    "Statement": [
                        {
                            "Sid": "Enable IAM User Permissions",
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": f"arn:aws:iam::{self.current.account_id}:root",
                            },
                            "Action": "kms:*",
                            "Resource": "*",
                        },
                        {
                            "Action": [
                                "kms:Update*",
                                "kms:UntagResource",
                                "kms:TagResource",
                                "kms:ScheduleKeyDeletion",
                                "kms:Revoke*",
                                "kms:ReplicateKey",
                                "kms:Put*",
                                "kms:List*",
                                "kms:ImportKeyMaterial",
                                "kms:Get*",
                                "kms:Enable*",
                                "kms:Disable*",
                                "kms:Describe*",
                                "kms:Delete*",
                                "kms:Create*",
                                "kms:CancelKeyDeletion",
                            ],
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": sso_admin_role_arn,
                            },
                            "Resource": "*",
                            "Sid": "KeyAdministration",
                        },
                        {
                            "Action": [
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:Encrypt",
                                "kms:DescribeKey",
                                "kms:Decrypt",
                            ],
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": self.cluster_iam_role.arn,
                            },
                            "Resource": "*",
                            "Sid": "KeyUsage",
                        },
                    ],
                }
            ),
            opts=pulumi.ResourceOptions(parent=self),
        )

        self.kms_key_alias = aws.kms.Alias(
            resource_name=f"alias/eks/{name}",
            name=f"alias/eks/{name}",
            target_key_id=self.kms_key.id,
            opts=pulumi.ResourceOptions(parent=self),
        )

        clusterencryption_kms_role_policy = aws.iam.RolePolicy(
            resource_name=f"{name}-clusterencryption",
            name_prefix=f"{name}-clusterencryption-",
            policy=pulumi.Output.json_dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Action": [
                                "kms:Encrypt",
                                "kms:Decrypt",
                                "kms:ListGrants",
                                "kms:DescribeKey",
                            ],
                            "Effect": "Allow",
                            "Resource": self.kms_key.arn,
                        }
                    ],
                }
            ),
            role=self.cluster_iam_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        NODE GROUP IAM
        # ✅ module.eks.module.eks_managed_node_group["initial"].data.aws_iam_policy_document.assume_role_policy[0]:
        # ✅ module.eks.module.eks_managed_node_group["initial"].aws_iam_role.this[0]:
        # ✅ module.eks.module.eks_managed_node_group["initial"].aws_iam_role_policy_attachment.this["AmazonEC2ContainerRegistryReadOnly"]:
        # ✅ module.eks.module.eks_managed_node_group["initial"].aws_iam_role_policy_attachment.this["AmazonEKSWorkerNodePolicy"]:
        # ✅ module.eks.module.eks_managed_node_group["initial"].aws_iam_role_policy_attachment.this["AmazonEKS_CNI_IPv6_Policy"]:
        # ✅ module.eks.aws_iam_policy.cni_ipv6_policy[0]:
        """

        self.node_iam_role = aws.iam.Role(
            resource_name=f"{name}-initial-node-group-iam-role",
            name_prefix=f"{name}-initial-node-",
            assume_role_policy=json.dumps(
                {
                    "Statement": [
                        {
                            "Action": "sts:AssumeRole",
                            "Effect": "Allow",
                            "Principal": {
                                "Service": "ec2.amazonaws.com",
                            },
                        }
                    ],
                    "Version": "2012-10-17",
                }
            ),
            force_detach_policies=True,
            tags={"Name": f"{name}-initial-node-group-iam-role"},
            opts=pulumi.ResourceOptions(parent=self),
        )

        # TODO: better to go directly on vpc irsa / pod identity?
        # - [AWS EKS vpc cni ipv6](https://docs.aws.amazon.com/eks/latest/userguide/deploy-ipv6-cluster.html)
        # - [AWS EKS vpc cni ipv6 irsa](https://docs.aws.amazon.com/eks/latest/userguide/cni-iam-role.html)
        node_group_cni_ipv6_role_policy = aws.iam.RolePolicy(
            resource_name=f"{name}-cni-ipv6-policy",
            name_prefix=f"{name}-cni-ipv6-policy-",
            policy=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "AssignDescribe",
                            "Effect": "Allow",
                            "Action": [
                                "ec2:DescribeTags",
                                "ec2:DescribeNetworkInterfaces",
                                "ec2:DescribeInstances",
                                "ec2:DescribeInstanceTypes",
                                "ec2:AssignIpv6Addresses",
                            ],
                            "Resource": "*",
                        },
                        {
                            "Sid": "CreateTags",
                            "Effect": "Allow",
                            "Action": "ec2:CreateTags",
                            "Resource": "arn:aws:ec2:*:*:network-interface/*",
                        },
                    ],
                }
            ),
            role=self.node_iam_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # MANAGED POLICIES

        node_group_eks_worker_node_role_policy = aws.iam.RolePolicyAttachment(
            resource_name=f"{name}-amz-worker-node-policy-attach",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            role=self.node_iam_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        # TODO: remove after confirming works ok - tf only has ivp6 one on node role
        # node_group_eks_cni_role_policy = aws.iam.RolePolicyAttachment(
        #     resource_name=f"{name}-amz-cni-policy-attach",
        #     policy_arn="arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
        #     role=self.node_iam_role.name,
        #     opts=pulumi.ResourceOptions(parent=self),
        # )

        node_group_eks_ecr_ro_role_policy = aws.iam.RolePolicyAttachment(
            resource_name=f"{name}-amz-ecr-ro-policy-attach",
            policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            role=self.node_iam_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        node_group_ssm_role_policy = aws.iam.RolePolicyAttachment(
            resource_name=f"{name}-amz-ssm-policy-attach",
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            role=self.node_iam_role.name,
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        CLOUDWATCH
        NOTE: Didn't use this so didn't create it
        - should use a KMS Key for encryption as well https://github.com/terraform-aws-modules/terraform-aws-eks/blob/master/main.tf#L203
        # module.eks.aws_cloudwatch_log_group.this[0]:
        log group name must be in the below format and match EKS cluster name
          name              = "/aws/eks/${var.cluster_name}/cluster"
        """

        """
        EKS CLUSTER
        using some defaults from ipv6 eks cluster blueprint to get this running
        in the future, another stack will have better practices and do this differently
        - bootstrap_self_managed_addons=True
        # module.eks.aws_eks_cluster.this[0]:
        DEPENDS_ON: I've added some extras but including
        - node SG rule attachments
        - cluster SG rule attachments
        - cluster iam role policy attachments 
        """

        self.cluster = aws.eks.Cluster(
            resource_name=f"{name}",
            name=f"{name}",
            access_config={
                "authentication_mode": "API",
                "bootstrap_cluster_creator_admin_permissions": False,  # use access entries instead
            },
            bootstrap_self_managed_addons=True,
            enabled_cluster_log_types=[
                "api",
                "audit",
                "authenticator",
            ],
            encryption_config={
                "resources": ["secrets"],
                "provider": {
                    "key_arn": self.kms_key.arn,
                },
            },
            kubernetes_network_config={
                "ip_family": "ipv6",  # MUST be ipv6 at creation - cannot change after
                "elastic_load_balancing": {
                    "enabled": False,
                },
            },
            role_arn=self.cluster_iam_role.arn,
            upgrade_policy={
                "support_type": "STANDARD",  # AUTO UPGRADE to avoid huge costs on playgrounds
            },
            version=cluster_version,
            vpc_config={  # https://www.pulumi.com/registry/packages/aws/api-docs/eks/cluster/#clustervpcconfig
                "endpoint_private_access": True,
                "endpoint_public_access": True,
                "public_access_cidrs": ["0.0.0.0/0"],
                "security_group_ids": [  # CLUSTER SG and any addtl SGs
                    self.cluster_sg.id
                ],
                "subnet_ids": private_subnet_ids,
            },
            tags={"Name": name},
            opts=pulumi.ResourceOptions(
                parent=self,
                depends_on=[
                    node_groups_all_ipv4_egress_sgr,
                    node_groups_all_ipv6_egress_sgr,
                    node_groups_https_to_cluster_ingress_sgr,
                    node_groups_tcp53_ingress_sgr,
                    node_groups_udp53_ingress_sgr,
                    cluster_all_ipv4_egress_sgr,
                    cluster_all_ipv6_egress_sgr,
                    cluster_https_to_node_groups_ingress_sgr,
                    cluster_4443_to_node_groups_ingress_sgr,
                    cluster_6443_to_node_groups_ingress_sgr,
                    cluster_8443_to_node_groups_ingress_sgr,
                    cluster_9443_to_node_groups_ingress_sgr,
                    cluster_10250_to_node_groups_ingress_sgr,
                    cluster_ephemeral_to_node_groups_ingress_sgr,
                    # should depend also on: cloudwatch log group
                    cluster_custom_role_policy,
                    clusterencryption_kms_role_policy,
                    amz_eks_cluster_policy_attach,  # this is the main important one
                    amz_vpc_cntrlr_policy_attach,
                    # cni_ipv6_policy instead of a node role policy? If i have errors, try changing this
                    # NOTE: auto-mode requires more AMZ default managed policy attachments
                ],
            ),
        )

        """
        EKS ACCESS ENTRIES
        for now - can test by doing a pulumi import
        # module.eks.aws_eks_access_entry.this["cluster_creator"]:
        # module.eks.aws_eks_access_policy_association.this["cluster_creator_admin"]:
        """

        admin_sso_access_entry = aws.eks.AccessEntry(
            resource_name=f"{name}-admin-sso",
            cluster_name=self.cluster.name,
            principal_arn=sso_admin_role_arn,
            type="STANDARD",
            tags={"Name": f"{name}-admin-sso"},
            user_name=f"{sso_admin_assume_role_arn}/{{{{SessionName}}}}",  # escape double brackets
            opts=pulumi.ResourceOptions(
                parent=self, ignore_changes=["tags", "tagsAll"]
            ),
        )

        admin_sso_access_entry_assoc = aws.eks.AccessPolicyAssociation(
            resource_name=f"{name}-admin-sso",
            access_scope={
                "type": "cluster",
            },
            cluster_name=self.cluster.name,
            policy_arn="arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy",
            principal_arn=sso_admin_role_arn,
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        EKS ADD ONS - DONE
        NOTE: these three are auto installed on any new EKS cluster bc bootstrapping is turned on
        NOTE: the config values are all null and not custom so no work to do
        # module.eks.aws_eks_addon.this["coredns"]:
        # module.eks.aws_eks_addon.this["kube-proxy"]:
        # module.eks.aws_eks_addon.this["vpc-cni"]:
        """

        """
        IRSA - NOT USED
        REQUIRES EKS cluster oidc identity issuer url already existing
        - this is different than the EKS identity provider
        NOTE: skipping this as the blueprint works ok without it, I was able to launch an nginx pod
        # module.eks.data.tls_certificate.this[0]:
        # module.eks.aws_iam_openid_connect_provider.oidc_provider[0]:
        """

        """
        NOTE: DIDN'T NEED THIS
        SLEEP? not 100% sure where it should go
        # module.eks.time_sleep.this[0]:

        # This sleep resource is used to provide a timed gap between the cluster creation and the downstream dependencies
        # that consume the outputs from here. Any of the values that are used as triggers can be used in dependencies
        # to ensure that the downstream resources are created after both the cluster is ready and the sleep time has passed.
        # This was primarily added to give addons that need to be configured BEFORE data plane compute resources
        # enough time to create and configure themselves before the data plane compute resources are created.
        """

        """
        EKS MANAGED NODE GROUP
        - largely based off https://github.com/terraform-aws-modules/terraform-aws-eks/blob/master/node_groups.tf
        - and https://github.com/terraform-aws-modules/terraform-aws-eks/blob/master/modules/eks-managed-node-group/main.tf
        - terraform-aws-eks module keeps these resources in separate node_groups.tf file but i'm including in here for simplicity
        NOTE: didn't need the null_resource
        # module.eks.module.eks_managed_node_group["initial"].aws_eks_node_group.this[0]:
        # module.eks.module.eks_managed_node_group["initial"].aws_launch_template.this[0]:
        # module.eks.module.eks_managed_node_group["initial"].module.user_data.null_resource.validate_cluster_service_cidr:
        """

        launch_template = aws.ec2.LaunchTemplate(
            resource_name=f"{name}-initial-node-group-lt",
            name_prefix=f"{name}-initial-",
            disable_api_stop=False,
            disable_api_termination=False,
            description="Custom launch template for initial EKS managed node group",
            metadata_options={
                "http_endpoint": "enabled",
                "http_put_response_hop_limit": 2,
                "http_tokens": "required",
            },
            monitoring={
                "enabled": True,
            },
            vpc_security_group_ids=[self.node_sg.id],
            update_default_version=True,
            tag_specifications=[
                {"resource_type": "instance", "tags": {"Name": f"{name}-initial"}},
                {
                    "resource_type": "network-interface",
                    "tags": {"Name": f"{name}-initial"},
                },
                {"resource_type": "volume", "tags": {"Name": f"{name}-initial"}},
            ],
            tags={"Name": f"{name}-initial-node-group-lt"},
            opts=pulumi.ResourceOptions(
                parent=self,
                depends_on=[
                    node_group_cni_ipv6_role_policy,
                    node_group_eks_worker_node_role_policy,
                    node_group_eks_ecr_ro_role_policy,
                    node_group_ssm_role_policy,
                ],
            ),
        )

        self.node_group = aws.eks.NodeGroup(
            resource_name=f"{name}-initial-node-group",
            cluster_name=self.cluster.name,
            instance_types=["m5.large"],
            launch_template={
                "id": launch_template.id,
                "version": launch_template.default_version,
            },
            node_group_name_prefix=f"{name}-initial-",
            node_role_arn=self.node_iam_role.arn,
            subnet_ids=private_subnet_ids,
            scaling_config={
                "desired_size": 1,
                "max_size": 2,
                "min_size": 1,
            },
            update_config={
                "max_unavailable": 1,
            },
            tags={"Name": f"{name}-initial-node-group"},
            opts=pulumi.ResourceOptions(
                parent=self,
                depends_on=[
                    node_group_cni_ipv6_role_policy,
                    node_group_eks_worker_node_role_policy,
                    node_group_eks_ecr_ro_role_policy,
                ],
            ),
        )

        """
        By registering the outputs on which the component depends, we ensure
        that the Pulumi CLI will wait for all the outputs to be created before
        considering the component itself to have been created.
        - explicitly setting objects as outputs
        NOTE: didn't set all of the resources on register outputs since everything is in one file and not used elsewhere
        """
        self.register_outputs(
            # TODO: add in lots of other self items
            {
                "cluster": self.cluster,
                "cluster_iam_role": self.cluster_iam_role,
                "cluster_sg": self.cluster_sg,
                "kms_key": self.kms_key,
                "kms_key_alias": self.kms_key_alias,
                "node_iam_role": self.node_iam_role,
                "node_sg": self.node_sg,
            }
        )
