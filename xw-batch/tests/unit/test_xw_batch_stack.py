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

    template.has_resource(
        "AWS::S3::Bucket",
        {
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
        },
    )
