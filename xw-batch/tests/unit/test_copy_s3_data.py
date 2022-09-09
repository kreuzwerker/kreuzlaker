from unittest.mock import MagicMock

import aws_cdk
import pytest
from aws_cdk import aws_s3
from aws_cdk.assertions import Match, Template

import lambdas.copyjob_for_s3_data.copyjob_for_s3_data

# In InteliJ, you have to mark the xw_batch folder as "source folder"
from xw_batch.copy_s3_data import CopyS3Data


class _S3CopyStack(aws_cdk.Stack):
    def __init__(self):
        super().__init__()
        self.bucket = aws_s3.Bucket(self, id="test-bucket", bucket_name="target-test")
        self.copy_job = CopyS3Data(
            self,
            "s3-copy-job",
            source_bucket_path="/source-path",
            source_bucket_name="source-bucket",
            target_bucket=self.bucket,
            target_bucket_path="/target-path",
        )


@pytest.fixture(name="stack", scope="module")
def stack_fixture() -> _S3CopyStack:
    stack = _S3CopyStack()
    return stack


@pytest.fixture(name="template", scope="module")
def template_fixture(stack: _S3CopyStack) -> Template:
    template = Template.from_stack(stack)
    return template


def test_cron_lambda_created(template: Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        props={
            "Handler": "copyjob_for_s3_data.sync_bucket_uri",
            "Runtime": "python3.9",
        },
    )

    # Needs to have:
    # - Lambda
    #   - with an aws cli layer
    #   - with access to the source and target bucket
    #   - A role to be assumed
    # - synchron-rule to copy the stuff every hour


def test_copy_job_has_role_defined(
    template: Template,
    stack: _S3CopyStack,
):
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": [
                    {
                        "Action": "sts:AssumeRole",
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                    }
                ],
                "Version": "2012-10-17",
            },
            "ManagedPolicyArns": [
                {
                    "Fn::Join": [
                        "",
                        [
                            "arn:",
                            {"Ref": "AWS::Partition"},
                            ":iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                        ],
                    ]
                }
            ],
        },
    )


def test_copy_job_lambda_has_access_to_target_bucket(
    template: Template,
    stack: _S3CopyStack,
):
    resolved_target_bucket_arn = stack.resolve(stack.bucket.bucket_arn)
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "PolicyDocument": {
                "Statement": [
                    {
                        "Action": [
                            "s3:GetObject*",
                            "s3:GetBucket*",
                            "s3:List*",
                            "s3:DeleteObject*",
                            "s3:PutObject",
                            "s3:PutObjectLegalHold",
                            "s3:PutObjectRetention",
                            "s3:PutObjectTagging",
                            "s3:PutObjectVersionTagging",
                            "s3:Abort*",
                        ],
                        "Effect": "Allow",
                        "Resource": [
                            resolved_target_bucket_arn,
                            {
                                "Fn::Join": [
                                    "",
                                    [
                                        resolved_target_bucket_arn,
                                        "/*",
                                    ],
                                ]
                            },
                        ],
                    },
                    {
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Effect": "Allow",
                        "Resource": [
                            "arn:aws:s3:::source-bucket/*",
                            "arn:aws:s3:::source-bucket",
                        ],
                    },
                ],
                "Version": "2012-10-17",
            },
        },
    )


def test_copy_job_lambda_sets_env_variables(
    template: Template,
    stack: _S3CopyStack,
):
    resolved_target_bucket_name = stack.resolve(stack.bucket.bucket_name)
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "Environment": {
                "Variables": {
                    "SOURCE_BUCKET_URI": "s3://source-bucket/source-path",
                    "TARGET_BUCKET_URI": {
                        "Fn::Join": [
                            "",
                            ["s3://", resolved_target_bucket_name, "/target-path"],
                        ]
                    },
                }
            },
        },
    )


def test_copy_job_lambda_has_aws_cli(
    template: Template,
):
    # access to the aws cli
    template.has_resource_properties(
        "AWS::Lambda::LayerVersion",
        {
            "Content": {
                "S3Bucket": {
                    "Fn::Sub": Match.string_like_regexp(
                        r"\${AWS::AccountId}-\${AWS::Region}"
                    )
                },
                "S3Key": Match.string_like_regexp(r".*\.zip"),
            },
            "Description": "/opt/awscli/aws",
        },
    )


def test_copy_job_sync_rule(
    template: Template,
    stack: _S3CopyStack,
):
    resolved_lambda_arn = stack.resolve(stack.copy_job.copy_data_lambda.function_arn)
    resolved_sync_rule_arn = stack.resolve(stack.copy_job.synchron_lambda_rule.rule_arn)

    # rule
    template.has_resource_properties(
        "AWS::Events::Rule",
        {
            "ScheduleExpression": "cron(10 * ? * * *)",
            "State": "ENABLED",
            "Targets": [
                {
                    "Arn": resolved_lambda_arn,
                    "Id": "Target0",
                }
            ],
        },
    )

    # permission to invoke the lambda
    template.has_resource_properties(
        "AWS::Lambda::Permission",
        {
            "Action": "lambda:InvokeFunction",
            "FunctionName": resolved_lambda_arn,
            "Principal": "events.amazonaws.com",
            "SourceArn": resolved_sync_rule_arn,
        },
    )


def test_copy_s3_data_lambda(monkeypatch):
    #     sync_command = f"/opt/awscli/aws s3 sync {source_bucket_uri} {target_bucket_uri}"
    #     subprocess.check_call(sync_command, shell=True)

    monkeypatch.setenv("SOURCE_BUCKET_URI", "s3://source/a")
    monkeypatch.setenv("TARGET_BUCKET_URI", "s3://target/b")

    fake_check_call = MagicMock()
    monkeypatch.setattr(
        lambdas.copyjob_for_s3_data.copyjob_for_s3_data.subprocess,
        "check_call",
        fake_check_call,
    )
    ret = lambdas.copyjob_for_s3_data.copyjob_for_s3_data.sync_bucket_uri({}, {})

    fake_check_call.assert_called_with(
        "/opt/awscli/aws s3 sync s3://source/a s3://target/b", shell=True
    )
    assert ret == {
        "statusCode": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": "Successfully ran aws s3 sync s3://source/a s3://target/b\n",
    }


def test_copy_s3_data_lambda_without_env(monkeypatch):
    #     sync_command = f"/opt/awscli/aws s3 sync {source_bucket_uri} {target_bucket_uri}"
    #     subprocess.check_call(sync_command, shell=True)

    fake_check_call = MagicMock()
    monkeypatch.setattr(
        lambdas.copyjob_for_s3_data.copyjob_for_s3_data.subprocess,
        "check_call",
        fake_check_call,
    )
    # Not checking for the full name as we do not care which one comes first and raises
    with pytest.raises(KeyError, match="BUCKET_URI"):
        lambdas.copyjob_for_s3_data.copyjob_for_s3_data.sync_bucket_uri({}, {})

    fake_check_call.assert_not_called()


def test_copy_s3_data_snapshot(snapshot, template: Template):
    assert template.to_json() == snapshot
