"""
# Copyjob from some s3 bucket path to a s3 bucket in our cdk stack

Adjusted from
https://gitlab.kreuzwerker.de/alican.kapusuz/cop-de-scoofy-alican/-/blob/master/scoofy_project/scoofy_project_stack.py

"""
import aws_cdk
from aws_cdk import (
    aws_events,
    aws_events_targets,
    aws_iam,
    aws_lambda,
    aws_s3,
    lambda_layer_awscli,
)
from constructs import Construct


class CopyS3Data(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        source_bucket_name: str,
        source_bucket_path: str,
        target_bucket: aws_s3.Bucket,
        target_bucket_path: str,
        schedule_cron_minute: str = "10",
        schedule_cron_hour: str = "*",
    ):
        """Copies the s3 data from a source s3 bucket to the target s3 bucket"""
        super().__init__(scope, id)
        self.source_bucket_name = source_bucket_name
        self.source_bucket_path = source_bucket_path
        self.target_bucket = target_bucket
        self.target_bucket_path = target_bucket_path
        self.schedule_cron_minute = schedule_cron_minute
        self.schedule_cron_hour = schedule_cron_hour

        # Synchronize raw input bucket with duplicated data bucket
        self.copy_data_lambda = aws_lambda.Function(
            self,
            id="copy-data-lambda",
            runtime=aws_lambda.Runtime.PYTHON_3_9,  # type: ignore
            code=aws_lambda.Code.from_asset(
                "lambdas/copyjob_for_s3_data",
                exclude=[
                    # Excluded to make repeatable builds in case these files get compiled by tests
                    "__pycache__",
                ],
            ),
            handler="copyjob_for_s3_data.sync_bucket_uri",
            environment={
                "SOURCE_BUCKET_URI": f"s3://{self.source_bucket_name}{self.source_bucket_path}",
                "TARGET_BUCKET_URI": f"s3://{self.target_bucket.bucket_name}{self.target_bucket_path}",
            },
            timeout=aws_cdk.Duration.minutes(15),
        )
        # For some reason, this is needed to resolve the name in the environment variable
        # https://bobbyhadz.com/blog/aws-cdk-dependson-relation
        self.copy_data_lambda.node.add_dependency(self.target_bucket)

        self.synchron_lambda_rule = aws_events.Rule(
            self,
            id="synchron-rule",
            schedule=aws_events.Schedule.cron(
                minute=f"{self.schedule_cron_minute}",
                hour=f"{self.schedule_cron_hour}",
                month="*",
                week_day="*",
                year="*",
            ),
        )
        self.synchron_lambda_rule.add_target(
            aws_events_targets.LambdaFunction(self.copy_data_lambda)
        )
        # AWS CLI will be installed under /opt/awscli/aws
        self.copy_data_lambda.add_layers(
            lambda_layer_awscli.AwsCliLayer(self, "AwsCliLayer")
        )

        self.target_bucket.grant_read_write(self.copy_data_lambda)

        self.source_bucket_arn = f"arn:aws:s3:::{self.source_bucket_name}"

        self.allow_read_access_to_source_bucket_statement = aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=[
                "s3:GetObject",
                "s3:ListBucket",
            ],
            resources=[
                self.source_bucket_arn + "/*",  # for s3:GetObject
                self.source_bucket_arn,  # for s3:ListBucket
            ],
        )

        self.copy_data_lambda.add_to_role_policy(
            self.allow_read_access_to_source_bucket_statement
        )
