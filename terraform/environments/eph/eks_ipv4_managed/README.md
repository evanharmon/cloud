# EKS playground
ipv4 with managed node groups with bottlerocket

## Goal
this folder should be able to stand up a complete personal EKS cluster

## Tools
i'm using `uv` to be able to test parts with localstack - so there are additional files in here.

## Structure
right now just creating separate named files for the all the types of resources

- main.tf
- vpc.tf
- iam.tf
etc...

## Commands

### Update local kubeconfig
or this could be setup in terraform...
`aws eks update-kubeconfig --name eph-ipv4-mng --alias eph-ipv4-mng  --user-alias admin`