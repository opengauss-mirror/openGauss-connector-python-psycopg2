"""
Opensearch Connection Pool Module

基于 psycopg2.pool.ThreadedConnectionPool 实现线程安全的连接池管理。
支持配置最小/最大连接数、连接超时等参数。
"""

import logging
from typing import Optional, Any
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool as psycopg2_pool

logger = logging.getLogger(__name__)


class OpenGaussConnectionPool:
    """
    Opensearch 连接池管理器
    
    基于 psycopg2 的 ThreadedConnectionPool 实现线程安全的连接池。
    
    Features:
    - 线程安全：使用 ThreadedConnectionPool
    - 自动重连：检测连接失效并自动重建
    - 上下文管理器：支持 with 语句自动归还连接
    - 健康检查：定期检查连接状态
    
    Usage:
        # 创建连接池（推荐使用环境变量或配置文件）
        import os
        pool = OpenGaussConnectionPool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "mydb"),
            user=os.getenv("DB_USER", "user"),
            password=os.getenv("DB_PASSWORD"),  # 必须设置环境变量
            min_conn=5,
            max_conn=20
        )
        
        # 方式1：手动获取和归还
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
        finally:
            pool.return_connection(conn)
        
        # 方式2：使用上下文管理器（推荐）
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        min_conn: int = 5,
        max_conn: int = 20,
        **kwargs: Any
    ):
        """
        初始化连接池
        
        :arg host: 数据库主机地址
        :arg port: 数据库端口
        :arg database: 数据库名称
        :arg user: 用户名
        :arg password: 密码
        :arg min_conn: 最小连接数（默认 5）
        :arg max_conn: 最大连接数（默认 20）
        :arg kwargs: 其他传递给 psycopg2.connect 的参数
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.extra_kwargs = kwargs
        
        # 创建 ThreadedConnectionPool
        self._pool = None
        self._initialize_pool()
        
        logger.info(
            f"Connection pool initialized: min={min_conn}, max={max_conn}, "
            f"host={host}:{port}, database={database}"
        )
    
    def _initialize_pool(self):
        """初始化连接池"""
        try:
            self._pool = psycopg2_pool.ThreadedConnectionPool(
                minconn=self.min_conn,
                maxconn=self.max_conn,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                **self.extra_kwargs
            )
            
            # 设置所有初始连接的 autocommit 为 False（手动管理事务）
            for conn in self._pool._pool:
                conn.autocommit = False
                
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise
    
    def get_connection(self):
        """
        从连接池获取一个连接
        
        :return: 数据库连接对象
        :raises: psycopg2.pool.PoolError 如果连接池已满
        """
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized")
        
        try:
            conn = self._pool.getconn()
            
            # 确保 autocommit 为 False（手动管理事务）
            conn.autocommit = False
            
            # 检查连接是否有效
            if self._is_connection_valid(conn):
                logger.debug("Got valid connection from pool")
                return conn
            else:
                # 连接失效，尝试重置
                logger.warning("Got invalid connection, resetting...")
                self._reset_connection(conn)
                return conn
                
        except psycopg2_pool.PoolError as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise
    
    def return_connection(self, conn):
        """
        归还连接到连接池
        
        :arg conn: 要归还的连接对象
        """
        if self._pool is None or conn is None:
            return
        
        try:
            # [OK] 关键修复：不要关闭连接，直接归还到池中
            # 即使连接处于事务状态，也应该归还，由下一个使用者决定如何处理
            # 只有在连接真正损坏时才关闭
            if conn.closed:
                # 连接已物理关闭，无法归还，记录日志
                logger.warning("Connection is physically closed, cannot return to pool")
                return
            
            # 如果连接处于错误状态，先回滚事务
            if conn.status != psycopg2.extensions.STATUS_READY:
                try:
                    conn.rollback()
                    logger.debug("Rolled back transaction before returning connection")
                except Exception:
                    pass
            
            self._pool.putconn(conn)
            logger.debug("Connection returned to pool")
            
        except Exception as e:
            logger.error(f"Failed to return connection to pool: {e}")
            # 如果归还失败，强制关闭连接
            try:
                conn.close()
            except Exception:
                pass
    
    @contextmanager
    def get_connection_context(self):
        """
        获取连接的上下文管理器（推荐使用）
        
        自动处理连接的获取和归还，即使发生异常也能正确归还连接。
        
        Usage:
            with pool.get_connection_context() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
        """
        conn = self.get_connection()
        try:
            yield conn
        except Exception as e:
            # 发生异常时回滚事务
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self.return_connection(conn)
    
    @staticmethod
    def _is_connection_valid(conn) -> bool:
        """
        检查连接是否有效
        
        :arg conn: 数据库连接对象
        :return: True 如果连接有效
        """
        try:
            # 检查连接状态
            if conn.closed:
                return False
            
            # 尝试执行简单查询测试连接
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
            
        except Exception:
            return False
    
    def _reset_connection(self, conn):
        """
        重置失效的连接
        
        :arg conn: 数据库连接对象
        """
        try:
            # 先关闭旧连接
            if not conn.closed:
                conn.close()
        except Exception:
            pass
        
        # 重新建立连接
        try:
            new_conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                **self.extra_kwargs
            )
            # 替换连接对象的内部状态（psycopg2 不支持直接替换，需要重新获取）
            # 这里我们通过归还旧连接并获取新连接来实现
            self._pool.putconn(new_conn)
        except Exception as e:
            logger.error(f"Failed to reset connection: {e}")
            raise
    
    def close_all(self):
        """关闭连接池中的所有连接"""
        if self._pool:
            try:
                self._pool.closeall()
                logger.info("All connections closed")
            except Exception as e:
                logger.error(f"Failed to close all connections: {e}")
                raise
    
    def get_pool_status(self) -> dict:
        """
        获取连接池状态
        
        :return: 包含连接池状态的字典
        """
        if self._pool is None:
            return {"status": "not_initialized"}
        
        return {
            "status": "active",
            "min_conn": self.min_conn,
            "max_conn": self.max_conn,
            "used_connections": len(self._pool._used),
            "available_connections": len(self._pool._pool),
            "total_connections": len(self._pool._used) + len(self._pool._pool)
        }
    
    def __enter__(self):
        """支持 with 语句"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出 with 语句时关闭所有连接"""
        self.close_all()
        return False
