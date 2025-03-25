"""
Generic functions that are used and recycled throughout the project workflow
"""
import os
from sqlalchemy import create_engine

#ToDo: Construct as object that retrieves connection params from environment
def pg_engine():
    """ Create a SQLalchemy PG engine connection
    
    Args: 
        
    Returns: 
        sqlalchemy.engine.base.Engine
    """
    DB_USERNAME = os.environ['DB_USERNAME']
    DB_PASSWORD = os.environ['DB_PASSWORD']
    DB_HOST = os.environ['DB_HOST']
    DB_PORT = os.environ['DB_PORT']
    DB_NAME = os.environ['DB_NAME']

    connection = f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(connection)
