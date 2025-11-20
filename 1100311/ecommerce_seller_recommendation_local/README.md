Name    : Vineeth Vijayan
ID      : 2025EM1100311


The project follows the below directory structure.
Each processed folder has bronze, Silver, quarantine and gold outputs.
consumption_recommendation_spark_submit.sh uses gold output for processing.

#2025EM1100311/ecommerce_seller_recommendation_local/

├── configs
│   └── ecomm_prod.yml # Paths for Inputs/Outputs
├── processed  #Output files
│   ├── company_sales_hudi
│   │   ├── bronze 
│   │   ├── gold
│   │   ├── quarantine
│   │   └── silver
│   ├── competitor_sales_hudi
│   │   ├── bronze
│   │   ├── gold
│   │   ├── quarantine
│   │   └── silver
│   ├── recommendations_csv
│   │   └── seller_recommend_data.csv
│   └── seller_catalog_hudi
│       ├── bronze
│       ├── gold
│       ├── quarantine
│       └── silver
├── inputs
│   ├── company_sales_clean.csv
│   ├── competitor_sales_clean.csv
│   └── seller_catalog_clean.csv
├── README.md
├── scripts
│   ├── consumption_recommendation_spark_submit.sh
│   ├── etl_company_sales_spark_submit.sh
│   ├── etl_competitor_sales_spark_submit.sh
│   └── etl_seller_catalog_spark_submit.sh
└── src
    ├── consumption_recommendation.py
    ├── etl_company_sales.py
    ├── etl_competitor_sales.py
    └── etl_seller_catalog.py

Execution:

0. cd 2025EM1100311/ecommerce_seller_recommendation_local/. 
1. Make sure that the CSV files are copied at inputs directory.
2. Execute scripts/etl* and generate the processed gold files.
   then execute the consumption_recommendation_spark_submit.sh.

   i.e
   bash etl_company_sales_spark_submit.sh
   bash etl_competitor_sales_spark_submit.sh
   bash etl_seller_catalog_spark_submit.sh
   bash consumption_recommendation_spark_submit.sh

The output file will be generated at 
    *processed/recommendations_csv/seller_recommend_data.csv*
