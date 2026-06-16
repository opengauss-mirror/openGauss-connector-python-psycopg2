import json
from datetime import datetime
from typing import Optional
from .session import SQLTraceSession


def _format_sql_with_params(sql_text: str, params) -> str:
    formatted_sql = sql_text
    for param in (params or []):
        replacement = f"'{param}'" if isinstance(param, str) else str(param)
        formatted_sql = formatted_sql.replace('%s', replacement, 1)
    return formatted_sql


def _append_sql_record(lines: list, record, label: str, result_suffix: str = " rows") -> None:
    lines.append(f"-- SQL {label}: {record.context}")
    lines.append(f"-- Duration: {record.duration_ms:.2f}ms, Results: {record.result_count}{result_suffix}")

    sql_text = record.sql.strip()
    lines.append(sql_text)
    if sql_text.upper().startswith('SELECT') and record.params:
        lines.append(f"-- Parameters: {record.params}")
        try:
            lines.append(f"-- Formatted: {_format_sql_with_params(sql_text, record.params)}")
        except Exception:
            pass

    if record.sampled_results:
        lines.append(f"-- Sampled results ({len(record.sampled_results)} rows):")
        for j, row in enumerate(record.sampled_results[:5], 1):
            lines.append(f"--   {j}. {row}")
        if len(record.sampled_results) > 5:
            lines.append(f"--   ... and {len(record.sampled_results) - 5} more rows")


def export_markdown(session: SQLTraceSession, verbose: bool = False) -> str:
    """导出为 Markdown 格式"""
    lines = []
    
    # 标题
    lines.append("# SQL Trace Report\n")
    lines.append(f"**Session ID**: `{session.session_id}`\n")
    lines.append(f"**Operation**: {session.operation}\n")
    lines.append(f"**Index**: {session.index_name or 'N/A'}\n")
    lines.append(f"**Total Duration**: {session.total_duration_ms:.2f}ms\n")
    lines.append(f"**SQL Count**: {len(session.records)}\n")
    lines.append(f"**Generated At**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("\n---\n")
    
    # SQL 详情
    for i, record in enumerate(session.records, 1):
        status = "[FAIL] ERROR" if record.error else "[OK] SUCCESS"
        duration_str = f"{record.duration_ms:.1f}ms"
        
        lines.append(f"\n## SQL {i}/{len(session.records)}: {record.context.upper()}\n")
        lines.append(f"- **Status**: {status}")
        lines.append(f"- **Duration**: {duration_str}")
        lines.append(f"- **Result**: {record.result_count} rows\n")
        
        lines.append("```sql")
        lines.append(record.sql.strip())
        lines.append("```\n")
        
        if record.params:
            masked_params = record._get_masked_params(True)
            lines.append("**Parameters:**\n")
            lines.append(f"```python\n{masked_params}\n```\n")
        
        if verbose and record.sampled_results:
            lines.append("**Sampled Results:**\n")
            lines.append("```")
            for row in record.sampled_results[:10]:
                lines.append(str(row))
            if len(record.sampled_results) > 10:
                lines.append(f"... and {len(record.sampled_results) - 10} more rows")
            lines.append("```\n")
        
        if record.error:
            lines.append(f"**Error**: {record.error}\n")
        
        lines.append("\n---\n")
    
    return "\n".join(lines)


def export_json(session: SQLTraceSession) -> str:
    """导出为 JSON 格式"""
    data = session.to_dict()
    data['exported_at'] = datetime.now().isoformat()
    data['mask_sensitive_params'] = True
    
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_sql(session: SQLTraceSession) -> str:
    """导出为可执行的 SQL 脚本"""
    lines = []
    lines.append("-- SQL Trace Export")
    lines.append(f"-- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"-- Index: {session.index_name or 'N/A'}")
    lines.append(f"-- Operation: {session.operation}")
    lines.append(f"-- Total SQL statements: {len(session.records)}")
    lines.append("")
    lines.append("-- ========================================")
    lines.append("-- Usage:")
    lines.append("-- 1. Execute this script in your database")
    lines.append("-- 2. It will recreate the table structure and data")
    lines.append("-- 3. Query examples are included at the end")
    lines.append("-- ========================================")
    lines.append("")
    
    for i, record in enumerate(session.records, 1):
        _append_sql_record(lines, record, str(i), " rows")
        lines.append("")
    
    return '\n'.join(lines)


def export_yaml(session: SQLTraceSession) -> str:
    """导出为 YAML 格式（简洁版）"""
    return session.to_yaml_style()


def export_all_markdown(sessions: list) -> str:
    """导出所有会话为 Markdown"""
    lines = []
    lines.append("# Full Workflow SQL Trace Report\n")
    lines.append(f"**Generated at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"**Total sessions**: {len(sessions)}\n")
    lines.append("\n---\n")
    
    for session_idx, session in enumerate(sessions, 1):
        lines.append(f"\n## Stage {session_idx}: {session.operation.upper()}\n")
        lines.append(f"- **Index**: {session.index_name or 'N/A'}")
        lines.append(f"- **Total duration**: {session.total_duration_ms:.2f}ms")
        lines.append(f"- **SQL count**: {len(session.records)}\n")
        
        for i, record in enumerate(session.records, 1):
            status = "[OK] SUCCESS" if not record.error else "[FAIL] ERROR"
            lines.append(f"\n### SQL {session_idx}-{i}: {record.context}\n")
            lines.append(f"- **Status**: {status}")
            lines.append(f"- **Duration**: {record.duration_ms:.2f}ms")
            lines.append(f"- **Results**: {record.result_count} rows\n")
            lines.append("```sql")
            lines.append(record.sql.strip())
            lines.append("```\n")
            
            if record.params:
                lines.append("**Parameters:**\n```python")
                lines.append(str(record.params))
                lines.append("```\n")
        
        lines.append("\n---\n")
    
    return '\n'.join(lines)


def export_all_sql(sessions: list) -> str:
    """导出所有会话为可执行 SQL 脚本"""
    lines = []
    lines.append("-- Full Workflow SQL Script")
    lines.append(f"-- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"-- Total sessions: {len(sessions)}")
    lines.append("")
    lines.append("-- ========================================")
    lines.append("-- Usage:")
    lines.append("-- 1. Execute this script in your database")
    lines.append("-- 2. It will recreate tables, indexes, and data")
    lines.append("-- 3. Query examples are included")
    lines.append("-- ========================================")
    lines.append("")
    
    for session_idx, session in enumerate(sessions, 1):
        lines.append(f"-- ========== Stage {session_idx}: {session.operation.upper()} ==========")
        lines.append(f"-- Duration: {session.total_duration_ms:.2f}ms, SQL count: {len(session.records)}")
        lines.append("")
        
        for i, record in enumerate(session.records, 1):
            _append_sql_record(lines, record, f"{session_idx}-{i}", "")
            lines.append("")
        
        lines.append("")
    
    return '\n'.join(lines)


def export_all_yaml(sessions: list) -> str:
    """导出所有会话为 YAML 格式"""
    lines = []
    lines.append("# Full Workflow SQL Trace")
    lines.append(f"generated_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"total_sessions: {len(sessions)}")
    lines.append("")
    
    for session_idx, session in enumerate(sessions, 1):
        lines.append(f"- operation: {session.operation}")
        lines.append(f"  index: {session.index_name or 'N/A'}")
        lines.append(f"  total_time_ms: {session.total_duration_ms:.2f}")
        lines.append(f"  sql_count: {len(session.records)}")
        lines.append(f"  records:")
        
        for i, record in enumerate(session.records, 1):
            lines.append(f"    - context: {record.context}")
            lines.append(f"      duration_ms: {record.duration_ms:.2f}")
            lines.append(f"      result_count: {record.result_count}")
            lines.append(f"      sql: |")
            for line in record.sql.strip().split('\n'):
                lines.append(f"        {line}")
            
            if record.params:
                lines.append(f"      params: {record.params}")
            
            if record.sampled_results:
                lines.append(f"      sampled_results: {len(record.sampled_results)} rows")
        
        lines.append("")
    
    return '\n'.join(lines)
