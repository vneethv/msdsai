Ecommerce Seller Recommendation - Project scaffold
Structure:
- configs/ecomm_prod.yml : paths for inputs and outputs
- src/ : ETL and consumption PySpark scripts (local-parquet placeholders for Hudi)
- scripts/ : spark-submit helper scripts

This scaffold reads the uploaded CSVs under raw/ and writes cleaned parquet under processed/*/cleaned_parquet/
The consumption script produces recommendations CSV to the configured output path.

