""" Stack Config """
import pulumi

# Explicitly provide config outputs
_config = pulumi.Config()

AZ_ZONE_IDS = _config.require_object("az_zone_ids")
PROJECT_NAME = _config.require("project_name")
VPC_CIDR = _config.require("vpc_cidr")
