import json

import aws_cdk
import pytest
from aws_cdk.assertions import Capture, Match, Template

from xw_batch.users_and_groups import GROUP_DATA_LAKE_DEBUGGING

# In InteliJ, you have to mark the xw_batch folder as "source folder"
from xw_batch.xw_batch_stack import XwBatchStack


@pytest.fixture(name="stack", scope="module")
def stack_fixture() -> XwBatchStack:
    app = aws_cdk.App()
    stack = XwBatchStack(app, "xw-batch")
    return stack


@pytest.fixture(name="template", scope="module")
def template_fixture(stack: XwBatchStack) -> Template:
    template = Template.from_stack(stack)
    return template


def test_example_data_created(stack: XwBatchStack):
    # We test the s3 data copy job elsewhere, just make sure we have created one here with the right config
    assert stack.scoofy_example_data
    assert stack.scoofy_example_data.source_bucket_name == "xw-d13g-scoofy-data-inputs"
    assert stack.scoofy_example_data.source_bucket_path == "/data/journeys"
    assert stack.scoofy_example_data.target_bucket_path == "/raw/scoofy/journeys/"
    assert stack.scoofy_example_data.target_bucket == stack.s3_raw_bucket


def test_cloudwatch_access_for_debugging_user(
    template: Template, stack: XwBatchStack
) -> None:
    template.has_resource_properties(
        "AWS::IAM::Group",
        {
            "GroupName": GROUP_DATA_LAKE_DEBUGGING,
            # we need array_with to not fail if we would add more than one policy
            "ManagedPolicyArns": Match.array_with(
                [
                    {
                        "Fn::Join": [
                            "",
                            [
                                "arn:",
                                {"Ref": "AWS::Partition"},
                                ":iam::aws:policy/CloudWatchReadOnlyAccess",
                            ],
                        ]
                    }
                ]
            ),
        },
    )


def test_raw_data_s3_bucket_created(template: Template):
    # this will fail when we add more buckets
    # TODO: find a better way to test for the existence of the exact amount of buckets...
    template.resource_count_is("AWS::S3::Bucket", 1)

    # This checks the default removal policy if not explicitly set
    template.has_resource(
        "AWS::S3::Bucket",
        {
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
        },
    )


def test_glue_database_converted(template: Template):
    # This checks the default removal policy if not explicitly set
    template.has_resource_properties(
        "AWS::Glue::Database",
        {
            "CatalogId": {"Ref": "AWS::AccountId"},
            "DatabaseInput": {"Name": "data_lake_converted"},
        },
    )


def test_glue_raw_crawler_scoofy_example_data(template: Template):
    # This checks the default removal policy if not explicitly set
    targets = Capture()
    template.has_resource_properties(
        "AWS::Glue::Crawler",
        {
            "Targets": targets,
            "DatabaseName": "data_lake_raw",
        },
    )
    assert "/raw/scoofy/journeys/" in json.dumps(targets.as_object())


def test_glue_convert_job_for_scoofy_example_data(
    template: Template,
    stack: XwBatchStack,
):
    # This checks the default removal policy if not explicitly set
    print(template.to_json())
    resolved_raw_bucket_name = stack.resolve(stack.s3_raw_bucket.bucket_name)
    resolved_convert_glue_role_arn = stack.resolve(stack.glue_converted_role.role_arn)
    script_location = Capture()
    extra_py_files = Capture()
    template.has_resource_properties(
        "AWS::Glue::Job",
        {
            "Command": {
                "Name": "glueetl",
                "PythonVersion": "3",
                # The filename is getting mangled, not nice, but works with multiple versions...
                "ScriptLocation": script_location,
            },
            "Role": resolved_convert_glue_role_arn,
            "DefaultArguments": {
                "--job-language": "python",
                "--extra-py-files": extra_py_files,
                "--job-bookmark-option": "job-bookmark-enable",
                "--SOURCE_BUCKET_URI": {
                    "Fn::Join": [
                        "",
                        [
                            "s3://",
                            resolved_raw_bucket_name,
                            "/raw/scoofy/journeys/",
                        ],
                    ],
                },
                "--SOURCE_COMPRESSION_TYPE": "gzip",
                "--SOURCE_FORMAT": "json",
                "--SOURCE_PARTITION_VAR": "start_dt",
                "--TARGET_BUCKET_URI": {
                    "Fn::Join": [
                        "",
                        [
                            "s3://",
                            resolved_raw_bucket_name,
                            "/converted/journeys",
                        ],
                    ]
                },
                "--TARGET_DB_NAME": "data_lake_converted",
                "--TARGET_TABLE_NAME": "journeys",
                "--TARGET_COMPRESSION_TYPE": "snappy",
                "--TARGET_FORMAT": "glueparquet",
            },
            "Description": Match.string_like_regexp("_created_at"),
            "GlueVersion": "3.0",
            "MaxRetries": 1,
            "NumberOfWorkers": 2,
            "WorkerType": "G.1X",
        },
    )
    assert ".py" in json.dumps(script_location.as_object())
    assert ".zip" in json.dumps(extra_py_files.as_object())


@pytest.mark.parametrize(
    "keep_data_resources_on_destroy, expected_policy, match_tags",
    [
        (True, "Retain", False),
        (False, "Delete", True),
    ],
)
def test_all_s3_buckets_honour_stack_removal_policy(
    keep_data_resources_on_destroy: bool, expected_policy: str, match_tags: bool
):
    app = aws_cdk.App()
    stack = XwBatchStack(
        app, "xw-batch", keep_data_resources_on_destroy=keep_data_resources_on_destroy
    )
    template = Template.from_stack(stack)

    for name, resource in template.find_resources(type="AWS::S3::Bucket").items():
        print(resource)
        assert resource["DeletionPolicy"] == expected_policy
        assert resource["UpdateReplacePolicy"] == expected_policy
        if match_tags:
            assert {"Key": "aws-cdk:auto-delete-objects", "Value": "true"} in resource[
                "Properties"
            ]["Tags"]


def _join_arn_ref(arn_ref: dict, add_on: str):
    return {"Fn::Join": ["", [arn_ref, add_on]]}


def test_raw_data_s3_bucket_access_for_debugging_user(
    template: Template, stack: XwBatchStack
) -> None:
    # stack.resolve() returns CF references to items by name or arn (maybe more?)
    # The api doc is ... unhelpful: https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.Stack.html#resolveobj
    ref_group_name = stack.resolve(
        stack.users_and_groups.get_group(GROUP_DATA_LAKE_DEBUGGING).group_name
    )
    ref_bucket_arn = stack.resolve(stack.s3_raw_bucket.bucket_arn)
    wanted_bucket_resources = [
        # The bucket itself
        ref_bucket_arn,
        # The items in the bucket
        _join_arn_ref(ref_bucket_arn, "/*"),
    ]
    template.has_resource_properties(
        "AWS::IAM::Policy",
        {
            "Groups": Match.array_with([ref_group_name]),
            "PolicyDocument": {
                "Statement": [
                    {
                        "Action": [
                            "s3:GetObject*",
                            "s3:GetBucket*",
                            "s3:List*",
                        ],
                        "Effect": "Allow",
                        "Resource": Match.array_with(wanted_bucket_resources),
                    },
                ],
                "Version": "2012-10-17",
            },
        },
    )


def test_whole_stack_snapshot(snapshot, template: Template):
    assert template.to_json() == snapshot
