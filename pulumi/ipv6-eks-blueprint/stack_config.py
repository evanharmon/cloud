""" Stack Config """
import pulumi

# Explicitly provide config outputs
# NOTE: `aws:` values aren't available as provider won't be initialized yet
_config = pulumi.Config()

AZ_ZONE_IDS = _config.require_object("az_zone_ids")
CLUSTER_VERSION = _config.get("cluster_version")
PROJECT_NAME = _config.require("project_name")
REGION = _config.require("region")
VPC_CIDR = _config.require("vpc_cidr")

STACK_NAME = pulumi.get_stack()
STACK_REGION_NAME = f"{PROJECT_NAME}-{REGION}"

# Clustername must be known ahead of time for tagging non-eks resource on creation
# - like subnets
EKS_CLUSTER_NAME = f"{STACK_REGION_NAME}"

SSO_ADMIN_ROLE_NAME = _config.require('sso_admin_role_name')
