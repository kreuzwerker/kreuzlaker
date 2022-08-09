import aws_cdk
from aws_cdk import (
    aws_s3,
)

from constructs import Construct

from .copy_example_data import add_copy_scoofy_example_data


class XwBatchStack(aws_cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # s3 bucket for raw data
        self.s3_raw_bucket = aws_s3.Bucket(
            self,
            id="xw_batch_bucket_raw",
            # TODO: define a name in some config
            # bucket_name="xw-batch-bucket-raw-" + os.environ("ENVIRONMENT_NAME"),
        )

        # Add stuff for some example data
        example_data_location = add_copy_scoofy_example_data(self, self.s3_raw_bucket)
