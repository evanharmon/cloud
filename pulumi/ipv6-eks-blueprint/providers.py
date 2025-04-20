""" Providers """
# import pulumi
import pulumi_aws as aws

# Relying mainly on config settings for AWS provider
aws_provider = aws.Provider("aws-provider")
