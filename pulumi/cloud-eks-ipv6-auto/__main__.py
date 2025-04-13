""" Pulumi """
# Call pulumi files that are not constructors
# ruff: noqa: F401
import pulumi
import pulumi_aws as aws
from stack_config import AZ_ZONE_IDS, PROJECT_NAME, VPC_CIDR
from vpc import VpcResources

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

pulumi.export("selected_azs_names", selected_az_names)
pulumi.export("selected_azs_zone_ids", selected_az_zone_ids)

# SINGLE REGION FOR NOW - us-east-1

# Clustername must be known ahead of time for tagging non-eks resource on creation
# - like subnets
EKS_CLUSTER_NAME = f"{PROJECT_NAME}"
eks_vpc = VpcResources(
    name=PROJECT_NAME,
    az_zone_ids=selected_az_zone_ids,
    cluster_name=EKS_CLUSTER_NAME,
    vpc_cidr_block=VPC_CIDR,
)
