import importlib
import sys
from typing import Dict

# Every awsglue line has to be ignored as we cannot install this from pypi :-(
from awsglue import DynamicFrame  # type: ignore
from awsglue.context import GlueContext  # type: ignore
from awsglue.job import Job  # type: ignore

# from awsglue.transforms import *  # type: ignore
from awsglue.utils import getResolvedOptions  # type: ignore
from pyspark.context import SparkContext
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def extract(
    glue_context: GlueContext,
    source_bucket_uri: str,
    data_format: str,
    compression: str,
) -> DataFrame:
    """Extract data from S3 and return it as a Spark DataFrame."""
    return glue_context.create_dynamic_frame.from_options(
        format_options={"multiline": False},
        connection_type="s3",
        format=data_format,
        connection_options={
            "paths": [source_bucket_uri],
            "recurse": True,
            "compression": compression,
        },
        transformation_ctx="load_from_s3",
    ).toDF()


def load(
    df_clean: DataFrame,
    glue_context: GlueContext,
    target_bucket_uri: str,
    database_name: str,
    table_name: str,
    file_format: str,
    compression: str,
) -> None:
    """Load data from a Spark DataFrame to S3."""
    df_clean_dynamic = DynamicFrame.fromDF(df_clean, glue_context, table_name)

    sink = glue_context.getSink(
        path=target_bucket_uri,
        connection_type="s3",
        updateBehavior="UPDATE_IN_DATABASE",
        partitionKeys=["_created_at"],
        compression=compression,
        enableUpdateCatalog=True,
        transformation_ctx="load_into_s3",
    )
    sink.setCatalogInfo(
        catalogDatabase=database_name,
        catalogTableName=table_name,
    )
    sink.setFormat(file_format)
    sink.writeFrame(df_clean_dynamic)

    return None


# transform
def add_column_partition_date(df: DataFrame, source_partition_variable: str):
    """Adds a column to the dataframe which acts as a date partition."""
    return df.withColumn("_created_at", F.to_date(F.col(source_partition_variable)))


def etl(args: Dict[str, str], glue_context: GlueContext) -> None:
    """Extract, transform and load data by orchestrating the corresponding functions."""
    # source
    source_bucket_uri = args["SOURCE_BUCKET_URI"]
    source_compression_type = args["SOURCE_COMPRESSION_TYPE"]
    source_partition_var = args["SOURCE_PARTITION_VAR"]
    source_format = args["SOURCE_FORMAT"]
    # destination
    target_bucket_uri = args["TARGET_BUCKET_URI"]
    target_db_name = args["TARGET_DB_NAME"]
    target_table_name = args["TARGET_TABLE_NAME"]
    target_compression_type = args["TARGET_COMPRESSION_TYPE"]
    target_format = args["TARGET_FORMAT"]

    df = extract(
        glue_context=glue_context,
        data_format=source_format,
        source_bucket_uri=source_bucket_uri,
        compression=source_compression_type,
    )

    # transform
    # get schema definition
    table_definition = importlib.import_module(f"business_logic.convert.{target_table_name}")

    df = table_definition.transform(df, glue_context.spark_session)
    df = add_column_partition_date(df=df, source_partition_variable=source_partition_var)

    # load
    load(
        df_clean=df,
        glue_context=glue_context,
        target_bucket_uri=target_bucket_uri,
        file_format=target_format,
        database_name=target_db_name,
        table_name=target_table_name,
        compression=target_compression_type,
    )


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "SOURCE_BUCKET_URI",
            "SOURCE_PARTITION_VAR",
            "SOURCE_FORMAT",
            "SOURCE_COMPRESSION_TYPE",
            "TARGET_BUCKET_URI",
            "TARGET_DB_NAME",
            "TARGET_TABLE_NAME",
            "TARGET_COMPRESSION_TYPE",
            "TARGET_FORMAT",
        ],
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    etl(args, glue_context)

    job.commit()


if __name__ == "__main__":
    main()
