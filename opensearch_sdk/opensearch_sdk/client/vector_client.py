"""
Multi-retrieval client for Opensearch Vector Database.

Provides a unified interface for vector search, full-text search, 
hybrid search, and multi-path retrieval.
"""

import logging
from typing import List, Dict, Any, Optional, Union

from psycopg2 import sql
from psycopg2.vector_types import (
    TableSchema, IndexConfig, SearchResult,
    VectorDBException, TableNotFoundException, ColumnType, DistanceMetric
)
from psycopg2.retrievers import VectorRetriever, FullTextRetriever

from opensearch_sdk.client.constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_HNSW_EF_SEARCH,
    DEFAULT_RABITQ_SAMPLE_ROWS,
)

logger = logging.getLogger(__name__)


class MultiRetrieverClient:
    """Multi-retrieval client
    
    Provides a unified interface for vector search, full-text search, 
    hybrid search, and multi-path retrieval.
    
    Example:
        >>> # Create Opensearch client (use environment variables or config file)
        >>> import os
        >>> client = OpenGauss(
        ...     hosts=[{"host": os.getenv("DB_HOST", "localhost"), "port": int(os.getenv("DB_PORT", "5432"))}],
        ...     database=os.getenv("DB_NAME", "mydb"),
        ...     user=os.getenv("DB_USER", "myuser"),
        ...     password=os.getenv("DB_PASSWORD")  # Must set environment variable
        ... )
        >>>
        >>> # Access multi-retrieval client
        >>> multi = client.multi
        >>>
        >>> # Create table
        >>> schema = TableSchema(columns=[...])
        >>> multi.create_table("documents", schema)
        >>>
        >>> # Vector search
        >>> results = multi.vector_search(
        ...     table_name="documents",
        ...     query_vector=[0.1, 0.2, ...],
        ...     top_k=10
        ... )
    """
    
    def __init__(self, parent_client):
        """Initialize multi-retrieval client
        
        Args:
            parent_client: Parent Opensearch client instance
        """
        self.parent = parent_client
        logger.info("MultiRetrieverClient initialized")
    
    def get_connection(self):
        """Get connection from parent client"""
        return self.parent.get_connection()
    
    def return_connection(self, conn):
        """Return connection to parent client"""
        self.parent.return_connection(conn)
    
    def close(self):
        """Close client (delegates to parent)"""
        self.parent.close()
        logger.info("MultiRetrieverClient closed")
    
    def _get_mapping(self, table_name: str) -> dict:
        """
        Get index mapping for nested field detection
        
        :param table_name: Table name
        :return: Mapping dictionary, empty dict if failed
        """
        try:
            if hasattr(self.parent, 'indices') and hasattr(self.parent.indices, 'get_mapping'):
                return self.parent.indices.get_mapping(index=table_name)
        except Exception:
            pass
        return {}
    
    @staticmethod
    def _has_nested_fields(mapping: dict) -> bool:
        """
        Check if mapping contains nested fields
        
        :param mapping: Index mapping
        :return: True if contains nested fields
        """
        if not mapping or 'mappings' not in mapping:
            return False
        
        properties = mapping['mappings'].get('properties', {})
        return any(
            props.get('type') == 'nested' 
            for props in properties.values()
        )
    
    def execute_sql(
        self,
        query: str,
        params: tuple = None,
        fetch: bool = True
    ) -> Optional[List[Dict]]:
        """Execute SQL query
        
        Args:
            query: SQL query statement
            params: Query parameters
            fetch: Whether to return query results
            
        Returns:
            List of query results (if fetch=True)
        """
        conn = None
        db_cursor = None
        try:
            # [FIX] 使用新的连接管理模式
            with self.parent.connection.get_connection_for_operation() as conn:
                db_cursor = conn.cursor()
                
                if params is not None:
                    db_cursor.execute(query, params)
                else:
                    db_cursor.execute(query)
                
                results = None
                if fetch and hasattr(db_cursor, 'description') and db_cursor.description:
                    # Convert tuple rows to dicts
                    columns = [desc[0] for desc in db_cursor.description]
                    results = [dict(zip(columns, row)) for row in db_cursor.fetchall()]
                
                conn.commit()
                return results
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"SQL execution failed: {e}\nQuery: {query}")
            raise VectorDBException(f"SQL execution failed: {e}")
        finally:
            # Close the cursor
            if db_cursor:
                db_cursor.close()
    
    def create_table(
        self,
        table_name: str,
        schema: TableSchema,
        if_not_exists: bool = True
    ) -> bool:
        """Create table
        
        Args:
            table_name: Table name
            schema: Table schema
            if_not_exists: Whether to ignore if table exists
            
        Returns:
            Whether creation was successful
        """
        schema.validate()
        
        sql_parts = ["CREATE TABLE"]
        if if_not_exists:
            sql_parts.append("IF NOT EXISTS")
        sql_parts.append(f'"{table_name}"')
        
        column_defs = [col.to_sql() for col in schema.columns]
        sql_parts.append(f"({', '.join(column_defs)})")
        
        sql_query = " ".join(sql_parts)
        
        try:
            self.execute_sql(sql_query, fetch=False)
            logger.info(f"Table '{table_name}' created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create table '{table_name}': {e}")
            return False
    
    def drop_table(
        self,
        table_name: str,
        if_exists: bool = True,
        cascade: bool = False
    ) -> bool:
        """Drop table
        
        Args:
            table_name: Table name
            if_exists: Whether to ignore if table does not exist
            cascade: Whether to cascade delete dependent objects
            
        Returns:
            Whether deletion was successful
        """
        sql_parts = ["DROP TABLE"]
        if if_exists:
            sql_parts.append("IF EXISTS")
        sql_parts.append(f'"{table_name}"')
        if cascade:
            sql_parts.append("CASCADE")
        
        sql_query = " ".join(sql_parts)
        
        try:
            self.execute_sql(sql_query, fetch=False)
            logger.info(f"Table '{table_name}' dropped successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to drop table '{table_name}': {e}")
            return False
    
    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Describe table structure
        
        Args:
            table_name: Table name
            
        Returns:
            Table structure information
        """
        query = """
                SELECT
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
                """
        
        columns = self.execute_sql(query, (table_name,))
        
        if not columns:
            raise TableNotFoundException(f"Table '{table_name}' not found")
        
        return {
            "table_name": table_name,
            "columns": columns
        }
    
    def list_tables(self, pattern: str = None) -> List[str]:
        """List all tables
        
        Args:
            pattern: Table name pattern (SQL LIKE syntax)
            
        Returns:
            List of table names
        """
        # 动态获取当前 schema
        current_schema = self.get_connection().get_current_schema()
        
        query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_type = 'BASE TABLE'
                """
        
        params = (current_schema,)
        if pattern:
            query += " AND table_name LIKE %s"
            params = params + (pattern,)
        
        query += " ORDER BY table_name"
        
        results = self.execute_sql(query, params)
        return [row['table_name'] for row in results]
    
    # ========== Index Management Interface ==========
    
    def create_index(
        self,
        table_name: str,
        index_config: IndexConfig,
        if_not_exists: bool = True
    ) -> bool:
        """Create index
        
        Args:
            table_name: Table name
            index_config: Index configuration
            if_not_exists: Whether to ignore if index exists
            
        Returns:
            Whether creation was successful
        """
        sql_query = index_config.to_sql(table_name)
        
        if if_not_exists:
            # Handle both "CREATE INDEX" and "CREATE UNIQUE INDEX"
            sql_query = sql_query.replace("CREATE UNIQUE INDEX", "CREATE UNIQUE INDEX IF NOT EXISTS")
            if "IF NOT EXISTS" not in sql_query:
                sql_query = sql_query.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS")
        
        try:
            # Execute pre-create SQL if needed (e.g. ALTER TABLE for BM25 parallel_workers)
            pre_sql = index_config.get_pre_create_sql(table_name)
            if pre_sql:
                self.execute_sql(pre_sql, fetch=False)
            
            self.execute_sql(sql_query, fetch=False)
            logger.info(f"Index on '{table_name}' created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False
    
    def drop_index(
        self,
        index_name: str,
        if_exists: bool = True,
        cascade: bool = False
    ) -> bool:
        """Drop index
        
        Args:
            index_name: Index name
            if_exists: Whether to ignore if index does not exist
            cascade: Whether to cascade delete
            
        Returns:
            Whether deletion was successful
        """
        sql_parts = ["DROP INDEX"]
        if if_exists:
            sql_parts.append("IF EXISTS")
        sql_parts.append(f'"{index_name}"')
        if cascade:
            sql_parts.append("CASCADE")
        
        sql_query = " ".join(sql_parts)
        
        try:
            self.execute_sql(sql_query, fetch=False)
            logger.info(f"Index '{index_name}' dropped successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to drop index '{index_name}': {e}")
            return False
    
    def list_indexes(self, table_name: str = None) -> List[Dict[str, Any]]:
        """List indexes
        
        Args:
            table_name: Optional table name to filter
            
        Returns:
            List of index information
        """
        query = """
                SELECT
                    indexname,
                    tablename,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                """
        
        params = ()
        if table_name:
            query += " AND tablename = %s"
            params = (table_name,)
        
        results = self.execute_sql(query, params)
        return results
    
    # ========== Data Operations Interface ==========
    
    def insert(
        self,
        table_name: str,
        data: List[Dict[str, Any]],
        batch_size: int = DEFAULT_BATCH_SIZE
    ) -> int:
        """Insert data
        
        Args:
            table_name: Table name
            data: List of dictionaries to insert
            batch_size: Batch size for bulk insert
            
        Returns:
            Number of inserted rows
        """
        if not data:
            logger.warning("No data to insert")
            return 0
        
        # [OK] 处理 nested 字段扁平化（首值策略）- 直接展开，不需要 mapping
        needs_flatten = any(
            isinstance(value, (dict, list))
            for doc in data
            for value in doc.values()
        )
        
        if needs_flatten:
            from opensearch_sdk.client.doc_utils import _flatten_nested_document
            data = [_flatten_nested_document(doc, None) for doc in data]  # 不传 mapping，直接展开
        
        columns = list(data[0].keys())
        column_str = ", ".join(f'"{col}"' for col in columns)
        query = f'INSERT INTO "{table_name}" ({column_str}) VALUES %s'
        
        conn = None
        db_cursor = None
        try:
            # [FIX] 使用新的连接管理模式
            with self.parent.connection.get_connection_for_operation() as conn:
                db_cursor = conn.cursor()
                
                from psycopg2.extras import execute_values
                
                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    values = [tuple(row[col] for col in columns) for row in batch]
                    
                    execute_values(db_cursor, query, values, page_size=batch_size)
                
                conn.commit()
                logger.info(f"Inserted {len(data)} rows into '{table_name}'")
                return len(data)
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to insert data: {e}")
            raise VectorDBException(f"Failed to insert data: {e}")
        finally:
            # Close the cursor
            db_cursor.close()
            self.return_connection(conn)
    
    def update(
        self,
        table_name: str,
        data: Dict[str, Any],
        condition: str,
        params: Dict = None
    ) -> int:
        """Update data
        
        Args:
            table_name: Table name
            data: Data to update
            condition: WHERE condition
            params: Condition parameters
            
        Returns:
            Number of updated rows
        """
        set_clause = ", ".join(f'"{k}" = %s' for k in data.keys())
        query = f'UPDATE "{table_name}" SET {set_clause} WHERE {condition}'
        
        query_params = list(data.values())
        if params:
            query_params.extend(params.values())
        
        conn = self.get_connection()
        db_cursor = conn.cursor
        
        try:
            db_cursor.execute(query, query_params)
            updated_count = db_cursor.rowcount
            conn.commit()
            logger.info(f"Updated {updated_count} rows in '{table_name}'")
            return updated_count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update data: {e}")
            raise VectorDBException(f"Failed to update data: {e}")
        finally:
            self.return_connection(conn)
    
    def delete(
        self,
        table_name: str,
        condition: str = None,
        ids: List = None,
        id_column: str = "id"
    ) -> int:
        """Delete data
        
        Args:
            table_name: Table name
            condition: WHERE condition
            ids: ID list (mutually exclusive with condition)
            id_column: ID column name (default "id")
            
        Returns:
            Number of deleted rows
        """
        if ids is not None:
            placeholders = ", ".join(["%s"] * len(ids))
            query = f'DELETE FROM "{table_name}" WHERE "{id_column}" IN ({placeholders})'
            params = tuple(ids)
        elif condition:
            query = f'DELETE FROM "{table_name}" WHERE {condition}'
            params = ()
        else:
            raise ValueError("Either condition or ids must be provided")
        
        conn = self.get_connection()
        db_cursor = conn.cursor
        
        try:
            db_cursor.execute(query, params)
            deleted_count = db_cursor.rowcount
            conn.commit()
            logger.info(f"Deleted {deleted_count} rows from '{table_name}'")
            return deleted_count
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete data: {e}")
            raise VectorDBException(f"Failed to delete data: {e}")
        finally:
            self.return_connection(conn)
    
    def query(
        self,
        table_name: str,
        columns: List[str] = None,
        condition: str = None,
        params: tuple = None,
        limit: int = None,
        offset: int = 0,
        order_by: str = None
    ) -> List[Dict]:
        """Query data
        
        Args:
            table_name: Table name
            columns: Columns to query (None means all columns)
            condition: WHERE condition
            params: Condition parameters
            limit: Limit on number of returned rows
            offset: Offset
            order_by: Order by field
            
        Returns:
            Query results
        """
        column_str = "*" if not columns else ", ".join(f'"{col}"' for col in columns)
        query = f'SELECT {column_str} FROM "{table_name}"'
        
        if condition:
            query += f" WHERE {condition}"
        
        if order_by:
            query += f" ORDER BY {order_by}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        if offset:
            query += f" OFFSET {offset}"
        
        return self.execute_sql(query, params)
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
    
    # ========== Search Helpers ==========
    
    def _execute_retriever(
        self,
        retriever,
        table_name: str,
        top_k: int,
        filter_condition: str = None,
        filter_params: Dict = None,
        output_columns: List[str] = None
    ) -> List[Dict]:
        """Execute a retriever and convert results to dict format."""
        results = retriever.retrieve(
            client=self.parent,  # Use parent client
            table_name=table_name,
            top_k=top_k,
            filter_condition=filter_condition,
            filter_params=filter_params,
            output_columns=output_columns
        )
        # r.data expanded first; score/source always take precedence
        return [
            {**r.data, 'id': r.id, 'score': r.score, 'source': r.source}
            for r in results
        ]
    
    # ========== Vector Search Interface ==========
    
    def vector_search(
        self,
        table_name: str,
        query_vector: List[float],
        vector_column: str = "embedding",
        top_k: int = 10,
        metric: str = "l2",
        id_column: str = "id",
        filter_condition: str = None,
        filter_params: Dict = None,
        output_columns: List[str] = None,
        use_index: bool = True,
        ef_search: int = None,
        probes: int = None,
        # RabitQ query parameters
        rbq_query_bits: int = None,
        rbq_refinek: float = None,
        rbq_sample_rows: int = None,
        # PQ query parameters
        hnsw_earlystop_threshold: int = None,
        ivfpq_kreorder: int = None,
        # DiskANN query parameters
        diskann_probes: int = None
    ) -> List[Dict]:
        """Vector search
        
        Internally uses VectorRetriever to avoid code duplication.
        Supports HNSW, IVFFlat, DiskANN indexes, and RabitQ quantization acceleration.
        
        Args:
            table_name: Table name.
            query_vector: Query vector.
            vector_column: Vector column name.
            top_k: Number of results to return.
            metric: Distance metric (l2, inner_product, cosine).
            id_column: ID column name (primary key column).
            filter_condition: SQL WHERE clause for filtering.
            filter_params: Parameters for filter condition.
            output_columns: Columns to include in output.
            use_index: Whether to use index.
            ef_search: HNSW query parameter.
            probes: IVFFlat query parameter.
            rbq_query_bits: RabitQ query vector scalar quantization bits 1~8 (default 8).
            rbq_refinek: RabitQ refinement candidate pool range 1~2000000000 (default 5.0).
            rbq_sample_rows: RabitQ delayed index data row count threshold (default DEFAULT_RABITQ_SAMPLE_ROWS).
            hnsw_earlystop_threshold: HNSW-PQ early termination threshold 160~INT32_MAX.
            ivfpq_kreorder: IVFFlat-PQ refinement candidate set size.
            diskann_probes: DiskANN query candidate set size (default 128).
        
        Returns:
            List of search results.
        
        Example:
            # Regular vector search
            results = client.vector_search("docs", query_vector, metric="cosine")
            
            # Vector search using RabitQ index (improves recall)
            results = client.vector_search(
                "docs", query_vector,
                metric="cosine",
                ef_search=DEFAULT_HNSW_EF_SEARCH,
                rbq_query_bits=8,
                rbq_refinek=10
            )
            
            # Vector search using DiskANN index
            results = client.vector_search(
                "docs", query_vector,
                metric="l2",
                diskann_probes=64
            )
        """
        retriever = VectorRetriever(
            query_vector=query_vector,
            vector_column=vector_column,
            metric=metric,
            id_column=id_column,
            use_index=use_index,
            ef_search=ef_search,
            probes=probes,
            rbq_query_bits=rbq_query_bits,
            rbq_refinek=rbq_refinek,
            rbq_sample_rows=rbq_sample_rows,
            hnsw_earlystop_threshold=hnsw_earlystop_threshold,
            ivfpq_kreorder=ivfpq_kreorder,
            diskann_probes=diskann_probes
        )
        
        return self._execute_retriever(
            retriever, table_name, top_k,
            filter_condition, filter_params, output_columns
        )
    
    # ========== Full-text Search Interface ==========
    
    def fulltext_search(
        self,
        table_name: str,
        query_text: str,
        text_column: str = "content",
        top_k: int = 10,
        id_column: str = "id",
        filter_condition: str = None,
        filter_params: Dict = None,
        output_columns: List[str] = None,
        use_bm25_taat: bool = False,
        bm25_topk: int = None,
        bm25_k1: float = None,
        bm25_b: float = None
    ) -> List[Dict]:
        """Full-text search (using openGauss BM25 index).
        
        Internally uses FullTextRetriever to avoid code duplication.
        
        Args:
            table_name: Table name.
            query_text: Query text.
            text_column: Text column name (must have a BM25 index).
            top_k: Number of results to return.
            id_column: ID column name (primary key column).
            filter_condition: SQL WHERE clause for filtering.
            filter_params: Parameters for filter condition.
            output_columns: Columns to include in output.
            use_bm25_taat: Whether to use TAAT method.
            bm25_topk: Dynamic top-k candidate set size.
            bm25_k1: BM25 k1 parameter.
            bm25_b: BM25 b parameter.
        
        Returns:
            List of search results (includes score column).
        """
        retriever = FullTextRetriever(
            query_text=query_text,
            text_column=text_column,
            id_column=id_column,
            use_bm25_taat=use_bm25_taat,
            bm25_topk=bm25_topk,
            bm25_k1=bm25_k1,
            bm25_b=bm25_b
        )
        
        return self._execute_retriever(
            retriever, table_name, top_k,
            filter_condition, filter_params, output_columns
        )
    
    # ========== Hybrid Search Interface ==========
    
    def hybrid_search(
        self,
        table_name: str,
        retrievers: List,
        top_k: int = 10,
        fusion_strategy: 'FusionStrategy' = None,
        parallel: bool = True
    ) -> List[Dict]:
        """Hybrid search (supports arbitrary multi-path recall)
        
        Args:
            table_name: Table name
            retrievers: List of retrievers [retriever1, retriever2, ...]
                       Supports multiple vector retrievers, multiple full-text retrievers, any combination
                       Each Retriever can independently configure filter/output_columns
            top_k: Number of results to return
            fusion_strategy: Fusion strategy object, default RRFFusion() (automatically distributes weights)
                           Weights configured in fusion_strategy
            parallel: Whether to execute in parallel (default True)
        
        Returns:
            Hybrid search results
        
        Examples:
            # Example 1: Default equal weight distribution
            retrievers = [
                VectorRetriever(query_vector, metric="cosine"),
               FullTextRetriever("query text")
            ]
            results = client.hybrid_search("docs", retrievers)
            
            # Example 2: Custom weights (configured in fusion strategy)
            from opensearch_sdk.retrieval import RRFFusion
            results = client.hybrid_search("docs", retrievers,
                fusion_strategy=RRFFusion(k=60, weights=[0.6, 0.4]))
            
            # Example 3: Weighted fusion (custom weights)
            from opensearch_sdk.retrieval import WeightedFusion
            results = client.hybrid_search("docs", retrievers,
                fusion_strategy=WeightedFusion(weights=[0.7, 0.3]))
        """
        # Import here to avoid circular dependency
        # Reuse project's lib implementation (psycopg2 package) using absolute import
        from psycopg2.multi_retrieval import MultiRetrievalEngine, RRFFusion
        
        if not retrievers:
            raise ValueError("retrievers list cannot be empty")
        
        # Default to RRF fusion (automatically distributes weights)
        if fusion_strategy is None:
            fusion_strategy = RRFFusion(k=60)
        
        # Create multi-retrieval engine
        engine = MultiRetrievalEngine(
            retrievers=retrievers,
            fusion_strategy=fusion_strategy
        )
        
        # Execute search (parallel)
        results = engine.search(
            client=self.parent,
            table_name=table_name,
            top_k=top_k,
            parallel=parallel
        )
        
        return results
