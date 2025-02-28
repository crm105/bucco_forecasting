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
    connection = "postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}".format(**connection_params)
    return create_engine(connection)
