import numpy as np
import pandas as pd
import pickle
import yaml

from sklearn.linear_model import LinearRegression
from sqlalchemy import create_engine

import sys
sys.path.append('..')

from utils.utils import pg_engine

with open("../db_config.yml", "r") as file:
    db_config = yaml.safe_load(file)

engine = pg_engine(db_config)

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