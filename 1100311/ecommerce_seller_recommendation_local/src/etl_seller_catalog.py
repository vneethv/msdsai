from pyspark.sql import SparkSession, functions as F, types as T
import yaml, sys

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
    inp = cfg['seller_catalog']['input_path']
    out = cfg['seller_catalog']['hudi_output_path']

    spark = get_spark_session("etl_seller_catalog")
    df = (spark.read.option("header",True).csv(inp))

    # Trim and rename
    for c in ['seller_id','item_id','item_name','category']:
        df = df.withColumn(c, F.trim(F.col(c)))
    # Normalize casing
    df = df.withColumn('item_name', F.initcap(F.col('item_name')))
    df = df.withColumn('category', F.initcap(F.col('category')))

    # Cast numeric
    df = df.withColumn('marketplace_price', F.col('marketplace_price').cast('double'))           .withColumn('stock_qty', F.col('stock_qty').cast('int'))

    # Fill stock nulls with 0
    df = df.withColumn('stock_qty', F.when(F.col('stock_qty').isNull(), F.lit(0)).otherwise(F.col('stock_qty')))

    # DQ checks: collect bad records
    dq_exprs = [
      ("missing_seller_id", F.col('seller_id').isNull()),
      ("missing_item_id", F.col('item_id').isNull()),
      ("missing_item_name", F.col('item_name').isNull()),
      ("missing_category", F.col('category').isNull()),
      ("negative_price", F.col('marketplace_price') < 0),
      ("negative_stock", F.col('stock_qty') < 0)
    ]

    bad = None
    for name, expr in dq_exprs:
        bad_part = df.filter(expr).withColumn("dq_failure_reason", F.lit(name))
        bad = bad_part if bad is None else bad.unionByName(bad_part, allowMissingColumns=True)

    good = df
    if bad is not None:
        # remove bad records from good by anti-join on primary key
        key = ['seller_id','item_id']
        bad_keys = bad.select(*key).distinct()
        good = good.join(bad_keys, on=key, how='left_anti')
        # write bad to quarantine (CSV)
        bad.write.mode('overwrite').option('header',True).csv(out + "/quarantine/")
    # Remove duplicates based on key keeping latest (if no timestamp, keep first)
    good = good.dropDuplicates(['seller_id','item_id'])

    # Write cleaned parquet (placeholder for Hudi - here using parquet for local)
    good.write.mode('overwrite').option('header',True).parquet(out + "/cleaned_parquet/")
    spark.stop()

if __name__ == '__main__':
    main(sys.argv[1])