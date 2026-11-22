import pandas as pd
import time

years = [2017,2018,2019,2020,2021,2022,2023,2024,2025]
payroll_tables=[]
for year in years:
    payroll_table = pd.read_html(f"https://www.spotrac.com/mlb/aav/_/year/{year}/sort/combined_aav_total")[0]
    payroll_table['season'] = year
    payroll_table['Team'] = payroll_table['Team'].str[:3]
    payroll_tables.append(payroll_table)
    time.sleep(10)
payroll_tables = pd.concat(payroll_tables).dropna()

import os
os.environ['DB_HOST'] = 'localhost'

engine = pg_engine()

payroll_tables['Total AAV'] = payroll_tables['Total AAV'].replace({'\$':'', ',':''}, regex=True).astype(int)

payroll_tables.to_sql('payroll_tables', engine, schema = "spotrac", if_exists="append",
                #method = _postgres_upsert,
                        index=False)
