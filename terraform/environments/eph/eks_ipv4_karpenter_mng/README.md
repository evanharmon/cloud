# EKS IPV4 KARPENTER WITH MANAGED NODE GROUP

## Warnings
Right now, tearing this down with karpenter instances up leaves them running!
this project does not terraform apply cleanly. Runs in to errors around:
- CoreDNS

## Features
IRSA setups!

- karpenter with managed node group
- vpc cni with network policies
- working aws-lb-controller

## Running
```bash
# make sure you are logged in, profile used in TF setup
aws sso login --profile eph-music-dev
# export AWS creds as helm / other tools will need it for getting EKS token
output=$(aws configure export-credentials --profile eph-music-dev --format env-no-export) && for line in $output; do export $(echo "$line"); done
terraform plan
terraform apply
terraform destroy
```
