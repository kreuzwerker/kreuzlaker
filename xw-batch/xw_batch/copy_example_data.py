"""
# Copyjob for example data

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


def add_copy_scoofy_example_data(
    stack: aws_cdk.Stack, raw_data_bucket: aws_s3.Bucket
) -> str:
    """Copies the scoofy example data to the bucket under /raw/scoofy/journeys/"""
    cron_minute = 10
    cron_hour = "*"
    input_bucket = "xw-d13g-scoofy-data-inputs"
    input_bucket_path = "/data/journeys"
    output_bucket_path = "/raw/scoofy/journeys/"

    # Synchronize raw input bucket with duplicated data bucket
    copy_scoofy_example_data_lambda = aws_lambda.Function(
        stack,
        id="copy-scoofy-example-data",
        runtime=aws_lambda.Runtime.PYTHON_3_9,  # type: ignore
        code=aws_lambda.Code.from_asset("lambda/copyjob_for_example_data"),
        handler="copyjob_for_example_data.sync_bucket_uri",
        environment={
            "INPUT_BUCKET_URI": f"s3://{input_bucket}{input_bucket_path}",
            "OUTPUT_BUCKET_URI": f"s3://{raw_data_bucket.bucket_name}{output_bucket_path}",
        },
        timeout=aws_cdk.Duration.minutes(15),
    )

    synchron_lambda_rule = aws_events.Rule(
        stack,
        id="synchron-rule",
        schedule=aws_events.Schedule.cron(
            minute=f"{cron_minute}",
            hour=f"{cron_hour}",
            month="*",
            week_day="*",
            year="*",
        ),
    )
    synchron_lambda_rule.add_target(
        aws_events_targets.LambdaFunction(copy_scoofy_example_data_lambda)
    )
    # AWS CLI will be installed under /opt/awscli/aws
    copy_scoofy_example_data_lambda.add_layers(
        lambda_layer_awscli.AwsCliLayer(stack, "AwsCliLayer")
    )

    raw_data_bucket.grant_read_write(copy_scoofy_example_data_lambda)

    scoofy_example_data_bucket_arn = f"arn:aws:s3:::{input_bucket}"

    allow_read_access_to_scoofy_statement = aws_iam.PolicyStatement(
        effect=aws_iam.Effect.ALLOW,
        actions=[
            "s3:GetObject",
            "s3:ListBucket",
        ],
        resources=[
            scoofy_example_data_bucket_arn + "/*",  # for s3:GetObject
            scoofy_example_data_bucket_arn,  # for s3:ListBucket
        ],
    )

    copy_scoofy_example_data_lambda.add_to_role_policy(
        allow_read_access_to_scoofy_statement
    )

    return output_bucket_path
