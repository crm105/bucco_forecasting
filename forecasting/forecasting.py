from datetime import datetime
import numpy as np
import pandas as pd
import pickle
import yaml

import sys
sys.path.append('..')

from utils.utils import pg_engine
from sklearn.linear_model import LinearRegression


#ToDo: Offload Engine Creation to Util, Draw from environmental variables 
with open("../db_config.yml", "r") as file:
    db_config = yaml.safe_load(file)

engine = pg_engine(db_config)

# Let's only consider the week ahead 

query = f"""SELECT * FROM crm_mart.prediction_frame
            WHERE gamedate < CURRENT_DATE + 7"""
prediction_frame = pd.read_sql(query, con = engine )

#ToDo: Use config or other source to specify features to ensure 
features = ['home_pct', 'away_pct']
X = prediction_frame[features]

with open('../modeling/saved_models/model.pkl','rb') as f:
    model = pickle.load(f)

predicted_prob = model.predict(X)
prediction_frame['home_win_prob'] = predicted_prob
prediction_frame['home_win_predicted'] = np.rint(predicted_prob)

prediction_frame['pirates_win_prob'] = np.where(prediction_frame['home_id'] == 134,
                                                 prediction_frame['home_win_prob'],
                                                 1 - prediction_frame['home_win_prob'])

prediction_frame['pirates_win_predicted'] = np.where(prediction_frame['home_id'] == 134,
                                                 prediction_frame['home_win_predicted'],
                                                 1 - prediction_frame['home_win_predicted'])

prediction_frame['forecast_date'] = datetime.today().strftime("%Y-%m-%d")
prediction_frame = prediction_frame[['gamepk', 'gamedate', 'forecast_date',
                                      'pirates_win_prob', 'pirates_win_predicted']]

#Save prediction into PG
prediction_frame.to_sql(name = "completed_predictions", schema = "crm_mart", con = engine,
                        if_exists = "append", index=False)