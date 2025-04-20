# cloud
example cloud repo

## Infrastructure as Code

Using basic exported env creds or local named aws-profiles.
Doing this so it'll force me to setup IaC in `Core` repo
That's where things like special IAM roles, cross-account, etc should happen.

Example:
- deploying to staging from a local machine
- assuming a dedicated role like `Administrators` or `CI` in pulumi / tf config
