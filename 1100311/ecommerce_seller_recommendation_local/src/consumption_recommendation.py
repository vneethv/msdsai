#!/usr/bin/env python3
import sys
from pathlib import Path
import yaml
from pyspark.sql import SparkSession
import logging
from pyspark.sql.functions import col, sum as _sum, when, lit, expr
from pyspark.sql.functions import date_format, current_timestamp


# -------------------------
# Logging Setup
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("recommendation_logger")



def load_config(config_file):
    """
    Load YAML config and return (config_dict, config_directory)
    """
    config_path = Path(config_file).resolve()
    config_dir = config_path.parent

    with config_path.open("r") as f:
        config = yaml.safe_load(f)

    return config, config_dir


def resolve_path(config_dir, relative_path):
    """
    Convert relative YAML paths into absolute paths.
    """
    return (config_dir / relative_path).resolve()

# -------------------------
# Schema Validation Helper
# -------------------------
def validate_columns(df, required_cols, df_name):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logger.error(f"Missing columns in {df_name}: {missing}")
        raise Exception(f"Schema validation failed for {df_name}. Missing columns: {missing}")
    logger.info(f"Schema validation passed for {df_name}")

# -------------------------
# Top-N Helper
# -------------------------
def top_n_items(df, key_col, metric_col, n=10):
    return (
        df.orderBy(col(metric_col).desc())
          .limit(n)
    )


def main(config_file):
    # Load config
    config, config_dir = load_config(config_file)

    # Resolve paths from YAML
    seller_parquet_dir = resolve_path(config_dir, config["recommendation"]["seller_catalog_hudi"]) / "cleaned_parquet"
    company_parquet_dir = resolve_path(config_dir, config["recommendation"]["company_sales_hudi"]) / "cleaned_parquet"
    competitor_parquet_dir = resolve_path(config_dir, config["recommendation"]["competitor_sales_hudi"]) / "cleaned_parquet"
    output_csv_path = str(resolve_path(config_dir, config["recommendation"]["output_csv"]))

    print("\n=== PATHS BEING USED ===")
    print("Seller parquet:", seller_parquet_dir)
    print("Company parquet:", company_parquet_dir)
    print("Competitor parquet:", competitor_parquet_dir)
    print("Output CSV:", output_csv_path)
    print("========================\n")

    # Start Spark
    spark = (
        SparkSession.builder
        .appName("SellerConsumptionRecommendation")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .getOrCreate()
    )

    # ---------------------------
    # READ PARQUET — NOT HUDI
    # ---------------------------
    try:
        seller_df = spark.read.parquet(str(seller_parquet_dir))
        print("Loaded seller catalog parquet.")
    except Exception as e:
        print("❌ ERROR loading seller catalog parquet:", e)
        raise

    try:
        company_df = spark.read.parquet(str(company_parquet_dir))
        print("Loaded company sales parquet.")
    except Exception as e:
        print("❌ ERROR loading company sales parquet:", e)
        raise

    try:
        competitor_df = spark.read.parquet(str(competitor_parquet_dir))
        print("Loaded competitor sales parquet.")
    except Exception as e:
        print("❌ ERROR loading competitor sales parquet:", e)
        raise

    # -------------------------
    # Schema Validation
    # -------------------------
    validate_columns(
        seller_df,
        ["seller_id", "item_id", "item_name", "category", "marketplace_price", "stock_qty"],
        "seller_catalog"
    )

    validate_columns(
        company_df,
        ["item_id", "units_sold", "revenue", "sale_date"],
        "company_sales"
    )

    validate_columns(
        competitor_df,
        ["item_id", "units_sold", "revenue", "marketplace_price", "seller_id", "sale_date"],
        "competitor_sales"
    )

     # -------------------------
    # Clean & Preprocess
    # -------------------------
    company_df = company_df.withColumn("sale_ym", date_format(col("sale_date"), "yyyy-MM"))
    competitor_df = competitor_df.withColumn("sale_ym", date_format(col("sale_date"), "yyyy-MM"))

    # -------------------------
    # Aggregate company top sellers
    # -------------------------
    company_agg = (
        company_df.groupBy("item_id")
            .agg(_sum("units_sold").alias("total_units"))
    )

    top_company_items = top_n_items(company_agg, "item_id", "total_units", 10)

    logger.info("Computed Top-N company items")

 # -------------------------
    # Aggregate competitor top sellers
    # -------------------------
    competitor_agg = (
        competitor_df.groupBy("item_id")
                  .agg(_sum("units_sold").alias("comp_units"))
    )

    top_competitor_items = top_n_items(competitor_agg, "item_id", "comp_units", 10)

    logger.info("Computed Top-N competitor items")

    # -------------------------
    # Join seller catalog to find missing items
    # -------------------------
    seller_items = seller_df.select("seller_id", "item_id").dropDuplicates()

    missing_company = (
        seller_items.join(top_company_items, "item_id", "right")
                     .where(seller_items["item_id"].isNull())
                     .select(lit(None).alias("seller_id"), "item_id", "total_units")
    )

    missing_competitor = (
        seller_items.join(top_competitor_items, "item_id", "right")
                     .where(seller_items["item_id"].isNull())
                     .select(lit(None).alias("seller_id"), "item_id", "comp_units")
    )

     # Expected revenue calculation
    # -------------------------
    avg_price = competitor_df.groupBy("item_id") \
                       .agg(expr("avg(marketplace_price)").alias("market_price"))

    expected = (
        top_company_items.join(avg_price, "item_id", "left")
            .withColumn(
                "expected_units_sold",
                col("total_units")  # naive method — can be improved
            )
            .withColumn(
                "expected_revenue",
                col("expected_units_sold") * col("market_price")
            )
    )

    logger.info("Expected revenue calculated")

    # -------------------------
    # Final Output
    # -------------------------
    final = expected.select(
        "item_id",
        "market_price",
        "expected_units_sold",
        "expected_revenue"
    )

    logger.info("Writing recommendations output to {output_csv_path}")

    final.write.mode("overwrite").option("header", True).csv(output_csv_path)

    logger.info("Recommendation job completed successfully.")

    # Make sure output directory exists
    # output_csv_path.parent.mkdir(parents=True, exist_ok=True)

#    # Save CSV
#    (
#        result_df.coalesce(1)
#        .write.mode("overwrite")
#        .option("header", True)
#        .csv(str(output_csv_path))
#    )
#
    print(f"✔ Recommendation file written to: {output_csv_path}")

    spark.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python consumption_recommendation.py <config.yml>")
        sys.exit(1)

    main(sys.argv[1])

