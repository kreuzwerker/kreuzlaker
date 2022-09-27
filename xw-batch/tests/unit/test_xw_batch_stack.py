import json
import typing

import aws_cdk
import pytest
from aws_cdk.assertions import Capture, Match, Template

from xw_batch.users_and_groups import (
    GROUP_DATA_LAKE_ATHENA_USER,
    GROUP_DATA_LAKE_DEBUGGING,
)

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


# Helper functions for IAM


def _filter_by_resource(
    statements: typing.List[typing.Dict[str, typing.Any]],
    *,
    equal: str = None,
    contain: typing.Any = None,
    match: str = None,
    exclude: str = None,
) -> typing.Generator[typing.Dict[str, typing.Any], None, None]:
    # can only handle a single one
    assert len(["set" for x in (equal, contain, match, exclude) if x is not None]) == 1
    for statement in statements:
        resource = statement.get("Resource")
        if equal:
            if resource == equal:
                yield statement
        elif contain:
            if isinstance(resource, list):
                for r in resource:
                    if r == contain:
                        yield statement
        elif match:
            if match in json.dumps(resource):
                yield statement
        else:
            if exclude not in json.dumps(resource):
                yield statement


def _filter_actions(
    statement: typing.Dict[str, typing.Any],
    *,
    matches: typing.List[str] = None,
    excludes: typing.List[str] = None,
) -> typing.Generator[str, None, None]:
    # can't handle both
    assert len(["set" for x in (matches, excludes) if x is not None]) == 1
    actions = statement.get("Action", [])
    if matches:
        for action in actions:
            for match in matches:
                if match in action:
                    yield action
                    # Only yield once
                    break

    else:
        for action in actions:
            excluded = False
            for exclude in excludes:
                if exclude in action:
                    excluded = True
                    # No need to search further
                    break
            if not excluded:
                yield action


def _one(
    statements: typing.Generator[typing.Dict[str, typing.Any], None, None]
) -> typing.Dict[str, typing.Any]:
    stmts = list(statements)
    assert len(stmts) == 1
    return stmts[0]


def _empty(iterator: typing.Generator[typing.Any, None, None]) -> bool:
    return not list(iterator)


def _exists(iterator: typing.Generator[typing.Any, None, None]) -> bool:
    return bool(list(iterator))


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
    # Data lake, athena query results
    template.resource_count_is("AWS::S3::Bucket", 2)

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


# Athena integration
def test_athena_query_result_bucket(template: Template) -> None:
    """Check that a bucket with the specific lifecycle policy exists"""
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": [
                    {
                        "ExpirationInDays": 20,
                        "Id": "remove_query_results_after_20_days",
                        "Prefix": "users/",
                        "Status": "Enabled",
                    },
                ],
            },
        },
    )


def test_athena_user_managed_policy(template: Template, stack: XwBatchStack) -> None:
    """Test the managed policy for specific functionality and ensure that not more is given"""

    # I'm really curious is these specific chaecks have a better maintainability than writing out the
    # whole policy here and just string comparing it...

    ref_raw_bucket_arn = stack.resolve(stack.s3_raw_bucket.bucket_arn)
    ref_query_result_bucket_arn = stack.resolve(stack.s3_query_result_bucket.bucket_arn)
    ref_datalake_converted_arn = stack.resolve(
        stack.raw_converted_database.database_arn
    )
    # for some reason, this arn has the "Partition" as a Ref and so won't match when doing
    # a normal "==" comparison against whatever is in the IAM statement. Fix that..
    # resolved:  {"Fn::Join": ["",["arn:",{"Ref": "AWS::Partition"}, ":glue:", ...]]}
    # IAM:       {"Fn::Join": ["",["arn:aws:glue:", ... ]]}
    if ref_datalake_converted_arn["Fn::Join"][1][1] == {"Ref": "AWS::Partition"}:
        ref_datalake_converted_arn["Fn::Join"][1][0] = "arn:aws:glue:"
        del ref_datalake_converted_arn["Fn::Join"][1][2]
        del ref_datalake_converted_arn["Fn::Join"][1][1]

    statements_capture = Capture()
    template.has_resource_properties(
        "AWS::IAM::ManagedPolicy",
        {
            "Description": "Allow athena access to users.",
            "Path": "/",
            "PolicyDocument": {
                "Statement": statements_capture,
                "Version": "2012-10-17",
            },
        },
    )
    statements = statements_capture.as_array()

    # Athena statement
    athena_stmt = _one(_filter_by_resource(statements, equal="*"))
    # users are allowed a few list and get stuff for athena
    assert _empty(_filter_actions(athena_stmt, excludes=["athena:List", "athena:Get"]))
    # User is allowed to list all workgroups
    assert _exists(_filter_actions(athena_stmt, matches=["athena:ListWorkGroup"]))

    # users can do basically everything in the workgroup
    # -> don't care about the details, just that there is such a statement
    assert _one(_filter_by_resource(statements, match=":workgroup/all_users"))

    # Glue: again, users should only be able to work in their own database
    # this is in the same statement, but we want to catch both;
    # Could probably be split, but then the statement would have to be split...
    for resource_match in (
        ":table/user_*/*",
        ":database/user_*",
    ):
        stmt = _one(_filter_by_resource(statements, match=resource_match))
        # users are allowed to do a lot!
        assert _exists(
            _filter_actions(
                stmt,
                matches=[
                    "glue:CreateDatabase",
                    "glue:UpdateDatabase",
                    "glue:DeleteDatabase",
                ],
            )
        )
        assert _exists(
            _filter_actions(
                stmt,
                matches=[
                    "glue:CreateTable",
                    "glue:DeleteTable",
                    "glue:DeleteTable",
                ],
            )
        )
        assert _exists(
            _filter_actions(
                stmt,
                matches=[
                    "glue:CreatePartition",
                    "glue:UpdatePartition",
                    "glue:DeletePartition",
                ],
            )
        )
    glue_datalake_stmt = _one(
        _filter_by_resource(statements, contain=ref_datalake_converted_arn)
    )
    # users are NOT allowed to write
    assert _empty(
        _filter_actions(
            glue_datalake_stmt, matches=["glue:Create", "glue:Update", "glue:Delete"]
        )
    )
    # Only read
    assert _exists(_filter_actions(glue_datalake_stmt, matches=["glue:Get"]))

    # query result bucket access: users are allowed only a few things and only that
    query_result_bucket_stmt = _one(
        _filter_by_resource(statements, match="/users/user_${aws:username}/*")
    )
    assert _empty(
        _filter_actions(
            query_result_bucket_stmt, excludes=["s3:Put", "s3:Get", "s3:Abort"]
        )
    )
    assert _exists(
        _filter_actions(
            query_result_bucket_stmt, matches=["s3:Put", "s3:Get", "s3:Abort"]
        )
    )
    # List is only allowed with a condition
    query_result_bucket_stmt_list = _one(
        _filter_by_resource(statements, equal=ref_query_result_bucket_arn)
    )
    print(query_result_bucket_stmt_list)
    assert "s3:ListBucket" in query_result_bucket_stmt_list["Action"]
    assert "Condition" in query_result_bucket_stmt_list

    # raw data bucket access: only read access, but unconditionally to the whole bucket
    query_result_bucket_stmt = _one(
        _filter_by_resource(statements, contain=ref_raw_bucket_arn)
    )
    assert _empty(
        _filter_actions(query_result_bucket_stmt, excludes=["s3:List", "s3:Get"])
    )
    assert _exists(
        _filter_actions(query_result_bucket_stmt, matches=["s3:List", "s3:Get"])
    )


def test_athena_user_group(template: Template, stack: XwBatchStack) -> None:
    """Check that the group exists and has the required managed policy assigned"""

    ref_policy_arn = stack.resolve(
        stack.allow_users_athena_access_managed_policy.managed_policy_arn
    )

    template.has_resource_properties(
        "AWS::IAM::Group",
        {
            "GroupName": GROUP_DATA_LAKE_ATHENA_USER,
            "ManagedPolicyArns": Match.array_with([ref_policy_arn]),
        },
    )


def test_athena_work_group(template: Template, stack: XwBatchStack) -> None:
    """Check that a workgroup exists and has the required output location"""

    ref_bucket_name = stack.resolve(stack.s3_query_result_bucket.bucket_name)
    template.has_resource_properties(
        "AWS::Athena::WorkGroup",
        {
            "Description": "Workgroup for all users",
            "Name": "all_users",
            "WorkGroupConfiguration": {
                "ResultConfiguration": {
                    "OutputLocation": {
                        "Fn::Join": ["", ["s3://", ref_bucket_name, "/users/shared/"]],
                    },
                },
            },
        },
    )


def test_whole_stack_snapshot(snapshot, template: Template):
    assert template.to_json() == snapshot
