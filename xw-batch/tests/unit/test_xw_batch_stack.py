import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

# In InteliJ, you have to mark the xw_batch folder as "source folder"
from xw_batch.xw_batch_stack import XwBatchStack


@pytest.fixture(name="stack", scope="module")
def stack_fixture() -> XwBatchStack:
    app = core.App()
    stack = XwBatchStack(app, "xw-batch")
    return stack


@pytest.fixture(name="template", scope="module")
def template_fixture(stack: XwBatchStack) -> assertions.Template:
    template = assertions.Template.from_stack(stack)
    return template


def test_cron_lambda_created(template: assertions.Template):
    template.has_resource_properties(
        "AWS::Lambda::Function",
        props={
            "Handler": "copyjob_for_example_data.sync_bucket_uri",
            "Runtime": "python3.9",
        },
    )


def test_raw_data_s3_bucket_created(template: assertions.Template):
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
    app = core.App()
    stack = XwBatchStack(
        app, "xw-batch", keep_data_resources_on_destroy=keep_data_resources_on_destroy
    )
    template = assertions.Template.from_stack(stack)

    for name, resource in template.find_resources(type="AWS::S3::Bucket").items():
        print(resource)
        assert resource["DeletionPolicy"] == expected_policy
        assert resource["UpdateReplacePolicy"] == expected_policy
        if match_tags:
            assert {"Key": "aws-cdk:auto-delete-objects", "Value": "true"} in resource[
                "Properties"
            ]["Tags"]
