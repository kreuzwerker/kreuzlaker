# XW Data Batch Stack

## Preparation

```bash
brew install git make python@3.10 node # all the rest gets installed into node.js/python environments
git clone git@gitlab.kreuzwerker.de:engineering/data-engineering/xw-data-toolkit.git
cd xw-data-toolkit/xw-batch
# Setup all required node.js and python packages in environments
make install-packages # only deploying via cdk 
make install-dev-packages # for developing (deploy + test + lint)
# Activate the environments -> adds cdk and all needed python commands into the path
make shell
```

## Deployment from local machines

This assumes you have set up aws credentials which are usable by `aws`/`boto3`/`cdk` 
(e.g. `export AWS_PROFILE=... && aws sso login` via SSO).

To deploy, run once `make bootstrap` and afterwards `make deploy`.

This will
* create the python virtual environment in `.venv/`, if it doesn't exist
* create a `node_modules/` subfolder with the required node.js packages, if it doesn't exist
* install the required packages for both nodejs (cdk) and python (e.g. cdk packages)
* run `cdk bootstrap` to deploy infrastructure needed by `cdk`.
* run `cdk synth -o cdk.out` to synthesize the stack(s) in `cdk.out/`
* run `cdk deploy -o cdk.out --hotswap dev/XwBatchStack` to deploy the dev stack which is defined in the synthesized
  output in `cdk.out/`.

To deploy again, run `make synth && make deploy` (just `make deploy` would deploy the old synthesized stack!).

Repeated runs of will of course reuse the python/node.js environments unless you change `requirements.txt.in`
(or the derived `requirements.txt`) or `package-lock.json`.

## Destroying the stack

To destroy the set-up `XwBatchStack` stack, run `make destroy`, which will make sure that the venv and node environments
exist and run `cdk destroy`.

## Useful commands

* `make help`                 shows all the available makefile targets, which also cover some of the below cdk commands
* `make bootstrap`            deploys needed cdk infrastructure into the currently active aws profile (run only once)
* `make install-packages`     installs packages from requirements.txt (also creates the venv!)
* `make install-dev-packages` installs additional packages from requirements-dev.txt needed for development
* `make update-packages`      adds/updates packages from requirements.txt.in (recreates the venv!)
* `make synth`                emits the synthesized CloudFormation template to the default output folder
* `make deploy`               deploys the dev stack from the previously synthesized CF templates to AWS into 
                              the currently active aws profile
* `make destroy`              destroys the stack the currently active aws profile
* `cdk ls`                    lists all stacks in the app
* `cdk synth`                 emits the synthesized CloudFormation template
* `cdk deploy <stack name>`   deploys this stack to your default AWS account/region
* `cdk diff`                  compares deployed stack with current state
* `cdk docs`                  opens CDK documentation

Enjoy!
