variable "cluster_version" {
  description = "EKS cluster version"
  type = string
}

variable "environment" {
  description = "Environment"
  type = string
}

variable "num_azs" {
  description = "number of AZs"
  type = number
}

variable "project_name" {
  description = "Name of the project."
  type = string
}

variable "region" {
  description = "AWS Region"
  type = string
}

variable "stack_name" {
  description = "Stack name"
  type = string
}

variable "stack_type" {
  description = "Stack type"
  type = string
}

variable "vpc_cidr" {
  description = "VPC cidr block"
  type = string
}

variable "tags" {
  description = "Default tags to automatically add to all AWS resources"
  type = map(string)
}
