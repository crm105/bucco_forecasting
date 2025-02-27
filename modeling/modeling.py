import pandas as pd
import pickle
import yaml

from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine

#ToDo: Offload Engine Creation to Util, Draw from environmental variables 
with open("../db_config.yml", "r") as file:
    config = yaml.safe_load(file)

DB_USERNAME = config["DB_USERNAME"]
DB_PASSWORD = config["DB_PASSWORD"]
DB_HOST = config["DB_HOST"]
DB_PORT = config["DB_PORT"]
DB_NAME = config["DB_NAME"]
TABLE_NAME = "game_results"

engine = create_engine(f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

query = "SELECT * FROM crm_mart.modeling_frame"
modeling_frame = pd.read_sql(query, con = engine )

""" 
Placeholder model with lots to do

ToDo: Train/Validation/Test Split and/or K-fold CV
ToDo: Model QC
ToDo: Define parameters, features in config
ToDo: Enable Feature Transformations
"""

features = ['home_pct', 'away_pct']
X = modeling_frame[features]
y = modeling_frame.home_win

linear_model = LinearRegression()
linear_model.fit(X, y)

with open('saved_models/model.pkl','wb') as f:
    pickle.dump(linear_model,f)