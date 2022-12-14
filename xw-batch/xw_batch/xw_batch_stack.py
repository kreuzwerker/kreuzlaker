import dataclasses

import aws_cdk
from aws_cdk import aws_applicationautoscaling, aws_athena
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr, aws_ecs, aws_ecs_patterns, aws_glue
from aws_cdk import aws_glue_alpha as glue
from aws_cdk import aws_iam, aws_s3, aws_s3_assets
from constructs import Construct

from .copy_s3_data import CopyS3Data
from .users_and_groups import (
    GROUP_DATA_LAKE_ATHENA_USER,
    GROUP_DATA_LAKE_DEBUGGING,
    OrgUsersAndGroups,
    create_org_groups,
)
from .vpc import XwVpc


class XwBatchStack(aws_cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        force_delete_flag: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        region = aws_cdk.Stack.of(self).region
        account = aws_cdk.Stack.of(self).account
        vpc = XwVpc(self, "XwBatchVpc").get_vpc()

        stack_removal_policy = aws_cdk.RemovalPolicy.DESTROY if force_delete_flag else aws_cdk.RemovalPolicy.RETAIN
        # the argument can only be non-None when we DESTROY the bucket
        stack_auto_delete_objects_in_s3 = True if force_delete_flag else None

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
        self.scoofy_example_data = CopyS3Data(
            self,
            id="copy-scoofy-example-data",
            source_bucket_name="xw-d13g-scoofy-data-inputs",
            source_bucket_path="/data/journeys",
            target_bucket=self.s3_raw_bucket,
            target_bucket_path="/raw/scoofy/journeys/",
        )

        self.users_and_groups: OrgUsersAndGroups = create_org_groups(self)

        # Idea:
        # 1. "something" puts (non-parquet) data into <bucket>/raw/source/table. There is an optional crawler defined,
        #     which has to be manually triggered (to not incur costs)
        # 2. glue job (with some table specific config) to convert to parquet for new files (via bookmarks) and
        #    add it as a table into another glue database into the same bucekt under <bucket>/converted/table

        # Easier handling of the table config
        _s3_raw_bucket = self.s3_raw_bucket

        @dataclasses.dataclass()
        class RawTableConfig:
            raw_table_path: str
            converted_table_name: str
            raw_table_id: str = dataclasses.field(init=False)
            converted_table_id: str = dataclasses.field(init=False)
            raw_bucket_uri: str = dataclasses.field(init=False)
            converted_bucket_uri: str = dataclasses.field(init=False)

            def __post_init__(self):
                self.raw_table_id = self.raw_table_path.replace("/", "-")
                self.converted_table_id = self.converted_table_name.replace("/", "-")
                self.raw_bucket_uri = f"s3://{_s3_raw_bucket.bucket_name}{self.raw_table_path}"
                self.converted_bucket_uri = f"s3://{_s3_raw_bucket.bucket_name}/converted/{self.converted_table_name}"

        raw_table_configs = [
            # converted_table_name needs a transform() in glue/business_logic/convert/<converted_table_name>.py
            RawTableConfig(self.scoofy_example_data.target_bucket_path, "journeys")
        ]
        # only [a-z0-9_]{1,255}, everything else beaks athena later on
        # https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices.html#schema-crawlers-schedule
        raw_data_base_name = "data_lake_raw"
        raw_glue_iam_role_name = "s3-raw-access-glue"
        raw_converted_database_name = "data_lake_converted"
        raw_converted_glue_iam_role_name = "s3-raw-converted-access-glue"

        role = aws_iam.Role(
            self,
            id=raw_glue_iam_role_name,
            assumed_by=aws_iam.ServicePrincipal("glue.amazonaws.com"),
        )
        glue_policy = aws_iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
        role.add_managed_policy(glue_policy)
        self.s3_raw_bucket.grant_read_write(role)

        # For debugging failing glue jobs and so on
        self.s3_raw_bucket.grant_read(self.users_and_groups.get_group(GROUP_DATA_LAKE_DEBUGGING))

        # add Glue role to convert the data to parquet
        self.glue_converted_role = aws_iam.Role(
            self,
            id=raw_converted_glue_iam_role_name,
            assumed_by=aws_iam.ServicePrincipal("glue.amazonaws.com"),
        )
        glue_policy_transformed = aws_iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
        self.glue_converted_role.add_managed_policy(glue_policy_transformed)
        self.s3_raw_bucket.grant_read_write(self.glue_converted_role)

        # https://constructs.dev/packages/@aws-cdk/aws-glue-alpha/
        # create database for transformed data
        self.raw_converted_database = glue.Database(
            self,
            id=raw_converted_database_name,
            database_name=raw_converted_database_name,
        )

        # Directly using Code.from_asset doesn't work, because it expects a single file. So we add a normal asset and
        # then pass that in as a Code.from_bucket()... -> should get resolved when the following issue is done
        # https://github.com/aws/aws-cdk/issues/21951
        # glue_additional_python_files = glue.Code.from_asset("glue/business_logic/")
        _glue_additional_python_files_asset = aws_s3_assets.Asset(
            self,
            "glue_additional_python_files",
            # If you add a dir, it's zipped, but without the dir as a path element :-/ So we have to zip the content
            # of the glue folder to get the business_logic part...
            path="glue/",
            # We only want the business_logic folder in the zip, but the first __init__.py also excludes that file
            # in all subfolders, so we need "!<folder>/**" to include all files in that subfolder again
            # For more on this magic: https://github.com/aws/aws-cdk/issues/9146
            exclude=[
                "__init__.py",
                "scripts",
                "!business_logic/**",
                # Excluded to make repeatable builds in case these files get compiled by tests
                "__pycache__",
            ],
        )
        glue_additional_python_files = glue.Code.from_bucket(
            bucket=_glue_additional_python_files_asset.bucket,
            key=_glue_additional_python_files_asset.s3_object_key,
        )

        for table_config in raw_table_configs:
            # Add a *MANUAL* crawler so that one could add these as tables to a raw database.
            # Hourly crawling costs quite a lot of money for no gain as the schema never changes
            # and all files are in the same prefix, so no additional partitions are added.
            crawler_name = f"rawcrawler-{table_config.raw_table_id}"

            aws_glue.CfnCrawler(
                self,
                id=crawler_name,
                name=crawler_name,
                role=role.role_arn,
                database_name=raw_data_base_name,
                targets=aws_glue.CfnCrawler.TargetsProperty(
                    s3_targets=[aws_glue.CfnCrawler.S3TargetProperty(path=table_config.raw_bucket_uri)]
                ),
            )

            # define parquet transformation job
            glue.Job(
                self,
                id=f"convert_to_parquet_{table_config.converted_table_id}",
                description=(
                    "Converts raw data to snappy-compressed parquet files partitioned on _created_at and "
                    + f"adds it as a new table into the '{raw_converted_database_name}' database "
                ),
                role=self.glue_converted_role,
                executable=glue.JobExecutable.python_etl(
                    glue_version=glue.GlueVersion.V3_0,  # type: ignore
                    python_version=glue.PythonVersion.THREE,
                    # Be aware that Code renames all files to the hash, so don't expect nice names in the s3 bucket...
                    # https://github.com/aws/aws-cdk/issues/20481
                    script=glue.Code.from_asset("glue/scripts/convert_to_parquet.py"),
                    extra_python_files=[glue_additional_python_files],
                ),
                max_retries=1,
                # Min is 2...
                worker_count=2,
                worker_type=glue.WorkerType.G_1_X,  # type: ignore
                continuous_logging={"enabled": True},
                default_arguments={
                    # bookmarks seems to have not yet any nice flags :-(
                    # https://github.com/aws/aws-cdk/issues/21954
                    "--job-bookmark-option": "job-bookmark-enable",
                    "--SOURCE_BUCKET_URI": table_config.raw_bucket_uri,
                    "--SOURCE_COMPRESSION_TYPE": "gzip",
                    "--SOURCE_FORMAT": "json",
                    "--SOURCE_PARTITION_VAR": "start_dt",
                    "--TARGET_BUCKET_URI": table_config.converted_bucket_uri,
                    "--TARGET_DB_NAME": raw_converted_database_name,
                    "--TARGET_TABLE_NAME": table_config.converted_table_name,
                    "--TARGET_COMPRESSION_TYPE": "snappy",
                    "--TARGET_FORMAT": "glueparquet",
                },
            )

        # Give a debugging group access to the logs
        # TODO: maybe restrict to glue logs? But if we get rif of the crawler, there are no logs,
        #       so lets keep it broad for now
        cloudwatch_read_only_policy = aws_iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchReadOnlyAccess")
        self.users_and_groups.get_group(GROUP_DATA_LAKE_DEBUGGING).add_managed_policy(cloudwatch_read_only_policy)

        # Athena
        # The idea: we have one single bucket for all athena query results, so also transformed data on "prod" which
        # should be available company-wide.
        # We give different accounts (prod vs individual users in groups) separate read/write access to the glue
        # database and s3. As a first step, we give read to the whole "data lake" part (so converted data) and
        # read/write to user specific glue databases and s3 portions

        # TODO: integrate lake formation...
        #      See https://github.com/aws-samples/data-lake-as-code/blob/mainline/lib/constructs/data-lake-enrollment.ts

        self.s3_query_result_bucket = aws_s3.Bucket(
            self,
            id="xw_batch_bucket_athena_query_results",
            # AthenaFullAccess has only access to buckets named aws-athena-query-results-*, but that bucket might
            # already exist and so would need special casing in cdk/here.
            # So lets go with a default generated name for now and not set one here
            # bucket_name=f"aws-athena-query-results-{region}-{account}",
            removal_policy=stack_removal_policy,
            auto_delete_objects=stack_auto_delete_objects_in_s3,
        )

        aws_cdk.CfnOutput(
            self,
            "out-xw_batch_bucket_athena_query_results_bucket_name",
            value=self.s3_query_result_bucket.bucket_name,
        )

        # Individual Users

        # For users, we throw everything away after 20 days to save space
        self.s3_query_result_bucket.add_lifecycle_rule(
            id="remove_query_results_after_20_days",
            enabled=True,
            expiration=aws_cdk.Duration.days(20),
            prefix="users/",
        )

        # The workgroup for all users
        # NOTE: the workgroup has to be switched manually by the user (primary is default)...
        #       There is a solution to switch this group to primary during deployment, but it involves adding
        #       a custom lambda which is triggered during deployment...
        #       https://github.com/aws-samples/data-lake-as-code/blob/mainline/lib/stacks/datalake-stack.ts#L117-L169
        self.athena_user_workgroup = aws_athena.CfnWorkGroup(
            self,
            id="athena_user_workgroup",
            name="all_users",
            description="Workgroup for all users",
            work_group_configuration={
                # Otherwise one cannot overwrite the output location
                "enforceWorkGroupConfiguration": False,
                "resultConfiguration": {
                    "encryptionConfiguration": {
                        "encryptionOption": "SSE_S3",
                    },
                    # I haven't found a way to use per user locations: it's either one workgroup
                    # per user or a shared location...
                    "outputLocation": f"s3://{self.s3_query_result_bucket.bucket_name}/users/shared/",
                },
            },
            recursive_delete_option=force_delete_flag,
        )

        aws_cdk.CfnOutput(
            self,
            "out-athena_user_workgroup",
            value=self.athena_user_workgroup.name,
        )

        self.allow_users_athena_access_policy_document = create_policy_document_for_athena_principal(
            account=account,
            region=region,
            workgroup=self.athena_user_workgroup,
            # can't use ${aws:username} here as that might contain a dot!
            allowed_glue_database_names="user_*",
            query_result_bucket=self.s3_query_result_bucket,
            # No slash at the beginning or end!
            query_result_bucket_userspecific_s3_prefix="users/user_${aws:username}",
            raw_converted_database=self.raw_converted_database,
            raw_bucket=self.s3_raw_bucket,
        )
        self.allow_users_athena_access_managed_policy = aws_iam.ManagedPolicy(
            self,
            "allow_users_athena_access_managed_policy",
            document=self.allow_users_athena_access_policy_document,
            # Do not set to not have problems when deploying any changes to the policy. See best practises for cdk
            # managed_policy_name="AllowAthenaAccessToUsers",
            description="Allow athena access to users.",
        )
        self.users_and_groups.get_group(GROUP_DATA_LAKE_ATHENA_USER).add_managed_policy(
            self.allow_users_athena_access_managed_policy
        )
        self.allow_manage_own_access_keys_policy_document = aws_iam.PolicyDocument(
            statements=[
                aws_iam.PolicyStatement.from_json(
                    {
                        "Sid": "ManageOwnAccessKeys",
                        "Effect": "Allow",
                        "Action": [
                            "iam:CreateAccessKey",
                            "iam:DeleteAccessKey",
                            "iam:GetAccessKeyLastUsed",
                            "iam:GetUser",
                            "iam:ListAccessKeys",
                            "iam:UpdateAccessKey",
                        ],
                        "Resource": "arn:aws:iam::*:user/${aws:username}",
                    }
                )
            ]
        )
        self.allow_manage_own_access_keys_managed_policy = aws_iam.ManagedPolicy(
            self,
            "allow_manage_own_access_keys",
            document=self.allow_manage_own_access_keys_policy_document,
            # Do not set to not have problems when deploying any changes to the policy. See best practises for cdk
            # managed_policy_name="AllowManageOwnAccessKeys",
            description="Allow users to create and update their own access keys.",
        )
        self.users_and_groups.get_group(GROUP_DATA_LAKE_ATHENA_USER).add_managed_policy(
            self.allow_manage_own_access_keys_managed_policy
        )

        # Setup for dbt prod

        self.dbt_run_repository = aws_ecr.Repository(
            self,
            "dbt-run-repository",
            repository_name="dbt-run",
            image_scan_on_push=True,
            image_tag_mutability=aws_ecr.TagMutability.MUTABLE,
            lifecycle_rules=[aws_ecr.LifecycleRule(description="Only keep the last 5 images", max_image_count=5)],
            removal_policy=stack_removal_policy,
        )

        aws_cdk.CfnOutput(
            self,
            "out-dbt-run-repository_uri",
            value=self.dbt_run_repository.repository_uri_for_tag("latest"),
        )

        self.athena_prod_workgroup = aws_athena.CfnWorkGroup(
            self,
            id="athena_prod_workgroup",
            name="dbt_prod",
            description="Workgroup for the dbt prod usage",
            work_group_configuration={
                # Otherwise one cannot overwrite the output location
                "enforceWorkGroupConfiguration": False,
                "resultConfiguration": {
                    "encryptionConfiguration": {
                        "encryptionOption": "SSE_S3",
                    },
                    # I haven't found a way to use per user locations: it's either one workgroup
                    # per user or a shared location...
                    "outputLocation": f"s3://{self.s3_query_result_bucket.bucket_name}/prod/",
                },
            },
            recursive_delete_option=force_delete_flag,
        )

        aws_cdk.CfnOutput(
            self,
            "out-athena_prod_workgroup",
            value=self.athena_prod_workgroup.name,
        )

        self.allow_prod_athena_access_policy_document = create_policy_document_for_athena_principal(
            account=account,
            region=region,
            workgroup=self.athena_prod_workgroup,
            allowed_glue_database_names="prod_*",
            query_result_bucket=self.s3_query_result_bucket,
            # No slash at the beginning or end!
            query_result_bucket_userspecific_s3_prefix="prod",
            raw_converted_database=self.raw_converted_database,
            raw_bucket=self.s3_raw_bucket,
        )
        self.allow_prod_athena_access_managed_policy = aws_iam.ManagedPolicy(
            self,
            "allow_prod_athena_access_managed_policy",
            document=self.allow_prod_athena_access_policy_document,
            # Do not set to not have problems when deploying any changes to the policy. See best practises for cdk
            # managed_policy_name="AllowAthenaAccessToUsers",
            description="Allow athena access to dbt prod.",
        )

        # We do not add a cluster (nor a vpc), so both are created for us in the ScheduledFargateTask

        self.dbt_runner_task = aws_ecs_patterns.ScheduledFargateTask(
            self,
            id="dbtScheduledFargateTask",
            vpc=vpc,
            scheduled_fargate_task_image_options=aws_ecs_patterns.ScheduledFargateTaskImageOptions(
                # Latest => a revert will be a git revert + push!
                image=aws_ecs.ContainerImage.from_ecr_repository(self.dbt_run_repository, tag="latest"),
                # We do not need much, as the main work will be done on the athena service, but we want
                # 2 vCPU and this is only possible with 4GB of mem. For the cpu definition: 1vCPU = 1024
                # https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html
                memory_limit_mib=4096,
                cpu=2048,
                # Needed to actually trigger the use of the right "config" from dbt/profile-prod.yml
                environment={"DBT_TARGET": "prod"},
            ),
            # daily at 0123 UTC
            schedule=aws_applicationautoscaling.Schedule.cron(
                minute="23",
                hour="1",
                month="*",
                week_day="*",
                year="*",
            ),
            subnet_selection=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            platform_version=aws_ecs.FargatePlatformVersion.LATEST,  # type: ignore
        )

        self.dbt_runner_task.task_definition.task_role.add_managed_policy(self.allow_prod_athena_access_managed_policy)


def create_policy_document_for_athena_principal(
    *,
    account: str,
    region: str,
    workgroup: aws_athena.CfnWorkGroup,
    allowed_glue_database_names: str,
    query_result_bucket: aws_s3.Bucket,
    query_result_bucket_userspecific_s3_prefix: str,
    raw_converted_database: glue.Database,
    raw_bucket: aws_s3.Bucket,
):
    # Athena access has three levels
    # 1. Access to athena and athena (specific) workgroups
    # 2. Read/write access to the glue database + tables
    # 3. Read/write access to the underlying data in s3
    # The latter two usually come paired...

    return aws_iam.PolicyDocument(
        statements=[
            aws_iam.PolicyStatement.from_json(
                {
                    # Athena: usage rights
                    "Effect": "Allow",
                    "Action": [
                        "athena:ListEngineVersions",
                        "athena:ListWorkGroups",
                        "athena:ListDataCatalogs",
                        "athena:ListDatabases",
                        "athena:GetDatabase",
                        "athena:ListTableMetadata",
                        "athena:GetTableMetadata",
                    ],
                    "Resource": "*",
                },
            ),
            aws_iam.PolicyStatement.from_json(
                {
                    # Athena workgroup: usage rights
                    "Effect": "Allow",
                    "Action": [
                        "athena:GetWorkGroup",
                        "athena:BatchGetQueryExecution",
                        "athena:GetQueryExecution",
                        "athena:ListQueryExecutions",
                        "athena:StartQueryExecution",
                        "athena:StopQueryExecution",
                        "athena:GetQueryResults",
                        "athena:GetQueryResultsStream",
                        "athena:CreateNamedQuery",
                        "athena:GetNamedQuery",
                        "athena:BatchGetNamedQuery",
                        "athena:ListNamedQueries",
                        "athena:DeleteNamedQuery",
                        "athena:CreatePreparedStatement",
                        "athena:GetPreparedStatement",
                        "athena:ListPreparedStatements",
                        "athena:UpdatePreparedStatement",
                        "athena:DeletePreparedStatement",
                    ],
                    "Resource": [
                        f"arn:aws:athena:{region}:{account}:workgroup/{workgroup.name}",
                    ],
                },
            ),
            aws_iam.PolicyStatement.from_json(
                {
                    # Glue: read and write access to the user db and tables in this db
                    "Effect": "Allow",
                    "Action": [
                        # read part
                        "glue:BatchGetPartition",
                        "glue:GetDatabase",
                        "glue:GetDatabases",
                        "glue:GetPartition",
                        "glue:GetPartitions",
                        "glue:GetTable",
                        "glue:GetTables",
                        "glue:GetTableVersion",
                        "glue:GetTableVersions",
                        # write part
                        "glue:BatchCreatePartition",
                        "glue:UpdateDatabase",
                        "glue:DeleteDatabase",
                        "glue:CreateTable",
                        "glue:CreateDatabase",
                        "glue:UpdateTable",
                        "glue:BatchDeletePartition",
                        "glue:BatchDeleteTable",
                        "glue:DeleteTable",
                        "glue:CreatePartition",
                        "glue:DeletePartition",
                        "glue:UpdatePartition",
                    ],
                    "Resource": [
                        f"arn:aws:glue:{region}:{account}:catalog",
                        # We want users to be able to create multiple databases (schema in dbt)
                        # to allow for proper organizing the transformation results...
                        # But hiding the databases from each other by adding the ${{aws:username}} part
                        # does not work: we can have usernames with dots in it which would break the naming
                        # convention for the databases (and identifiers). Therefor we allow users to see other
                        # users databases, but still not the underlying data, if they use the proper prefix
                        # (see next block, where s3 access is specified).
                        f"arn:aws:glue:{region}:{account}:database/{allowed_glue_database_names}",
                        f"arn:aws:glue:{region}:{account}:table/{allowed_glue_database_names}/*",
                    ],
                },
            ),
            aws_iam.PolicyStatement.from_json(
                {
                    # S3: write access to the Athena results bucket in /users/... prefix
                    "Effect": "Allow",
                    "Action": [
                        "s3:PutObject",
                        "s3:GetObject",
                        "s3:AbortMultipartUpload",
                        "s3:GetBucketLocation",
                    ],
                    "Resource": [
                        query_result_bucket.bucket_arn,
                        # user specific
                        f"{query_result_bucket.bucket_arn}/{query_result_bucket_userspecific_s3_prefix}/*",
                        # shared, used per default in the workgroup
                        f"{query_result_bucket.bucket_arn}/users/shared/*",
                    ],
                }
            ),
            aws_iam.PolicyStatement.from_json(
                {
                    # S3: list access to the Athena results bucket in user prefix
                    "Effect": "Allow",
                    "Action": [
                        "s3:ListBucket",
                    ],
                    "Resource": [
                        query_result_bucket.bucket_arn,
                    ],
                    "Condition": {
                        "StringLike": {
                            "s3:prefix": [
                                f"{query_result_bucket_userspecific_s3_prefix}/*",
                                "users/shared/*",
                            ]
                        }
                    },
                }
            ),
            # Read access to the converted data lake data
            aws_iam.PolicyStatement.from_json(
                {
                    # Glue: read converted data in the data lake
                    "Effect": "Allow",
                    "Action": [
                        "glue:BatchGetPartition",
                        "glue:GetDatabase",
                        "glue:GetDatabases",
                        "glue:GetPartition",
                        "glue:GetPartitions",
                        "glue:GetTable",
                        "glue:GetTables",
                        "glue:GetTableVersion",
                        "glue:GetTableVersions",
                    ],
                    "Resource": [
                        f"arn:aws:glue:{region}:{account}:catalog",
                        f"arn:aws:glue:{region}:{account}:database/{raw_converted_database.database_name}",
                        f"arn:aws:glue:{region}:{account}:table/{raw_converted_database.database_name}/*",
                    ],
                },
            ),
            aws_iam.PolicyStatement.from_json(
                {
                    # S3: read converted data in the data lake
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:ListBucket",
                        "s3:GetBucketLocation",
                    ],
                    "Resource": [
                        raw_bucket.bucket_arn,
                        raw_bucket.bucket_arn + "/*",
                    ],
                },
            ),
        ]
    )
