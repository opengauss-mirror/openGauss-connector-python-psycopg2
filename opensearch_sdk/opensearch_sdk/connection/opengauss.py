import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional, Union, TYPE_CHECKING

import psycopg2

logger = logging.getLogger(__name__)

from opensearch_sdk.connection import Connection
from opensearch_sdk.connection.pool import OpenGaussConnectionPool

if TYPE_CHECKING:
    from opensearch_sdk.client.sql_tracer import SQLTracer


# PooledCursor 类已移除，改为在 _raw_execute 中直接给 cursor 添加 close 钩子

class OpenGaussConnection(Connection):
    """
    Opensearch database connection implementation.
    Supports both single connection mode and connection pool mode.

    Connection Pool Mode (recommended for production):
        - Uses ThreadedConnectionPool for thread-safe connection management
        - Automatically handles connection lifecycle
        - Supports configurable min/max connections

    Single Connection Mode (for testing/simple scenarios):
        - Uses a single persistent connection
        - Simpler but not suitable for high concurrency
    """

    def __init__(
        self,
        host: str = "localhost",
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        sql_tracer: Optional['SQLTracer'] = None,
        use_connection_pool: bool = True,
        pool_min_conn: int = 5,
        pool_max_conn: int = 20,
        **kwargs: Any,
    ) -> None:
        """
        :arg host: hostname of the database (default: localhost)
        :arg port: port to use (integer, default: 5432)
        :arg database: database name
        :arg user: username for authentication
        :arg password: password for authentication
        :arg sql_tracer: SQL 追踪器实例（可选）
        :arg use_connection_pool: 是否使用连接池（默认 True）
        :arg pool_min_conn: 连接池最小连接数（默认 5）
        :arg pool_max_conn: 连接池最大连接数（默认 20）
        :arg kwargs: additional arguments
        """
        super().__init__(host=host, port=port, **kwargs)

        if port is None:
            port = 5432

        self.database = database
        self.user = user
        self.password = password
        self.sql_tracer = sql_tracer
        self.use_connection_pool = use_connection_pool
        self.extra_kwargs = kwargs  # 保存额外参数，用于 SSL 等配置

        # Connection management
        self._local = threading.local()  # Thread-local storage for borrowed connections
        self.conn = None  # For single connection mode
        self._pool = None  # For connection pool mode

        # Initialize based on mode
        if use_connection_pool:
            self._initialize_pool(pool_min_conn, pool_max_conn, **kwargs)
        else:
            logger.info("Using single connection mode (not recommended for production)")

    def _initialize_pool(self, min_conn: int, max_conn: int, **kwargs):
        """
        初始化连接池

        :arg min_conn: 最小连接数
        :arg max_conn: 最大连接数
        :arg kwargs: 其他参数
        """
        try:
            self._pool = OpenGaussConnectionPool(
                host=self.hostname,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_conn=min_conn,
                max_conn=max_conn,
                **kwargs
            )
            logger.info(
                f"Connection pool initialized: min={min_conn}, max={max_conn}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    def connect(self) -> None:
        """
        Establish connection to Opensearch database.

        In pool mode: Initializes the connection pool (already done in __init__)
        In single mode: Creates a single persistent connection
        """
        if not self.use_connection_pool:
            # Single connection mode
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(
                    host=self.hostname,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    **self.extra_kwargs
                )
                logger.info("Single connection established")

    def close(self) -> None:
        """
        Close connection(s).

        In pool mode: Closes all connections in the pool
        In single mode: Closes the single connection
        """
        if self.use_connection_pool:
            if self._pool:
                self._pool.close_all()
                logger.info("Connection pool closed")
        else:
            if self.conn:
                self.conn.close()
                logger.info("Single connection closed")

    def cursor(self, *args, **kwargs):
        """
        Get a database cursor.

        In pool mode: obtains a connection from the pool and creates a cursor on it.
        Uses thread-local storage so each thread tracks its own borrowed connection,
        avoiding race conditions when cursor() is called concurrently on the same
        OpenGaussConnection instance.

        In single mode: creates a cursor on the persistent connection.

        :return: Database cursor object
        """
        if self.use_connection_pool:
            conn = self._get_pooled_connection()
            self._local.borrowed_conn = conn
            return conn.cursor(*args, **kwargs)
        else:
            return self.conn.cursor(*args, **kwargs)

    def _return_borrowed_connection(self, borrowed):
        """
        归还借出的连接到连接池，清理事务状态

        :arg borrowed: 要归还的借用连接
        """
        try:
            if borrowed.status != psycopg2.extensions.STATUS_READY:
                try:
                    borrowed.rollback()
                except Exception:
                    pass
            if self._pool is not None:
                self._pool.return_connection(borrowed)
        finally:
            self._local.borrowed_conn = None

    def _release_borrowed_connection(self):
        """
        Release the borrowed connection back to the pool (if applicable).

        In pool mode: returns the current thread's tracked connection to the pool.
        In single mode: no-op.
        """
        if self.use_connection_pool:
            borrowed = getattr(self._local, 'borrowed_conn', None)
            if borrowed is not None:
                self._return_borrowed_connection(borrowed)

    def commit(self) -> None:
        """
        Commit the current transaction.

        [FIX] 在连接池模式下，commit() 不再有效，必须使用上下文管理器

        In pool mode: Raises RuntimeError - use get_connection_for_operation() instead
        In single mode: Commits on the persistent connection

        :raises RuntimeError: 如果在连接池模式下调用
        """
        if self.use_connection_pool:
            raise RuntimeError(
                "commit() is not supported in connection pool mode. "
                "Each execute() uses a different connection from the pool, "
                "so commit() would commit on a wrong connection.\n\n"
                "Use get_connection_for_operation() context manager instead:\n"
                "  with client.connection.get_connection_for_operation() as conn:\n"
                "      cursor = conn.cursor()\n"
                "      cursor.execute(...)\n"
                "      conn.commit()  # Commit on the same connection"
            )
        else:
            if self.conn:
                self.conn.commit()

    def get_current_schema(self) -> str:
        """
        获取当前连接的 schema 名称

        :return: 当前 schema 名称
        """
        try:
            # [OK] 使用新的连接管理模式
            with self.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT current_schema()")
                    result = cursor.fetchone()
                    return result[0] if result else 'public'
                finally:
                    cursor.close()
        except Exception:
            return 'public'

    def rollback(self) -> None:
        """
        Rollback the current transaction.

        [FIX] 在连接池模式下，rollback() 不再有效，必须使用上下文管理器

        In pool mode: Raises RuntimeError - use get_connection_for_operation() instead
        In single mode: Rollbacks on the persistent connection

        :raises RuntimeError: 如果在连接池模式下调用
        """
        if self.use_connection_pool:
            raise RuntimeError(
                "rollback() is not supported in connection pool mode. "
                "Each execute() uses a different connection from the pool, "
                "so rollback() would rollback on a wrong connection.\n\n"
                "Use get_connection_for_operation() context manager instead:\n"
                "  with client.connection.get_connection_for_operation() as conn:\n"
                "      cursor = conn.cursor()\n"
                "      try:\n"
                "          cursor.execute(...)\n"
                "          conn.commit()\n"
                "      except Exception:\n"
                "          conn.rollback()  # Rollback on the same connection\n"
                "          raise"
            )
        else:
            if self.conn:
                self.conn.rollback()

    def execute(self, query: str, params: Optional[Union[tuple, dict]] = None, conn=None) -> Any:
        """
        Execute a query using a connection from the pool (or single connection).

        [OK] 重要：conn 参数现在是必需的！
        调用者必须先通过 get_connection_for_operation() 获取连接，然后传入

        :arg query: SQL query to execute
        :arg params: Parameters for the query
        :arg conn: REQUIRED - Database connection to use (must be provided)
        :return: Query result cursor (caller must close it!)
        """
        # [OK] conn 参数现在是必需的
        if conn is None:
            raise RuntimeError(
                "conn parameter is required. "
                "Use get_connection_for_operation() to get a connection first, then pass it to execute()."
            )
        # SQL 追踪：如果启用了追踪，包装执行过程
        if self.sql_tracer and self.sql_tracer.enabled:
            return self._execute_with_trace(query, params, conn)
        else:
            # 传入 conn，让 _raw_execute 创建 cursor
            return self._raw_execute(query, params, conn)

    def _get_pooled_connection(self):
        """
        Get a connection from the pool

        :return: Database connection from pool
        """
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized")
        return self._pool.get_connection()

    def _get_single_connection(self):
        """
        Get the single persistent connection

        :return: Single database connection
        """
        if self.conn is None or self.conn.closed:
            self.connect()
        return self.conn

    def _return_connection(self, conn):
        """
        归还连接到连接池

        执行 rollback 清理事务状态，确保连接以干净状态归还到池中。

        :arg conn: 要归还的数据库连接
        """
        if not self.use_connection_pool or conn is None:
            return

        try:
            # [FIX] 关键修复：统一使用 rollback 清理事务状态
            # 原因：
            # 1. SELECT 查询开启的事务必须用 rollback 清理（commit 无意义）
            # 2. DDL 语句已自动提交，rollback 是安全的空操作
            # 3. 避免将脏连接（status=2）归还到连接池
            if conn.status != psycopg2.extensions.STATUS_READY:
                try:
                    conn.rollback()
                except Exception as e:
                    logger.error(f"Rollback failed: {e}")

            self._pool.return_connection(conn)
        except Exception as e:
            logger.error(f"Failed to return connection: {e}")
            import traceback
            traceback.print_exc()

    @contextmanager
    def get_connection_for_operation(self):
        """
        [OK] 关键设计：为单个业务操作获取一个连接，操作结束后自动归还

        使用方式：
            with connection.get_connection_for_operation() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ...")
                # ... 其他操作都使用同一个 conn ...
                conn.commit()
            # 退出 with 时自动归还连接

        :return: 数据库连接对象
        """
        conn = None
        try:
            if self.use_connection_pool:
                conn = self._get_pooled_connection()
            else:
                conn = self._get_single_connection()

            yield conn

        finally:
            self._return_connection(conn)

    def _raw_execute(self, query: str, params: Optional[Union[tuple, dict]] = None, conn=None) -> Any:
        """
        原始执行方法（不追踪）

        [OK] 重要：此方法不再自动管理连接生命周期
        调用者应该使用 get_connection_for_operation() 来获取和管理连接

        :arg query: SQL query to execute
        :arg params: Parameters for the query
        :arg conn: Database connection (REQUIRED - must be provided by caller)
        :return: Query result cursor
        """
        import sys
        print(f"[DEBUG] _raw_execute 开始", file=sys.stderr, flush=True)

        # [OK] 关键修复：conn 参数现在是必需的
        if conn is None:
            raise RuntimeError(
                "conn parameter is required. "
                "Use get_connection_for_operation() to get a connection first."
            )

        # Create a new cursor for each query (thread-safe!)
        cursor = conn.cursor()

        try:
            print(f"[DEBUG] 执行 cursor.execute...", file=sys.stderr, flush=True)
            cursor.execute(query, params)
            print(f"[DEBUG] cursor.execute 完成", file=sys.stderr, flush=True)
        except psycopg2.errors.InFailedSqlTransaction:
            # If in a failed transaction, rollback and retry
            print(f"[DEBUG] 检测到失败的事务，回滚并重试", file=sys.stderr, flush=True)
            conn.rollback()
            cursor.execute(query, params)

        # [OK] 返回原始 cursor，由调用者负责关闭
        return cursor

    def _execute_with_trace(self, query: str, params: Optional[Union[tuple, dict]] = None, conn=None) -> Any:
        """
        带追踪的执行方法

        :arg query: SQL query to execute
        :arg params: Parameters for the query
        :arg conn: Database connection (optional)
        :return: Query result cursor
        """
        # Use provided connection or get one
        if conn is None:
            if self.use_connection_pool:
                conn = self._get_pooled_connection()
            else:
                conn = self._get_single_connection()

        # [DEBUG] 打印即将执行的 SQL
        import sys
        formatted_sql = self.sql_tracer.format_sql_object(query, conn) if self.sql_tracer else str(query)
        print(f"[SQL] 即将执行: {formatted_sql[:200]}..." if len(formatted_sql) > 200 else f"[SQL] 即将执行: {formatted_sql}", file=sys.stderr, flush=True)

        try:
            # 执行原始 SQL
            cursor = self._raw_execute(query, params, conn)

            # 记录执行信息
            # 在 execute 时已经有 connection，可以展开 Composed 对象
            formatted_sql = self.sql_tracer.format_sql_object(query, conn)
            record = self.sql_tracer.record_execution(
                cursor=cursor,
                sql=formatted_sql,  # 使用完整格式化的 SQL
                params=tuple(params) if isinstance(params, dict) else params,
                context="database_operation"
            )

            return cursor

        except Exception as e:
            # 记录错误
            formatted_sql = self.sql_tracer.format_sql_object(query, conn)
            self.sql_tracer.record_error(
                sql=formatted_sql,
                error=e,
                params=tuple(params) if isinstance(params, dict) else params,
                context="database_operation"
            )
            logger.error(f"SQL execution failed: {e}")
            raise

    def fetchone(self) -> Any:
        """
        Fetch one row from cursor.
        Note: This method is deprecated. Use the cursor returned by execute() directly.
        """
        # This method should not be used with the new cursor-per-query approach
        raise NotImplementedError("fetchone() is deprecated. Use cursor from execute() instead.")

    def fetchall(self) -> Any:
        """
        Fetch all rows from cursor.
        Note: This method is deprecated. Use the cursor returned by execute() directly.
        """
        # This method should not be used with the new cursor-per-query approach
        raise NotImplementedError("fetchall() is deprecated. Use cursor from execute() instead.")

    def _get_default_user_agent(self) -> str:
        """
        Return the default user agent string
        """
        return "opengauss-python-client/1.0.0"
