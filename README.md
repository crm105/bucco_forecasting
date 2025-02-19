# bucco_forecasting
Hobby project focusing on developing an automated pipeline for producing and maintaining a Pittsburgh Pirates win prediction model


## Objectives

1.) Create an ML model that predicts probability of Pirates winning next game

2.) Allow for incremental lzearning to occur while in production 

3.) Training and prediction/forecast data are ingested and curated through an automated process 

I'm currently most interested in first standing up a pipeline that allows me to automate retreiving and processing data that can be used to train a prediction model. I'd like to deploy the model and allow for it to learn as new data is produced (i.e. more baseball is played). More structural changes to the prediction model can occur simultaneously following a traditional development framework. Ultimately, I suspect it may be some time before I focus on feature engineering and improving actual model performance. 

## RoadMap

### Construct a primitive ELT pipeline for collecting modeling, prediction data

 
1.) Scripts for pulling data from MLB api pushing to Postgres
    - Python, YML based approach 

2.) Orchestration of process for processing raw data in Postgres to create a basetable ready for ML modeling, prediction


### Modeling

Goal is to start with a minimally viable workflow for training basic prediction model. Minimum requirement is to be able to allow for cross validation. Do not really care about model performance at this stage so long as it's a reasonable skeleton for future improvements

### Prediction/Scoring 

Allow for orchestrated process to produce model predictions. Goal would be to create a process that does this automatically at a cadence that makes sense given the MLB schedule

## Data Sources:

## Proposed ML Model

Something painfully simple for the forseeable future. Will probably just use basic team level data to minimize the ELT and modeling data curation burden for the foreseeable future. Some fields to start pulling:

1.) Pirates current win %

2.) Opponent current win %

### MLB API
MLB api is free and does not require authentication. It's not particularly well documented, and I'm not sure it's a great source for large quantities/histories of data. However, it does appear to be maintained and updated in near real time. Given my interest in focusing on the workflow (and not necessarily producing a high powered model), I'm ok with this tradeoff for now. 
