"""
Script for training an XGB Classifier using data from modeling frame
Leverages Bayesian Search to tune HP's specified in accompanying model config
"""
import pandas as pd
import pickle
import yaml

import xgboost as xgb
from skopt import BayesSearchCV
from skopt.space import Real, Integer, Categorical

from utils.utils import pg_engine
from sklearn.model_selection import train_test_split

engine = pg_engine()

"""
2017 data are missing previous year features
2020 and 2021 have COVID cancelation related concerns
"""
query = "SELECT * FROM crm_mart.modeling_frame WHERE season not in (2017, 2020, 2021)"
modeling_frame = pd.read_sql(query, con = engine )

"""
Placeholder model with lots to do

ToDo: Model QC
ToDo: Enable Feature Transformations
"""

with open('modeling/modeling_config.yml', "r") as file:
        ml_config = yaml.safe_load(file)

features = ml_config['features']

X = modeling_frame[features]
y = modeling_frame['home_win']

X = modeling_frame[features]
# ToDo: Define specific feature fills in config
X = X.fillna(-1000)
#ToDo: Fill should occur within train and test separately
X_train, X_test, y_train, y_test = train_test_split(X, y, random_state=412)

dmatrix = xgb.DMatrix(X_train.to_numpy(),y_train.to_numpy())

search_space = {
    param: (
        Integer(v["min"], v["max"]) if v["type"] == "int" else
        Real(v["min"], v["max"], prior=v.get("scale", "uniform"))
    )
    for param, v in ml_config["search_params"].items()
}

opt = BayesSearchCV(
    xgb.XGBClassifier(objective='binary:logistic'),
    search_spaces = search_space,
    n_iter=50,
    scoring = 'accuracy'
)

opt.fit(X_train, y_train)

clf = xgb.XGBClassifier(eval_metric = 'logloss',**opt.best_params_)
clf.fit(X_train.to_numpy(), y_train.to_numpy())

with open('saved_models/model.pkl','wb') as f:
    pickle.dump(clf,f)
