#!/usr/bin/env python3
import os

import aws_cdk as cdk
import constructs

from xw_batch.users_and_groups import add_users_on_dev, add_users_on_prod
from xw_batch.xw_batch_stack import XwBatchStack


class XwDataStage(cdk.Stage):
    def __init__(
        self,
        scope: constructs.Construct,
        id: str,
        env: cdk.Environment,
        outdir: str = None,
        keep_data_resources_on_destroy: bool = True,
    ):
        """A stage or environment where one or multiple stacks should be created in"""
        super().__init__(scope, id, env=env, outdir=outdir)
        self.batch_stack = XwBatchStack(
            self,
            "XwBatchStack",
            env=env,
            keep_data_resources_on_destroy=keep_data_resources_on_destroy,
        )


app = cdk.App()

prod_stage = XwDataStage(
    app,
    "prod",
    # For more information on the env argument: https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    # TODO: add the correct values here, #677474147593 is Jan Katins Sandbox
    env=cdk.Environment(account="677474147593", region="eu-central-1"),
    keep_data_resources_on_destroy=True,
)
add_users_on_prod(prod_stage.batch_stack.users_and_groups)

dev_stage = XwDataStage(
    app,
    "dev",
    # the env variables are set by the cdk script and are taken from what is configured in
    # your currently active aws profile
    # For more information on the env argument: https://docs.aws.amazon.com/cdk/latest/guide/environments.html
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION")
    ),
    keep_data_resources_on_destroy=False,
)
add_users_on_dev(dev_stage.batch_stack.users_and_groups)

app.synth()
