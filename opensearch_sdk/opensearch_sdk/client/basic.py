"""
Opensearch兼容接口- Basic Client Module
最小化数据库客户端，仅提供连接管理和 SQL 执行能力
"""

from typing import Any, Optional

import psycopg2


class BasicClient:
    """
    基础数据库客户端 - 极简设计
    
    仅提供最底层的数据库连接和 SQL 执行能力，不包含任何业务逻辑封装。
    
    设计理念:
    - 只负责连接管理 (connect/close)
    - 只提供一个核心方法 (execute)
    - 只提供事务控制 (commit/rollback)
    - 不提供任何业务封装 (表、索引、 CRUD、搜索等由用户自己写 SQL)
    
    与 Opensearch 高级客户端的对比:
    - Opensearch: 高级抽象层，OpenSearch 兼容 API，自动管理连接，封装业务逻辑
    - BasicClient: 底层驱动层，纯 SQL 操作，手动管理连接，无业务封装
    
    适用场景:
    - 需要完全控制 SQL 的场景
    - 性能敏感的底层工具
    - 数据库运维脚本
    - 自定义 ORM 或查询构建器
    
    使用示例::
    
        # 基础使用（推荐使用环境变量或配置文件）
        import os
        client = BasicClient(
            dbname=os.getenv("DB_NAME", "mydb"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD"),  # 必须设置环境变量
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432"))
        )
        
        # 执行任意 SQL
        cursor = client.execute("SELECT version()")
        result = cursor.fetchone()
        print(f"Database version: {result[0]}")
        
        # 事务控制
        client.execute("INSERT INTO table VALUES (%s, %s)", (1, 'data'))
        client.commit()  # 手动提交
        
        # 上下文管理器
        with BasicClient(**db_config) as client:
            cursor = client.execute("SELECT * FROM table")
            results = cursor.fetchall()
        # 自动关闭连接
        
        # 向量搜索示例
        query_vector = [0.1, 0.2, 0.3]
        cursor = client.execute('''
            SELECT id, embedding <=> %s::vector AS distance
            FROM my_table
            ORDER BY embedding <=> %s::vector
            LIMIT 10
        ''', (query_vector, query_vector))
        
        results = cursor.fetchall()
    """
    
    def __init__(
        self,
        dbname: str,
        user: str,
        password: str,
        host: str = "localhost",
        port: int = 5432,
        **kwargs: Any
    ):
        """
        初始化数据库客户端
        
        :arg dbname: 数据库名称
        :arg user: 用户名
        :arg password: 密码
        :arg host: 主机地址，默认 localhost
        :arg port: 端口号，默认 5432
        :arg kwargs: 额外参数（传递给 psycopg2.connect）
        
        使用示例::
        
            import os
            client = BasicClient(
                dbname=os.getenv("DB_NAME", "test_db"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD"),  # 必须设置环境变量
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432"))
            )
        """
        self._conn_params = {
            'dbname': dbname,
            'user': user,
            'password': password,
            'host': host,
            'port': port,
            **kwargs
        }
        self.conn = None
        self._cursor = None
        
        # 建立初始连接
        self.connect()
    
    def connect(self) -> None:
        """
        建立数据库连接
        
        如果已有连接，会先关闭旧连接
        
        使用示例::
        
            client = BasicClient(**db_config)
            # 或者
            client = BasicClient(..., auto_connect=False)
            client.connect()
        """
        try:
            if self._cursor:
                self._cursor.close()
            if self.conn and not self.conn.closed:
                self.conn.close()
        except Exception:
            pass
        
        self.conn = psycopg2.connect(**self._conn_params)
        self._cursor = self.conn.cursor()
    
    def execute(self, sql: str, params: Optional[Any] = None) -> psycopg2.extensions.cursor:
        """
        执行任意 SQL 语句
        
        这是本客户端的核心方法，提供完全的 SQL 灵活性。
        
        :arg sql: SQL 语句（支持占位符 %s）
        :arg params: 参数值（可以是单个值、元组或列表）
        :return: psycopg2 cursor 对象（可调用 fetchone/fetchall 等）
        
        使用示例::
        
            # 查询
            cursor = client.execute("SELECT * FROM table WHERE id = %s", (1,))
            result = cursor.fetchone()
            
            # 插入
            cursor = client.execute(
                "INSERT INTO table (id, data) VALUES (%s, %s)",
                (1, 'value')
            )
            client.commit()  # 需要手动提交
            
            # 批量操作
            cursor = client.execute(
                "INSERT INTO table VALUES %s",
                [(1, 'a'), (2, 'b'), (3, 'c')]  # 需要配合 execute_values
            )
            client.commit()
            
            # 向量搜索
            query_vec = [0.1, 0.2, 0.3]
            cursor = client.execute('''
                SELECT id, embedding <=> %s::vector AS distance
                FROM my_table
                ORDER BY embedding <=> %s::vector
                LIMIT 10
            ''', (query_vec, query_vec))
            
            results = cursor.fetchall()
        """
        if self.conn is None or self.conn.closed:
            self.connect()
        
        cursor = self.conn.cursor()
        cursor.execute(sql, params)
        return cursor
    
    def commit(self) -> None:
        """
        提交当前事务
        
        对于 INSERT/UPDATE/DELETE 等写操作，必须显式调用 commit
        
        使用示例::
        
            client.execute("INSERT INTO table VALUES (%s, %s)", (1, 'data'))
            client.commit()  # 提交事务
        """
        if self.conn and not self.conn.closed:
            self.conn.commit()
    
    def rollback(self) -> None:
        """
        回滚当前事务
        
        发生错误时可以使用
        
        使用示例::
        
            try:
                client.execute("INSERT INTO table VALUES (%s, %s)", (1, 'data'))
            except Exception as e:
                client.rollback()  # 回滚
                raise
        """
        if self.conn and not self.conn.closed:
            self.conn.rollback()
    
    def close(self) -> None:
        """
        关闭数据库连接
        
        使用示例::
        
            client.close()
        """
        try:
            if self._cursor:
                self._cursor.close()
            if self.conn and not self.conn.closed:
                self.conn.close()
        except Exception as e:
            print(f"Error closing connection: {e}")
    
    def __enter__(self):
        """支持上下文管理器"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出时自动关闭连接"""
        self.close()
