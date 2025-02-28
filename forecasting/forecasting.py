import numpy as np
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

query = "SELECT * FROM crm_mart.prediction_frame"
prediction_frame = pd.read_sql(query, con = engine )

#ToDo: Use config or other source to specify features to ensure 
features = ['home_pct', 'away_pct']
X = prediction_frame[features]

with open('../modeling/saved_models/model.pkl','rb') as f:
    model = pickle.load(f)

prediction_frame['home_win_pred'] = model.predict(X)

prediction_frame['pirates_win_prob'] = np.where(prediction_frame['home_id'] == 134,
                                                 prediction_frame['home_win_pred'],
                                                 1 - prediction_frame['home_win_pred'])

#ToDo: Determine what to output and where to store output