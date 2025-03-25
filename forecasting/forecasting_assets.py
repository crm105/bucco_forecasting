import dagster as dg
from dagster_dbt import dbt_assets, get_asset_key_for_model
from transform_data import transform_assets

from datetime import datetime
import numpy as np
import pandas as pd
import pickle
import yaml

import sys
sys.path.append('..')

from utils.extract_utils import _postgres_upsert
from utils.utils import pg_engine

assets = dg.load_assets_from_modules([transform_assets])

@dg.asset(deps={get_asset_key_for_model(assets, "prediction_frame")},
          group_name = 'forecast')
def model_predictions():
    engine = pg_engine()

    query = f"""SELECT * FROM crm_mart.prediction_frame
                WHERE gamedate < CURRENT_DATE + 7
                AND gamedt > CURRENT_TIMESTAMP
            """
    prediction_frame = pd.read_sql(query, con = engine )

    with open('modeling/modeling_config.yml', "r") as file:
            ml_config = yaml.safe_load(file)

    features = ml_config['features']  
    
    #ToDo: Think of better way to fillna
    X = prediction_frame[features]
    X = X.fillna(-1000)

    with open('modeling/saved_models/model.pkl','rb') as f:
        model = pickle.load(f)

    predicted_prob = model.predict_proba(X.to_numpy())[:,1]
    prediction_frame['home_win_prob'] = predicted_prob
    prediction_frame['home_win_predicted'] = np.rint(predicted_prob)

    prediction_frame['forecast_date'] = datetime.today().strftime("%Y-%m-%d")
    prediction_frame['forecast_datetime'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    #Save prediction into PG
    prediction_frame.to_sql(name = "completed_predictions", schema = "crm_mart", con = engine,
                            if_exists = "append", index=False, 
                            method = _postgres_upsert)

del(assets)
