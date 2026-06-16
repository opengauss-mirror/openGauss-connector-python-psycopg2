import time
import uuid
from typing import Any, Dict, List
from .record import SQLTraceRecord


class SQLTraceSession:
    """
    SQL 追踪会话，记录一次完整操作中的所有 SQL
    
    Attributes:
        session_id: 会话唯一ID
        operation: 操作类型（如 "search", "create_index"）
        index_name: 索引名称
        start_time: 开始时间戳
        end_time: 结束时间戳
        records: SQL 执行记录列表
    """
    
    def __init__(self, operation: str, index_name: str = None, session_id: str = None):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.operation = operation
        self.index_name = index_name
        self.start_time = time.time()
        self.end_time = 0.0
        self.records: List[SQLTraceRecord] = []
    
    @property
    def total_duration_ms(self) -> float:
        """总耗时（毫秒）- 所有记录的duration之和"""
        return sum(r.duration_ms for r in self.records)
    
    def add_record(self, record: SQLTraceRecord) -> None:
        """添加 SQL 记录"""
        self.records.append(record)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'session_id': self.session_id,
            'operation': self.operation,
            'index_name': self.index_name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_duration_ms': round(self.total_duration_ms, 2),
            'record_count': len(self.records),  # 添加 record_count
            'sql_count': len(self.records),
            'records': [r.to_dict() for r in self.records]
        }
    
    def to_yaml_style(self) -> str:
        """转换为 YAML 风格字符串"""
        lines = []
        lines.append(f"session_id: {self.session_id}")
        lines.append(f"operation: {self.operation}")
        lines.append(f"index: {self.index_name or 'N/A'}")
        lines.append(f"total_time_ms: {self.total_duration_ms:.2f}")
        lines.append(f"sql_count: {len(self.records)}")
        lines.append("")
        
        for i, record in enumerate(self.records, 1):
            status = "[OK]" if not record.error else "[FAIL]"
            lines.append(f"- [{status}] SQL {i}: {record.context}")
            lines.append(f"  duration_ms: {record.duration_ms:.2f}")
            lines.append(f"  result_count: {record.result_count}")
            
            # SQL 语句（多行）
            lines.append(f"  sql: |")
            for line in record.sql.strip().split('\n'):
                lines.append(f"    {line}")
            
            # 参数
            if record.params:
                masked = record._get_masked_params(True)
                lines.append(f"  params: {masked}")
            
            # 错误信息
            if record.error:
                lines.append(f"  error: {record.error}")
            
            lines.append("")
        
        return '\n'.join(lines)
    
    def get_summary(self) -> str:
        """获取会话摘要"""
        success_count = sum(1 for r in self.records if not r.error)
        fail_count = len(self.records) - success_count
        
        summary = f"Session {self.session_id} ({self.operation})\n"
        summary += f"  Index: {self.index_name or 'N/A'}\n"
        summary += f"  Duration: {self.total_duration_ms:.2f}ms\n"
        summary += f"  SQL Count: {len(self.records)}\n"
        summary += f"  Success: {success_count}, Failed: {fail_count}\n"
        
        return summary
