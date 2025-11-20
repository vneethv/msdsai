from pyspark.sql import SparkSession, functions as F, types as T
import yaml, sys
from pyspark.sql.utils import AnalysisException

def get_spark_session(app_name: str):
    spark = (SparkSession.builder.appName(app_name)
             .config("spark.serializer","org.apache.spark.serializer.KryoSerializer")
             .config("spark.sql.legacy.timeParserPolicy","LEGACY")
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    return spark

def main(config_path):
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    inp = cfg['company_sales']['input_path']
    out = cfg['company_sales']['hudi_output_path']

    spark = get_spark_session("etl_company_sales")
    df = (spark.read.option("header",True).csv(inp))

    df = df.withColumn('item_id', F.trim(F.col('item_id')))
    df = df.withColumn('units_sold', F.col('units_sold').cast('int'))           .withColumn('revenue', F.col('revenue').cast('double'))           .withColumn('sale_date', F.to_date(F.col('sale_date')))

    df = df.fillna({'units_sold':0, 'revenue':0.0})

    dq_exprs = [
      ("missing_item_id", F.col('item_id').isNull()),
      ("negative_units_sold", F.col('units_sold') < 0),
      ("negative_revenue", F.col('revenue') < 0),
      ("missing_or_future_date", (F.col('sale_date').isNull()) | (F.col('sale_date') > F.current_date()))
    ]

    bad = None
    for name, expr in dq_exprs:
        bad_part = df.filter(expr).withColumn("dq_failure_reason", F.lit(name))
        bad = bad_part if bad is None else bad.unionByName(bad_part, allowMissingColumns=True)

    good = df
    if bad is not None:
        bad.write.mode('overwrite').option('header',True).csv(out + "/quarantine/")
        bad_keys = bad.select('item_id').distinct()
        good = good.join(bad_keys, on='item_id', how='left_anti')

    good = good.dropDuplicates(['item_id'])

    good.write.mode('overwrite').option('header',True).parquet(out + "/cleaned_parquet/")
    spark.stop()

if __name__ == '__main__':
    main(sys.argv[1])