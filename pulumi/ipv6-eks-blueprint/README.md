# PULUMI ipv6-eks blueprint

## Features
basic eks cluster with managed node group, autoscaler
ipv6 dual stack vpc

i tried using pulumi's converter on the terraform-aws-eks-blueprints but it doesn't support
try, and a bunch of errors came out.

## Commands

### Set AWS env vars for aws cli commands
optional - can always set `AWS_PROFILE` locally instead

1. **Sign in to AWS**
`aws sso login --profile eph-music-dev`

2. **Export aws credentials as env vars**
`source ../../scripts/aws_creds_export.sh eph-music-dev`

### Run pulumi
profile is hard-coded in my Pulumi.eph.yaml

`uvx pulumi up`

### Update kubeconfig locally
based on PROJECT_NAME / CLUSTER_NAME in stack config

```bash
AWS_PROFILE=eph-music-dev aws eks --region us-east-1 update-kubeconfig --name eks-ipv6-bp-us-east-1  --alias eks-ipv6-bp-us-east-1 --user-alias admin
```

### Destroy
`uvx pulumi destroy`
