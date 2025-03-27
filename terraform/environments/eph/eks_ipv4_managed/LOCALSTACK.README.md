# LOCALSTACK TF

## Guidelines
just using this here to test out AWS for specific files NOT the EKS setup right now.
so you can could pass in just the specific module against localstack

## Requirements

### Setup with `uv`

```bash
# install localstack
brew install localstack/tap/localstack-cli
# install if not on machine yet
curl -LsSf https://astral.sh/uv/install.sh | sh
# should already be done - but showing for example
uv init --bare
## install dependencies
uv add terraform-local
```

### Setup AWS Localstack vars
use `--endpoint-url` for localstack
```bash
export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"
export AWS_DEFAULT_REGION="eu-west-1"
aws --endpoint-url=http://localhost:4566 ec2 describe-vpcs
```

or setup a proper aws config / credentials file
```bash
mkdir -p ~/.aws && touch ~/.aws/config
cat > ~/.aws/config <<EOF
[profile localstack]
region=us-east-1
output=json
endpoint_url = http://localhost:4566
EOF
mkdir -p ~/.aws && touch ~/.aws/credentials
cat > ~/.aws/credentials <<EOF
[localstack]
aws_access_key_id=test
aws_secret_access_key=test
EOF
aws --profile localstack ec2 describe-vpcs
```
## Commands

### Start localstack
requires docker / orbstack running.
`localstack start -d`

### Create resources
```bash
tflocal init
tflocal plan --target=module.vpc -out=tfplan
tflocal apply tfplan
tflocal delete
```

### Stop localstack
also will delete AWS resources in ephemeral state
`localstack stop`
