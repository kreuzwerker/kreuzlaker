# Github CI/CD oidc via cdk

Modeled after https://github.com/WtfJoke/aws-gh-oidc (which is for github) with the information found in
https://docs.gitlab.com/ee/ci/cloud_services/aws/

Needs to be configured with the right role actions and manually deployed (once) into the main deployment account
for the main app.

## Configure and deployment

Deployment has to be done manually into a specific aws account and with a role which is allowed to do everything your
finally want your gitlab pipeline to do. The deployment of this CI/CD Identity / OIDC stack has to happen only once,
so it can be kept separate from the main app stack.

You need to configure the role which is set up in this stack to allow it whatever you the CICD pipeline need to do.
E.g. in case of deploying a (different) cdk stack, the role needs to be able to assume the cdk roles which were setup
during the cdk bootstrap part. You can also adjust the

- `npm run build && npm run test` to check if the stack still works as expected (test probably need changes, too)
- `cdk deploy` to deploy the stack into the currently active aws environment (e.g. via `aws sso login`)

## Useful commands

* `npm run build`   compile typescript to js
* `npm run watch`   watch for changes and compile
* `npm run test`    perform the jest unit tests (needs `npm run build` first to not run against old code!)
* `cdk deploy`      deploy this stack to your default AWS account/region
* `cdk diff`        compare deployed stack with current state
* `cdk synth`       emits the synthesized CloudFormation template
