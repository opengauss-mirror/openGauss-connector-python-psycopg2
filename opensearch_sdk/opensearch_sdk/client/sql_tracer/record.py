import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


def _convert_datetime_value(value: Any) -> Any:
    """
    将 datetime 对象转换为 ISO 格式字符串，其他值保持不变
    :param value: 任意值
    :return: 转换后的值
    """
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    elif not isinstance(value, (str, int, float, bool, type(None))):
        return str(value)
    return value


@dataclass
class SQLTraceRecord:
    """
    单条 SQL 执行记录

    Attributes:
        sql: SQL 语句
        params: 参数列表
        start_time: 开始时间戳
        end_time: 结束时间戳
        duration_ms: 执行耗时 (毫秒)
        result_count: 返回行数
        error: 错误信息（如果有）
        context: 上下文（如 "search", "create_index"）
        sampled_results: 采样结果（前 N 行）
        metadata: 额外元数据
    """
    sql: str
    params: Optional[Tuple] = None
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    duration_ms: float = 0.0
    result_count: int = 0
    error: Optional[str] = None
    context: str = ""
    sampled_results: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        # 处理 sampled_results，确保可以 JSON 序列化
        sampled = []
        if self.sampled_results:
            for row in self.sampled_results[:10]:  # 最多显示 10 行
                if isinstance(row, (list, tuple)):
                    # 如果是元组/列表，转换其中的 datetime 对象
                    sampled.append([_convert_datetime_value(item) for item in row])
                elif isinstance(row, dict):
                    # 如果是字典，转换其中的 datetime 值
                    sampled.append({k: _convert_datetime_value(v) for k, v in row.items()})
                else:
                    sampled.append(str(row))

        return {
            'sql': self._format_sql(),
            'params': self._get_masked_params(),
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration_ms': round(self.duration_ms, 2),
            'result_count': self.result_count,
            'error': self.error,
            'context': self.context,
            'sampled_results': sampled,
            'metadata': self.metadata
        }

    def _format_sql(self) -> str:
        """格式化 SQL 语句，将 Composed 对象转换为可读字符串"""
        if not self.sql:
            return ""

        # 如果是 psycopg2.sql.Composed 对象
        if hasattr(self.sql, 'as_string'):
            try:
                # 尝试使用 as_string 方法
                from psycopg2.extensions import connection
                # 如果没有连接，尝试简单转换
                return str(self.sql)
            except Exception:
                return str(self.sql)

        return str(self.sql)

    def _format_composed(self, composed, indent: int = 0) -> str:
        """递归格式化 Composed 对象"""
        parts = []
        for item in composed:
            if hasattr(item, 'as_string'):
                # 递归处理嵌套的 Composed
                parts.append(self._format_composed(item, indent + 1))
            elif hasattr(item, '__iter__') and not isinstance(item, str):
                parts.append(self._format_composed(item, indent + 1))
            else:
                parts.append(str(item))
        return "\n".join(parts)

    def _get_masked_params(self, mask_sensitive: bool = True) -> Optional[Tuple]:
        """获取脱敏后的参数"""
        if not self.params or not mask_sensitive:
            return self.params

        # 检测敏感关键词
        sensitive_keywords = ['password', 'passwd', 'pwd', 'secret', 'token', 'api_key', 'apikey']
        sql_lower = self.sql.lower() if self.sql else ''
        is_sensitive_context = any(keyword in sql_lower for keyword in sensitive_keywords)

        # 如果 SQL 中包含敏感关键词，完全脱敏所有参数
        if is_sensitive_context:
            return tuple('***MASKED***' for _ in self.params)

        # 否则只对长字符串进行部分脱敏
        masked = []
        for param in self.params:
            if isinstance(param, str) and len(param) > 8:
                masked.append('***MASKED***')
            else:
                masked.append(param)

        return tuple(masked)
