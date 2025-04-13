import ipaddress

import pulumi
import pulumi_aws as aws

"""
HELPERS
"""

# Allows IPv6 only clients to communicate with IPv4 only services
NAT64_DNS64_RESERVED_PREFIX = "64:ff9b::/96"

# cidr_subnet function like terraform-aws-module
def cidr_subnet(prefix, newbits, netnum) -> str:
    """similar to terraform local with cidr_subnet()"""
    network = ipaddress.ip_network(prefix)
    new_prefix_len = network.prefixlen + newbits
    new_subnet_size = 2 ** (32 - new_prefix_len)
    start_ip = network.network_address + (netnum * new_subnet_size)
    return f"{start_ip}/{new_prefix_len}"


# Get IPv6 based on index like terraform-aws-module
def get_ipv6_subnet(base: str, index: int, newbits: int = 8) -> str:
    network = ipaddress.IPv6Network(base)
    new_prefix_len = network.prefixlen + newbits
    return str(list(network.subnets(new_prefix=new_prefix_len))[index])


class VpcResources(pulumi.ComponentResource):
    """dual-stack VPC class with resources"""

    def __init__(
        self,
        name: str,
        cluster_name: str,
        az_zone_ids: list,
        vpc_cidr_block: str,
        opts: pulumi.ResourceOptions = None,
    ):
        super().__init__(t="eph:eks:VpcResources", name=name, props=None, opts=opts)

        """ VPC Setup """
        self.vpc = aws.ec2.Vpc(
            resource_name=name,
            assign_generated_ipv6_cidr_block=True,
            cidr_block=vpc_cidr_block,
            enable_dns_hostnames=True,
            enable_dns_support=True,
            tags={"Name": name},
            opts=pulumi.ResourceOptions(parent=self),
        )

        """
        SUBNETS
        """

        self.public_subnets = []
        self.private_subnets = []

        # NOTE: still doing /19's even on two AZs
        # 3 for /19
        private_subnet_cidrs = [
            cidr_subnet(vpc_cidr_block, 3, k + len(az_zone_ids))
            for k in range(len(az_zone_ids))
        ]
        public_subnet_cidrs = [
            cidr_subnet(vpc_cidr_block, 3, k) for k in range(len(az_zone_ids))
        ]

        # Calculate the IPv6 subnet allocations (will be Output objects)
        ipv6_subnet_allocations = []
        for i in range(len(az_zone_ids) * 2):  # Both public and private subnets
            ipv6_subnet = self.vpc.ipv6_cidr_block.apply(
                lambda v6base, idx=i: get_ipv6_subnet(v6base, idx)
            )
            ipv6_subnet_allocations.append(ipv6_subnet)

        for idx, zone_id in enumerate(az_zone_ids):
            # NOT launching karpenter instances in public subnets
            public_subnet = aws.ec2.Subnet(
                resource_name=f"{name}-public-{zone_id}",
                assign_ipv6_address_on_creation=True,
                availability_zone_id=zone_id,
                enable_dns64=True,
                cidr_block=public_subnet_cidrs[idx],
                ipv6_cidr_block=ipv6_subnet_allocations[idx],
                map_public_ip_on_launch=False,
                enable_resource_name_dns_a_record_on_launch=False,
                enable_resource_name_dns_aaaa_record_on_launch=True,
                tags={
                    "Name": f"{name}-public-{zone_id}",
                    f"kubernetes.io/cluster/{cluster_name}": "shared",
                    "kubernetes.io/role/elb": "1",
                },
                vpc_id=self.vpc.id,
                opts=pulumi.ResourceOptions(parent=self.vpc),
            )
            self.public_subnets.append(public_subnet)

            # Only launching karpenter instances in private subnets
            private_subnet = aws.ec2.Subnet(
                resource_name=f"{name}-private-{zone_id}",
                assign_ipv6_address_on_creation=True,
                availability_zone_id=zone_id,
                enable_dns64=True,
                cidr_block=private_subnet_cidrs[idx],
                ipv6_cidr_block=ipv6_subnet_allocations[idx + len(az_zone_ids)],
                map_public_ip_on_launch=False,
                enable_resource_name_dns_a_record_on_launch=False,
                enable_resource_name_dns_aaaa_record_on_launch=True,
                tags={
                    "Name": f"{name}-private-{zone_id}",
                    "karpenter.sh/discovery": cluster_name,
                    f"kubernetes.io/cluster/{cluster_name}": "shared",
                    "kubernetes.io/role/internal-elb": "1",
                },
                vpc_id=self.vpc.id,
                opts=pulumi.ResourceOptions(parent=self.vpc),
            )

            self.private_subnets.append(private_subnet)

        """
        Manage default resources
        TODO:
        - aws_default_security_group
        - aws_default_route_table
        - aws_default_network_acl
        """

        """
        PUBLIC ROUTING
        - aws_internet_gateway
        - public aws_route_table
        - public_internet_gateway_ipv6 aws_route
        - public_internet_gateway aws_route
        - public aws_route_table_association(s)
        """

        self.igw = aws.ec2.InternetGateway(
            resource_name=f"{name}-igw",
            vpc_id=self.vpc.id,
            tags={"Name": f"{name}-igw"},
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        self.public_route_table = aws.ec2.RouteTable(
            resource_name=f"{name}-public",
            vpc_id=self.vpc.id,
            tags={"Name": f"{name}-public"},
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        aws.ec2.Route(
            resource_name=f"{name}-public-igw",
            destination_cidr_block="0.0.0.0/0",
            gateway_id=self.igw.id,
            route_table_id=self.public_route_table.id,
            opts=pulumi.ResourceOptions(parent=self.public_route_table),
        )

        aws.ec2.Route(
            resource_name=f"{name}-public-igw-ipv6",
            destination_ipv6_cidr_block="::/0",
            gateway_id=self.igw.id,
            route_table_id=self.public_route_table.id,
            opts=pulumi.ResourceOptions(parent=self.public_route_table),
        )

        # Attach RouteTable to each subnet
        for subnet in self.public_subnets:
            aws.ec2.RouteTableAssociation(
                resource_name=subnet._name.replace("subnet", "rta"),
                route_table_id=self.public_route_table.id,
                subnet_id=subnet.id,
                opts=pulumi.ResourceOptions(parent=self.public_route_table),
            )

        # TODO: do last after all public / IGW
        """
        PRIVATE ROUTING
        NOTE(evan): just using 1 EIP / nat gw to save $$.
        - should be 2-3 for actual high availability
        Note(evan): just 1 private route table since 1 Nat gw
        - ideally would be route table per SUBNET with a nat for each
        - would require for loop, etc to support multiple NAT gateways
        TODO:
        - aws_nat_gateway
        - aws_egress_only_internet_gateway
        - nat aws_eip
        - private aws_route_table
        - private_nat_gateway aws_route
        - private_ipv6_egress aws_route
        - private_dns64_nat_gateway aws_route
        - private aws_route_table_association(s)
        """

        self.nat_eip = aws.ec2.Eip(
            resource_name=f"{self.public_subnets[0]._name}-nat-eip",
            domain="vpc",
            network_border_group="us-east-1",
            public_ipv4_pool="amazon",
            tags={"Name": f"{self.public_subnets[0]._name}-nat-eip"},
            opts=pulumi.ResourceOptions(parent=self.vpc, depends_on=[self.igw]),
        )

        self.nat_gw = aws.ec2.NatGateway(
            resource_name=f"{self.public_subnets[0]._name}-nat-gw",
            allocation_id=self.nat_eip.id,
            subnet_id=self.private_subnets[0].id,
            tags={"Name": f"{self.public_subnets[0]._name}-nat-eip"},
            opts=pulumi.ResourceOptions(parent=self.vpc, depends_on=[self.igw]),
        )

        self.egress_only_igw = aws.ec2.EgressOnlyInternetGateway(
            resource_name=f"{name}-egress-only-igw",
            vpc_id=self.vpc.id,
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        self.private_route_table = aws.ec2.RouteTable(
            resource_name=f"{name}-private",
            vpc_id=self.vpc.id,
            tags={"Name": f"{name}-private"},
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        aws.ec2.Route(
            resource_name=f"{name}-private-nat-gw",
            destination_cidr_block="0.0.0.0/0",
            nat_gateway_id=self.nat_gw.id,
            route_table_id=self.private_route_table.id,
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        aws.ec2.Route(
            resource_name=f"{name}-private-dns64-nat-gw",
            destination_ipv6_cidr_block=NAT64_DNS64_RESERVED_PREFIX,
            nat_gateway_id=self.nat_gw.id,
            route_table_id=self.private_route_table.id,
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        aws.ec2.Route(
            resource_name=f"{name}-private-ipv6-egress",
            destination_ipv6_cidr_block="::/0",
            egress_only_gateway_id=self.egress_only_igw.id,
            route_table_id=self.private_route_table.id,
            opts=pulumi.ResourceOptions(parent=self.vpc),
        )

        # Attach RouteTable to each subnet
        for subnet in self.private_subnets:
            aws.ec2.RouteTableAssociation(
                resource_name=subnet._name.replace("subnet", "rta"),
                route_table_id=self.private_route_table.id,
                subnet_id=subnet.id,
                opts=pulumi.ResourceOptions(parent=self.private_route_table),
            )

        """
        By registering the outputs on which the component depends, we ensure
        that the Pulumi CLI will wait for all the outputs to be created before
        considering the component itself to have been created.
        - explicitly setting objects as outputs
        """
        self.register_outputs(
            {
                "egress_only_gw": self.egress_only_igw,
                "igw": self.igw,
                "nat_eip": self.nat_eip,
                "nat_gw": self.nat_gw,
                "public_route_table": self.public_route_table,
                "public_subnets": self.public_subnets,
                "private_route_table": self.private_route_table,
                "private_subnets": self.private_subnets,
                "vpc": self.vpc.id,
            }
        )
