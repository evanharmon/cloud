# PULUMI CLOUD-EKS-IPV6-AUTO

## Features
eks ipv6 dual-stack automode cluster

## Commands

### Run pulumi
1. **Sign in to AWS**
`aws sso login --profile eph-music-dev`

2. **Export aws credentials as env vars**
`source ../../scripts/aws_creds_export.sh eph-music-dev`

3. **Run pulumi commands using uv managed version**
`uvx pulumi preview`
