from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType, TimestampType


def transform(df: DataFrame, spark_session: SparkSession) -> DataFrame:
    return df.select(
        F.col("journey_id").cast(StringType()),
        F.col("customer_id").cast(StringType()),
        F.col("scooter_id").cast(StringType()),
        F.col("start_dt").cast(TimestampType()),
        F.col("end_dt").cast(TimestampType()),
        F.col("amount_cents").cast(IntegerType()),
    )
