import aws_cdk
from aws_cdk import aws_glue, aws_iam, aws_s3
from constructs import Construct

from .copy_example_data import add_copy_scoofy_example_data
from .users_and_groups import (
    GROUP_DATA_LAKE_DEBUGGING,
    OrgUsersAndGroups,
    create_org_groups,
)


class XwBatchStack(aws_cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        keep_data_resources_on_destroy: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack_removal_policy = (
            aws_cdk.RemovalPolicy.RETAIN
            if keep_data_resources_on_destroy
            else aws_cdk.RemovalPolicy.DESTROY
        )
        # the argument can only be non-None when we DESTROY the bucket
        stack_auto_delete_objects_in_s3 = (
            None if keep_data_resources_on_destroy else True
        )

        # s3 bucket for raw data
        self.s3_raw_bucket = aws_s3.Bucket(
            self,
            id="xw_batch_bucket_raw",
            # TODO: define a name in some config
            # bucket_name="xw-batch-bucket-raw-" + os.environ("ENVIRONMENT_NAME"),
            removal_policy=stack_removal_policy,
            auto_delete_objects=stack_auto_delete_objects_in_s3,
        )

        # Add stuff for some example data
        example_data_location = add_copy_scoofy_example_data(self, self.s3_raw_bucket)

        self.users_and_groups: OrgUsersAndGroups = create_org_groups(self)

        # Idea:
        # 1. "something" puts data into <bucket>/raw/source/table, crawler (per table) discovers it via cron
        # 2. glue job (with manual script) to convert to parquet + add it as a table into another glue database, but
        #    still the same s3 bucket: <bucket>/converted/table

        raw_data_tables = [example_data_location]
        # only [a-z0-9_]{1,255}, everything else beaks athena later on
        # https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices.html#schema-crawlers-schedule
        raw_data_base_name = "data_lake_raw"
        raw_glue_iam_role_name = "s3-raw-access-glue"

        role = aws_iam.Role(
            self,
            id=raw_glue_iam_role_name,
            assumed_by=aws_iam.ServicePrincipal("glue.amazonaws.com"),
        )
        gluePolicy = aws_iam.ManagedPolicy.from_aws_managed_policy_name(
            "service-role/AWSGlueServiceRole"
        )
        role.add_managed_policy(gluePolicy)
        self.s3_raw_bucket.grant_read_write(role)

        self.s3_raw_bucket.grant_read(
            self.users_and_groups.get_group(GROUP_DATA_LAKE_DEBUGGING)
        )

        for table_path in raw_data_tables:
            table_id = table_path.replace("/", "-")
            # glue crawlers for the raw data
            crawler_name = f"rawcrawler-{table_id}"
            aws_glue.CfnCrawler(
                self,
                id=crawler_name,
                name=crawler_name,
                role=role.role_arn,
                database_name=raw_data_base_name,
                targets=aws_glue.CfnCrawler.TargetsProperty(
                    s3_targets=[
                        aws_glue.CfnCrawler.S3TargetProperty(
                            path=f"s3://{self.s3_raw_bucket.bucket_name}{table_path}"
                        )
                    ]
                ),
            )

            crawler_trigger_name = f"trigger-rawcrawler-{table_id}"

            # TODO: use event based triggers
            # This minute is adjusted from the minute used in the copy example data job, which uses cron_minute = 10
            self.cron_minute = 15
            self.cron_hour = "*"
            aws_glue.CfnTrigger(
                self,
                crawler_trigger_name,
                schedule=f"cron({self.cron_minute} {self.cron_hour} * * ? *)",
                type="SCHEDULED",
                actions=[aws_glue.CfnTrigger.ActionProperty(crawler_name=crawler_name)],
                start_on_creation=True,
            )

            # TODO: glue job to convert the table to parquet

        # Give a debugging group access to the logs
        # TODO: maybe restrict to glue logs? But if we get rif of the crawler, there are no logs,
        #       so lets keep it broad for now
        cloudwatch_read_only_policy = (
            aws_iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchReadOnlyAccess"
            )
        )
        self.users_and_groups.get_group(GROUP_DATA_LAKE_DEBUGGING).add_managed_policy(
            cloudwatch_read_only_policy
        )
