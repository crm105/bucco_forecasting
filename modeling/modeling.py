import pandas as pd
import pickle
import yaml

import sys
sys.path.append('..')

from sklearn.linear_model import LinearRegression
from utils.utils import pg_engine

engine = pg_engine()

query = "SELECT * FROM crm_mart.modeling_frame"
modeling_frame = pd.read_sql(query, con = engine )

""" 
Placeholder model with lots to do

ToDo: Train/Validation/Test Split and/or K-fold CV
ToDo: Model QC
ToDo: Define parameters, features in config
ToDo: Enable Feature Transformations
"""

with open('../modeling/modeling_config.yml', "r") as file:
        ml_config = yaml.safe_load(file)

features = ml_config['features']  
X = modeling_frame[features]
y = modeling_frame.home_win

linear_model = LinearRegression()
linear_model.fit(X, y)

with open('saved_models/model.pkl','wb') as f:
    pickle.dump(linear_model,f)