import logging
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

from .record import SQLTraceRecord
from .session import SQLTraceSession
from . import exporters

logger = logging.getLogger(__name__)


class SQLTracer:
    """
    SQL 追踪器核心类
    
    Features:
    - 线程安全的追踪上下文
    - 可配置的参数脱敏
    - 灵活的结果采样
    - 多种输出格式支持
    
    Usage:
        tracer = SQLTracer(
            enabled=True,
            mask_sensitive_params=True,
            max_sample_rows=10
        )
        
        with tracer.trace_session("search", "my_index") as session:
            # 执行 SQL 操作
            cursor = connection.execute(sql, params)
            tracer.record_execution(cursor, sql, params, "main_query")
        
        tracer.print_last_session()
        tracer.export_to_file()
    """
    
    @staticmethod
    def format_sql_object(sql_obj, connection=None) -> str:
        """格式化 SQL 对象（支持 Composed 对象）"""
        if not sql_obj:
            return ""
        
        if isinstance(sql_obj, str):
            return sql_obj.strip()
        
        if hasattr(sql_obj, 'as_string'):
            try:
                if connection is not None:
                    result = sql_obj.as_string(connection)
                else:
                    result = sql_obj.as_string(None)
                
                if result and len(result.strip()) > 10:
                    return result.strip()
            except Exception:
                pass
        
        sql_str = str(sql_obj)
        return sql_str
    
    def __init__(
        self,
        enabled: bool = False,
        mask_sensitive_params: bool = True,
        max_sample_rows: int = 10,
        store_full_results: bool = False,
        export_dir: Optional[str] = None
    ):
        """初始化 SQL 追踪器"""
        self.enabled = enabled
        self.mask_sensitive_params = mask_sensitive_params
        self.max_sample_rows = max_sample_rows
        self.store_full_results = store_full_results
        self.export_dir = Path(export_dir) if export_dir else Path.cwd() / "tmp" / "sql" / "exports"
        
        # 线程本地存储
        self._local = threading.local()
        
        # 历史会话（保留最近 100 个）
        self._sessions: List[SQLTraceSession] = []
        self._max_history = 100
        
        # 确保导出目录存在
        if self.enabled:
            self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_current_session(self) -> Optional[SQLTraceSession]:
        """获取当前线程的会话"""
        return getattr(self._local, 'current_session', None)
    
    def _set_current_session(self, session: SQLTraceSession) -> None:
        """设置当前线程的会话"""
        self._local.current_session = session
    
    @contextmanager
    def trace_session(self, operation: str, index_name: Optional[str] = None):
        """追踪会话上下文管理器"""
        if not self.enabled:
            yield None
            return
        
        session = SQLTraceSession(operation, index_name)
        self._set_current_session(session)
        
        try:
            yield session
        finally:
            session.end_time = time.time()
            self._set_current_session(None)
            
            # 保存到历史
            self._sessions.append(session)
            if len(self._sessions) > self._max_history:
                self._sessions.pop(0)
    
    def record_execution(
        self,
        cursor,
        sql: str,
        params: Optional[Tuple] = None,
        context: str = ""
    ) -> Optional[SQLTraceRecord]:
        """记录 SQL 执行（只记录元信息，不采样数据）"""
        if not self.enabled:
            return None
        
        session = self._get_current_session()
        if not session:
            return None
        
        start_time = time.time()
        
        # [OK] 只记录 rowcount，不采样数据
        result_count = 0
        if cursor and hasattr(cursor, 'rowcount') and cursor.rowcount >= 0:
            result_count = cursor.rowcount
        
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000
        
        record = SQLTraceRecord(
            sql=sql,
            params=params,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            result_count=result_count,
            context=context,
            sampled_results=[]  # 不采样数据
        )
        
        session.add_record(record)
        return record
    
    def record_error(
        self,
        sql: str,
        error: Exception,
        params: Optional[Tuple] = None,
        context: str = ""
    ) -> Optional[SQLTraceRecord]:
        """记录 SQL 执行错误"""
        if not self.enabled:
            return None
        
        session = self._get_current_session()
        if not session:
            return None
        
        record = SQLTraceRecord(
            sql=sql,
            params=params,
            start_time=time.time(),
            end_time=time.time(),
            duration_ms=0,
            error=str(error),
            context=context
        )
        
        record.duration_ms = (record.end_time - record.start_time) * 1000
        session.add_record(record)
        
        return record
    
    def get_last_session(self) -> Optional[SQLTraceSession]:
        """获取最后一次会话"""
        if not self._sessions:
            return None
        return self._sessions[-1]
    
    def get_sessions(self, limit: int = 10) -> List[SQLTraceSession]:
        """获取历史会话列表"""
        return self._sessions[-limit:]
    
    def clear_history(self) -> None:
        """清空历史会话"""
        self._sessions.clear()
    
    def print_last_session(self, verbose: bool = False) -> None:
        """打印最后一次会话到控制台"""
        session = self.get_last_session()
        if not session:
            print("No SQL trace session available")
            return
        
        self._print_session(session, verbose)
    
    @staticmethod
    def _print_session(session: SQLTraceSession, verbose: bool = False) -> None:
        """打印会话详情（YAML 风格）"""
        yaml_output = session.to_yaml_style()
        print(yaml_output)
        
        if verbose:
            print("\n" + "=" * 80)
            print("详细信息:")
            print("=" * 80)
            for i, record in enumerate(session.records, 1):
                print(f"\n[SQL {i}] {record.context}")
                print(f"  Duration: {record.duration_ms:.2f}ms")
                print(f"  Result Count: {record.result_count}")
                if record.error:
                    print(f"  Error: {record.error}")
    
    def export_to_file(
        self,
        export_format: str = "markdown",
        filename: Optional[str] = None,
        verbose: bool = False
    ) -> str:
        """导出会话到文件"""
        session = self.get_last_session()
        if not session:
            raise ValueError("No session to export")
        
        # 生成文件名
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = "md" if export_format.lower() == "markdown" else export_format
            filename = f"{timestamp}_{session.operation}_{session.index_name or 'unknown'}.{ext}"
        
        filepath = self.export_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # 导出
        if export_format.lower() == "markdown":
            content = exporters.export_markdown(session, verbose)
        elif export_format.lower() == "json":
            content = exporters.export_json(session)
        elif export_format.lower() == "sql":
            content = exporters.export_sql(session)
        elif export_format.lower() == "yaml":
            content = exporters.export_yaml(session)
        else:
            raise ValueError(f"Unsupported format: {export_format}")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Exported SQL trace to {filepath}")
        return str(filepath)
    
    def export_all_sessions(
        self,
        export_format: str = "markdown",
        filename_prefix: Optional[str] = None
    ) -> str:
        """导出所有会话到文件"""
        all_sessions = self._sessions
        
        if not all_sessions:
            raise ValueError("No sessions to export")
        
        # 生成文件名
        timestamp = int(datetime.now().timestamp())
        if not filename_prefix:
            filename_prefix = f"{timestamp}_full_workflow"
        
        ext_map = {
            'markdown': 'md',
            'json': 'json',
            'sql': 'sql',
            'yaml': 'yaml'
        }
        ext = ext_map.get(export_format.lower(), export_format)
        filename = f"{filename_prefix}.{ext}"
        
        filepath = self.export_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # 根据格式导出
        if export_format.lower() == "markdown":
            content = exporters.export_all_markdown(all_sessions)
        elif export_format.lower() == "sql":
            content = exporters.export_all_sql(all_sessions)
        elif export_format.lower() == "yaml":
            content = exporters.export_all_yaml(all_sessions)
        else:
            raise ValueError(f"Unsupported format: {export_format}")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Exported all sessions to {filepath}")
        return str(filepath)


# 全局追踪器实例（可选）
_global_tracer: Optional[SQLTracer] = None


def get_global_tracer() -> Optional[SQLTracer]:
    """获取全局追踪器实例"""
    return _global_tracer


def set_global_tracer(tracer: SQLTracer) -> None:
    """设置全局追踪器实例"""
    global _global_tracer
    _global_tracer = tracer


# 便捷的上下文管理器（独立于类）
@contextmanager
def trace_context(operation: str, index_name: Optional[str] = None, tracer: Optional[SQLTracer] = None):
    """独立的追踪上下文管理器"""
    if tracer is None:
        tracer = get_global_tracer()
    
    if tracer is None or not tracer.enabled:
        yield None
        return
    
    with tracer.trace_session(operation, index_name) as session:
        yield session


__all__ = [
    'SQLTracer',
    'trace_context',
    'get_global_tracer',
    'set_global_tracer'
]
