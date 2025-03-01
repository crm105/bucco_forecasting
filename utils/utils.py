"""
Generic functions that are used and recycled throughout the project workflow
"""

from sqlalchemy import create_engine

#ToDo: Construct as object that retrieves connection params from environment
def pg_engine(connection_params):
    """ Create a SQLalchemy PG engine connection
    
    Args: 
        connection_params (dict): dictionary containing DB_ USERNAME/PASSWORD/HOST/PORT/NAME keys

    Returns: 
        sqlalchemy.engine.base.Engine
    """
    DB_USERNAME = connection_params['DB_USERNAME']
    DB_PASSWORD = connection_params['DB_PASSWORD']
    DB_HOST = connection_params['DB_HOST']
    DB_PORT = connection_params['DB_PORT']
    DB_NAME = connection_params['DB_NAME']

    connection = f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(connection)
