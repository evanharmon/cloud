"""An AWS Python Pulumi program"""

# Call pulumi files that are not constructors
# ruff: noqa: F401
import pulumi
import pulumi_aws as aws
from eks import Cluster
from stack_config import (
    AZ_ZONE_IDS,
    CLUSTER_VERSION,
    EKS_CLUSTER_NAME,
    SSO_ADMIN_ROLE_NAME,
    VPC_CIDR,
)
from vpc import Vpc

"""
IDEA: could create cluster parent component for all resources for easier reference
in child components
"""

"""
Get available AZ names by speicific zone ids in config
- ensures same physical location across multiple AWS accounts
"""
available_azs = aws.get_availability_zones(
    filters=[
        {"name": "opt-in-status", "values": ["opt-in-not-required"]},
        {"name": "zone-id", "values": AZ_ZONE_IDS},
    ]
)
# Use zone_id to ensure same physical location across multiple accounts
selected_az_names = available_azs.names
selected_az_zone_ids = available_azs.zone_ids

# SINGLE REGION SETUP FOR NOW - us-east-1

# USE REGION STACK NAME TO AVOID DUPE ARN's FOR FUTURE REGIONS
eks_vpc = Vpc(
    name=EKS_CLUSTER_NAME,
    az_zone_ids=selected_az_zone_ids,
    cluster_name=EKS_CLUSTER_NAME,
    vpc_cidr_block=VPC_CIDR,
)

eks_cluster = Cluster(
    name=EKS_CLUSTER_NAME,
    cluster_version=CLUSTER_VERSION,
    admin_role_name=SSO_ADMIN_ROLE_NAME,
    private_subnet_ids=[subnet.id for subnet in eks_vpc.private_subnets],
    vpc_id=eks_vpc.vpc.id,
)
