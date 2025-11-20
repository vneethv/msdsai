#!/usr/bin/env python3
import sys
from pathlib import Path
import yaml
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum as _sum, avg as _avg, lit, coalesce, when, row_number
)
from pyspark.sql.window import Window


def load_config(config_file):
    config_path = Path(config_file).resolve()
    config_dir = config_path.parent
    with config_path.open("r") as f:
        cfg = yaml.safe_load(f)
    return cfg, config_dir


def resolve_path(config_dir, relative_path):
    return (config_dir / relative_path).resolve()


def validate_columns(df, required_cols, df_name):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise Exception(f"Schema validation failed for {df_name}. Missing: {missing}")


def main(config_file):
    config, config_dir = load_config(config_file)

    seller_parquet_dir = resolve_path(config_dir, config["recommendation"]["seller_catalog_hudi"]) / "gold"
    company_parquet_dir = resolve_path(config_dir, config["recommendation"]["company_sales_hudi"]) / "gold"
    competitor_parquet_dir = resolve_path(config_dir, config["recommendation"]["competitor_sales_hudi"]) / "gold"
    output_csv_path = str(resolve_path(config_dir, config["recommendation"]["output_csv"]))


    spark = (
        SparkSession.builder
        .appName("SellerConsumptionRecommendation")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .getOrCreate()
    )

    seller_df = spark.read.parquet(str(seller_parquet_dir))
    company_df = spark.read.parquet(str(company_parquet_dir))
    competitor_df = spark.read.parquet(str(competitor_parquet_dir))

    # Schemas
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

    # Product metadata (name + category)
    product_meta = seller_df.select("item_id", "item_name", "category").dropDuplicates(["item_id"])

    # Aggregate totals
    company_totals = (
        company_df.groupBy("item_id")
                  .agg(_sum("units_sold").alias("company_units"),
                       _sum("revenue").alias("company_revenue"))
    )

    competitor_totals = (
        competitor_df.groupBy("item_id")
                     .agg(_sum("units_sold").alias("competitor_units"),
                          _sum("revenue").alias("competitor_revenue"),
                          _avg("marketplace_price").alias("competitor_price"))
    )

    # Compute fallback company average price
    company_price = company_totals.withColumn(
        "company_price",
        when(col("company_units") > 0, col("company_revenue") / col("company_units"))
    ).select("item_id", "company_price")

    # Merge → price_table + metadata
    price_table = (
        competitor_totals.join(company_price, "item_id", "full_outer")
                         .join(product_meta, "item_id", "left")
    ).withColumn(
        "market_price",
        coalesce(col("competitor_price"), col("company_price"))
    )

    # Compute total units (company + competitor)
    totals = (
        company_totals.join(competitor_totals, "item_id", "full_outer")
                      .select(
                          coalesce(company_totals["item_id"], competitor_totals["item_id"]).alias("item_id"),
                          company_totals["company_units"],
                          competitor_totals["competitor_units"]
                      )
    ).fillna(0)

    totals = totals.withColumn(
        "total_units", col("company_units") + col("competitor_units")
    )

    totals_with_meta = totals.join(price_table, "item_id", "left")

    # Get the Top 10 selling items
    window_top = Window.orderBy(col("total_units").desc())

    top10_items = (
        totals_with_meta.withColumn("rn", row_number().over(window_top))
                        .where(col("rn") <= 10)
                        .select("item_id", "item_name", "category", "market_price", "total_units")
    )


    # Sellers who sell each item 
    sellers_per_item = (
        seller_df.select("item_id", "seller_id")
                 .dropDuplicates()
                 .groupBy("item_id")
                 .agg(_sum(lit(1)).alias("num_sellers"))
    )

    # Recommendation logic
    # For each seller → find which of the Top 10 they are missing
    sellers = seller_df.select("seller_id").dropDuplicates()
    seller_items = seller_df.select("seller_id", "item_id").dropDuplicates()

    # join sellers × top10 items
    seller_candidates = sellers.crossJoin(top10_items)

    # Exclude items the seller already has
    missing = seller_candidates.join(seller_items, ["seller_id", "item_id"], "left_anti")

    # Attach num sellers selling item
    missing = missing.join(sellers_per_item, "item_id", "left")

    missing = missing.withColumn(
        "num_sellers",
        when(col("num_sellers").isNull() | (col("num_sellers") == 0), lit(1))
        .otherwise(col("num_sellers"))
    )

    # Compute expected_units_sold + expected_revenue
    missing = missing.withColumn(
        "expected_units_sold",
        col("total_units") / col("num_sellers")
    )

    missing = missing.withColumn(
        "expected_revenue",
        col("expected_units_sold") * col("market_price")
    )

    # Generate the output file
    output = missing.select(
        "seller_id",
        "item_id",
        "item_name",
        "category",
        "market_price",
        "expected_units_sold",
        "expected_revenue"
    )


    output.coalesce(1).write.mode("overwrite").option("header", True).csv(output_csv_path)

    spark.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python consumption_recommendation.py <config.yml>")
        sys.exit(1)
    main(sys.argv[1])


