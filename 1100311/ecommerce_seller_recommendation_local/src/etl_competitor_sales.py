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

    inp         = cfg['competitor_sales']['input_path']
    out         = cfg['competitor_sales']['hudi_output_path']
    bronze_out  = out + "/bronze/"
    silver_out  = out + "/silver/"
    gold_out    = out + "/gold/"

    spark = get_spark_session("etl_competitor_sales")
    bronze = (spark.read.option("header",True).csv(inp))
    # write bronze for reference
    bronze.write.mode("overwrite").csv(bronze_out)

    silver = bronze
    for c in ['item_id','seller_id']:
        silver = silver.withColumn(c, F.trim(F.col(c)))
    silver = silver.withColumn('units_sold', F.col('units_sold').cast('int'))           .withColumn('revenue', F.col('revenue').cast('double'))           .withColumn('marketplace_price', F.col('marketplace_price').cast('double'))           .withColumn('sale_date', F.to_date(F.col('sale_date')))

    silver = silver.fillna({'units_sold':0, 'revenue':0.0, 'marketplace_price':0.0})

    # write silver for reference
    silver.write.mode('overwrite').option('header',True).parquet(silver_out)

    dq_exprs = [
      ("missing_item_id", F.col('item_id').isNull()),
      ("missing_seller_id", F.col('seller_id').isNull()),
      ("negative_units_sold", F.col('units_sold') < 0),
      ("negative_revenue", F.col('revenue') < 0),
      ("negative_price", F.col('marketplace_price') < 0),
      ("missing_or_future_date", (F.col('sale_date').isNull()) | (F.col('sale_date') > F.current_date()))
    ]

    bad = None
    for name, expr in dq_exprs:
        bad_part = silver.filter(expr).withColumn("dq_failure_reason", F.lit(name))
        bad = bad_part if bad is None else bad.unionByName(bad_part, allowMissingColumns=True)

    gold = silver
    if bad is not None:
        bad.write.mode('overwrite').option('header',True).csv(out + "/quarantine/")
        bad_keys = bad.select('item_id','seller_id').distinct()
        gold = gold.join(bad_keys, on=['item_id','seller_id'], how='left_anti')

    gold = gold.dropDuplicates(['seller_id','item_id'])

    # write silver for reference
    gold.write.mode('overwrite').option('header',True).parquet(gold_out)
    spark.stop()

if __name__ == '__main__':
    main(sys.argv[1])
