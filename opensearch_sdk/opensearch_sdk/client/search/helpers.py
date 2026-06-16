import re
from typing import Any, List, Tuple, Optional, Dict

from psycopg2 import sql

from opensearch_sdk.client.doc_utils.nested_handler import _reconstruct_nested_structure
from opensearch_sdk.client.utils import normalize_identifier


def reconstruct_nested_structure(source: dict) -> dict:
    """将扁平化的 nested 字段还原为嵌套结构。"""
    return _reconstruct_nested_structure(source)


def verify_match_phrase(doc_value: Any, phrase: str) -> bool:
    """
    验证短语是否是文档值的连续子串（match_phrase 的精确匹配）
    
    :param doc_value: 文档字段值
    :param phrase: 查询短语
    :return: 如果是连续子串返回 True
    """
    if isinstance(doc_value, list):
        # 数组字段：检查是否有任何元素包含该短语作为子串
        return any(phrase.lower() in str(item).lower() for item in doc_value)
    else:
        # 标量字段：直接检查
        return phrase.lower() in str(doc_value).lower()


def match_column_patterns(columns: List[str], pattern: str) -> List[str]:
    """
    匹配列名模式（支持通配符 *）
    
    :param columns: 所有列名列表
    :param pattern: 匹配模式（如 "user_*", "*name"）
    :return: 匹配的列名列表
    """
    import fnmatch
    # 将 OpenSearch 风格的 * 转换为 fnmatch 的 *
    return fnmatch.filter(columns, pattern)


def verify_match_phrase_with_gap(doc_value: Any, phrase: str, gap: int) -> bool:
    """
    验证文档是否满足 match_phrase 条件（支持 gap 参数）
    
    :param doc_value: 文档字段值
    :param phrase: 查询短语（如 "quick fox"）
    :param gap: 允许的最大间隔词数
    :return: 是否满足条件
    """
    text = str(doc_value)
    words = phrase.split()
    
    if len(words) <= 1:
        return True  # 单个词或空短语，直接返回 True
    
    # 找到所有词的位置（基于单词边界）
    all_positions = []
    for word in words:
        # 使用正则找到所有出现位置（按单词边界，忽略大小写）
        pattern = r'\b' + re.escape(word) + r'\b'
        matches = [(m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE)]
        if not matches:
            return False  # 有词未出现，直接失败
        all_positions.append(matches)
    
    # 检查是否存在一种组合满足 gap 要求
    return check_position_combinations(text, all_positions, gap)


def check_position_combinations(text: str, all_positions: List[List[Tuple[int, int]]], gap: int) -> bool:
    """
    检查所有词的位置组合是否有一种满足 gap 要求
    
    :param text: 完整文本
    :param all_positions: [[(start1, end1), ...], [(start2, end2), ...], ...]
    :param gap: 允许的最大间隔词数
    :return: 是否满足
    """
    from itertools import product
    
    # 生成所有可能的组合
    for combination in product(*all_positions):
        if is_valid_combination(text, combination, gap):
            return True
    
    return False


def count_words_between(text: str, start_pos: int, end_pos: int) -> int:
    """
    计算文本中两个位置之间的单词数
    
    :param text: 完整文本
    :param start_pos: 起始位置（第一个词的结束）
    :param end_pos: 结束位置（第二个词的开始）
    :return: 间隔的单词数
    """
    if start_pos >= end_pos:
        return 0
    
    # 提取中间的文本
    between_text = text[start_pos:end_pos]
    
    # 使用正则分词，计算单词数
    words = re.findall(r'\b\w+\b', between_text)
    return len(words)


def is_valid_combination(text: str, combination: List[Tuple[int, int]], gap: int) -> bool:
    """
    验证单个组合是否满足 gap 要求
    
    算法：计算相邻词之间的间隔词数
    - 如果间隔 <= gap，则满足
    - 必须保持查询词的顺序（不能颠倒）
    
    :param text: 完整文本
    :param combination: [(start1, end1), (start2, end2), ...] - 按查询词顺序排列的位置
    :param gap: 允许的最大间隔词数
    :return: 是否满足
    """
    if not combination:
        return True
    
    # 计算相邻词的起始位置差
    for i in range(len(combination) - 1):
        curr_end = combination[i][1]  # 当前词的结束位置
        next_start = combination[i + 1][0]  # 下一个词的起始位置
        
        # 检查词序：下一个词必须在当前词之后
        if next_start < curr_end:
            return False  # 词序颠倒，不允许
        
        # 使用精确的方法计算间隔的词数
        words_between = count_words_between(text, curr_end, next_start)
        
        if words_between > gap:
            return False
    
    return True


def build_must_not_condition(clause: Dict[str, Any]) -> Tuple[Optional[sql.Composable], Any]:
    """
    为 must_not 子句生成 NOT ILIKE SQL 条件
    
    根据测试文件 test_sql_must_not_filter.py 的验证结果：
    - text/keyword 字段：使用 NOT ILIKE '%value%'
    - term 查询：使用 NOT ILIKE
    - match/match_phrase 查询：使用 NOT ILIKE
    
    :param clause: must_not 子句
    :return: (SQL 条件，参数)
    """
    if "match_phrase" in clause:
        field, value = next(iter(clause["match_phrase"].items()))
        validated_field = normalize_identifier(field, "Sort field")
        # 使用 NOT ILIKE 进行模糊匹配
        condition = sql.SQL("{} NOT ILIKE %s").format(sql.Identifier(validated_field))
        return condition, f'%{value}%'
    
    elif "match" in clause:
        field, value = next(iter(clause["match"].items()))
        validated_field = normalize_identifier(field, "Sort field")
        # 使用 NOT ILIKE 进行模糊匹配
        condition = sql.SQL("{} NOT ILIKE %s").format(sql.Identifier(validated_field))
        return condition, f'%{value}%'
    
    elif "term" in clause:
        field, value = next(iter(clause["term"].items()))
        validated_field = normalize_identifier(field, "Sort field")
        # 使用 NOT ILIKE 进行模糊匹配（兼容数组字段）
        condition = sql.SQL("{} NOT ILIKE %s").format(sql.Identifier(validated_field))
        return condition, f'%{value}%'
    
    elif "terms" in clause:
        field, values = next(iter(clause["terms"].items()))
        validated_field = normalize_identifier(field, "Sort field")
        # 多个值使用 NOT IN
        placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(values))
        condition = sql.SQL("{} NOT IN ({})").format(sql.Identifier(validated_field), placeholders)
        return condition, values
    
    return None, None


def matches_clause(doc: Dict[str, Any], clause: Dict[str, Any]) -> bool:
    """
    检查文档是否匹配某个查询子句（用于 must_not 过滤）
    
    :param doc: 文档数据
    :param clause: 查询子句
    :return: 如果匹配返回 True
    """
    # 处理 match_phrase
    if "match_phrase" in clause:
        field, value = next(iter(clause["match_phrase"].items()))
        doc_value = doc.get(field)
        
        if doc_value is None:
            return False
        
        # 转换为字符串进行匹配
        query_str = str(value).lower()
        
        if isinstance(doc_value, list):
            # 数组字段：检查是否有任何元素包含查询词
            return any(query_str in str(item).lower() for item in doc_value)
        else:
            # 标量字段：直接检查
            return query_str in str(doc_value).lower()
    
    # 处理 term
    elif "term" in clause:
        field, value = next(iter(clause["term"].items()))
        doc_value = doc.get(field)
        
        if doc_value is None:
            return False
        
        # [OK] 多值字段用空格分隔，检查是否包含该词
        doc_str = str(doc_value).lower()
        query_str = str(value).lower()
        
        # 精确匹配：检查是否为独立单词（前后有空格或是整个字符串）
        # 例如："sale new" 应该匹配 "sale" 但不匹配 "sales"
        words = doc_str.split()
        return query_str in words
    
    # 处理 terms
    elif "terms" in clause:
        field, values = next(iter(clause["terms"].items()))
        doc_value = doc.get(field)
        
        if doc_value is None:
            return False
        
        # [OK] 多值字段用空格分隔，检查是否包含任一值
        doc_str = str(doc_value).lower()
        words = doc_str.split()
        
        # 检查是否有任一查询词在文档中
        return any(str(v).lower() in words for v in values)
    
    # 处理 match（简化版本）
    elif "match" in clause:
        field, value = next(iter(clause["match"].items()))
        doc_value = doc.get(field)
        
        if doc_value is None:
            return False
        
        query_str = str(value).lower()
        
        if isinstance(doc_value, list):
            return any(query_str in str(item).lower() for item in doc_value)
        else:
            return query_str in str(doc_value).lower()
    
    return False
