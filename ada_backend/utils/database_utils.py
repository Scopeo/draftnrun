"""
Database utility functions for direct PostgreSQL connections.
Provides reusable connection management for cases where Django ORM or SQLAlchemy aren't suitable.
"""

import logging
from contextlib import contextmanager
from typing import Generator, Tuple

import psycopg2
from settings import settings

LOGGER = logging.getLogger(__name__)


@contextmanager
def get_postgres_connection() -> Generator[Tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor], None, None]:
    """
    Context manager for PostgreSQL database connections.
    
    Yields:
        Tuple of (connection, cursor) for database operations
        
    Usage:
        with get_postgres_connection() as (conn, cursor):
            cursor.execute("SELECT * FROM table")
            results = cursor.fetchall()
    """
    db_params = {
        "dbname": settings.ADA_DB_NAME,
        "user": settings.ADA_DB_USER,
        "password": settings.ADA_DB_PASSWORD,
        "host": settings.ADA_DB_HOST,
        "port": settings.ADA_DB_PORT,
    }
    
    conn = None
    cursor = None
    
    try:
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()
        
        yield conn, cursor
        
        # Commit transaction if no exception occurred
        conn.commit()
        
    except Exception as e:
        if conn:
            conn.rollback()
        LOGGER.error(f"Database operation failed: {str(e)}")
        raise
        
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close() 