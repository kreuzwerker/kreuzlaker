AWS_ACCOUNT_ID=$(shell aws sts get-caller-identity --query "Account" --output text)
AWS_REGION=$(shell aws configure get region)
REGISTRY_URL=$(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com
IMG_LATEST=$(REGISTRY_URL)/dbt-run:latest

all: build

build:
	docker build -t dbt-run .


run: .env
	# Pass aws credentials in to have access to aws
	# Make sure you have added AWS_PROFILE=somethingsomething into .env!
	docker run -v $${HOME}/.aws:/root/.aws:rw --env-file .env dbt-run

.env:
	@echo "Created a .env file. Please edit to make sure aws credentials are passed in"
	@echo "# Add environment variables needed for dev aws access." > .env
	@echo "# We mount your ~/.aws folder into the container, but AWS_PROFILE might be needed," >> .env
	@echo "# if you do not use the default" >> .env
	@echo ""
	@echo "#AWS_PROFILE=${AWS_PROFILE}" >> .env
	@echo "# The target in profiles.yml (profiles-prod.yml in the repo) -> docker to not try with prod settings"
	@echo "DBT_TARGET=docker" >> .env
	false

deploy:
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin "$(REGISTRY_URL)"
	docker build -t "$(IMG_LATEST)" .
	docker push "$(IMG_LATEST)"
