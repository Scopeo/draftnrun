"""
Database connection module for QA project migration.

Provides read-only staging and read-write preprod database connections
with transaction management and error handling.
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

logger = logging.getLogger(__name__)

class DatabaseConnectionManager:
    """Manages database connections for staging (read-only) and preprod (read-write)."""
    
    def __init__(self):
        self.staging_pool = None
        self.preprod_pool = None
        self._initialize_connections()
    
    def _initialize_connections(self):
        """Initialize connection pools for staging and preprod databases."""
        try:
            # Staging connection (READ-ONLY)
            staging_url = os.getenv('STAGING_DATABASE_URL')
            if not staging_url:
                raise ValueError("STAGING_DATABASE_URL environment variable not set")
            
            self.staging_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                dsn=staging_url,
                cursor_factory=RealDictCursor
            )
            
            # Preprod connection (READ-WRITE)
            preprod_url = os.getenv('PREPROD_DATABASE_URL')
            if not preprod_url:
                raise ValueError("PREPROD_DATABASE_URL environment variable not set")
            
            self.preprod_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=preprod_url,
                cursor_factory=RealDictCursor
            )
            
            logger.info("Database connection pools initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database connections: {e}")
            raise
    
    @contextmanager
    def get_staging_connection(self):
        """Get a read-only staging database connection."""
        conn = None
        try:
            conn = self.staging_pool.getconn()
            # Ensure read-only mode
            conn.set_session(isolation_level=ISOLATION_LEVEL_READ_COMMITTED, readonly=True)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Staging connection error: {e}")
            raise
        finally:
            if conn:
                self.staging_pool.putconn(conn)
    
    @contextmanager
    def get_preprod_connection(self):
        """Get a read-write preprod database connection."""
        conn = None
        try:
            conn = self.preprod_pool.getconn()
            conn.set_session(isolation_level=ISOLATION_LEVEL_READ_COMMITTED, readonly=False)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Preprod connection error: {e}")
            raise
        finally:
            if conn:
                self.preprod_pool.putconn(conn)
    
    @contextmanager
    def get_preprod_transaction(self):
        """Get a preprod connection with transaction management."""
        conn = None
        try:
            conn = self.preprod_pool.getconn()
            conn.set_session(isolation_level=ISOLATION_LEVEL_READ_COMMITTED, readonly=False)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Preprod transaction error: {e}")
            raise
        finally:
            if conn:
                self.preprod_pool.putconn(conn)
    
    def validate_connections(self) -> Dict[str, bool]:
        """Validate that both database connections are working."""
        results = {'staging': False, 'preprod': False}
        
        # Test staging connection
        try:
            with self.get_staging_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    results['staging'] = True
                    logger.info("Staging connection validated")
        except Exception as e:
            logger.error(f"Staging connection validation failed: {e}")
        
        # Test preprod connection
        try:
            with self.get_preprod_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    results['preprod'] = True
                    logger.info("Preprod connection validated")
        except Exception as e:
            logger.error(f"Preprod connection validation failed: {e}")
        
        return results
    
    def close_all_connections(self):
        """Close all database connections."""
        try:
            if self.staging_pool:
                self.staging_pool.closeall()
                logger.info("Staging connection pool closed")
            
            if self.preprod_pool:
                self.preprod_pool.closeall()
                logger.info("Preprod connection pool closed")
        except Exception as e:
            logger.error(f"Error closing connections: {e}")
    
    def execute_staging_query(self, query: str, params: tuple = None) -> list:
        """Execute a read-only query on staging database."""
        with self.get_staging_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchall()
    
    def execute_preprod_query(self, query: str, params: tuple = None, fetch: bool = True) -> Optional[list]:
        """Execute a query on preprod database."""
        with self.get_preprod_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if fetch:
                    return cur.fetchall()
                conn.commit()
                return None
    
    def execute_preprod_transaction(self, queries: list, params_list: list = None) -> bool:
        """Execute multiple queries in a single transaction on preprod."""
        if params_list is None:
            params_list = [None] * len(queries)
        
        with self.get_preprod_transaction() as conn:
            try:
                with conn.cursor() as cur:
                    for query, params in zip(queries, params_list):
                        cur.execute(query, params)
                    conn.commit()
                    return True
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed: {e}")
                raise
    
    def get_row_count(self, table: str, where_clause: str = "", params: tuple = None) -> int:
        """Get row count for a table with optional WHERE clause."""
        query = f"SELECT COUNT(*) FROM {table}"
        if where_clause:
            query += f" WHERE {where_clause}"
        
        with self.get_preprod_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.fetchone()['count']
    
    def check_table_exists(self, table: str) -> bool:
        """Check if a table exists in preprod database."""
        query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = %s
        )
        """
        
        with self.get_preprod_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (table,))
                return cur.fetchone()['exists']
