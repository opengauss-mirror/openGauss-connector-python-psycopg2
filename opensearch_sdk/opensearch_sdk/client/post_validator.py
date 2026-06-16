import re
from typing import Any, Dict, List
from itertools import product

from opensearch_sdk.client.post_filter_mark import PostFilterMark


class PostValidator:
    """
    后验证器：对数据库返回的结果执行 Python 层验证
    
    使用场景:
    1. match_phrase 严格匹配（验证短语连续性）
    2. match_phrase with slop（验证词序和间隔）
    
    示例:
        validator = PostValidator()
        filtered_hits = validator.validate(hits, marks)
    """
    
    @staticmethod
    def validate(hits: List[Dict[str, Any]], marks: List[PostFilterMark]) -> List[Dict[str, Any]]:
        """
        对搜索结果执行后过滤
        
        :param hits: 数据库返回的原始结果
        :param marks: 后过滤标记列表
        :return: 过滤后的结果
        """
        if not marks or not hits:
            return hits
        
        # 分离不同类型的标记
        strict_marks = [
            m for m in marks 
            if m.filter_type == "match_phrase_strict" and m.requires_post_filter
        ]
        slop_marks = [
            m for m in marks 
            if m.filter_type == "match_phrase_slop" and m.requires_post_filter
        ]
        term_marks = [
            m for m in marks 
            if m.filter_type == "term_exact" and m.requires_post_filter
        ]
        
        # 如果没有必须的标记，直接返回
        if not strict_marks and not slop_marks and not term_marks:
            return hits
        
        # 执行过滤
        filtered_hits = []
        for hit in hits:
            if PostValidator._matches_all_marks(hit, strict_marks, slop_marks, term_marks):
                filtered_hits.append(hit)
        
        return filtered_hits
    
    @staticmethod
    def _matches_all_marks(
        hit: Dict[str, Any],
        strict_marks: List[PostFilterMark],
        slop_marks: List[PostFilterMark],
        term_marks: List[PostFilterMark]  # [OK] 新增 term 标记参数
    ) -> bool:
        """
        检查文档是否满足所有后过滤标记
        
        策略：
        - strict_marks: AND 逻辑（必须全部满足）
        - slop_marks: AND 逻辑（必须全部满足）
        - term_marks: AND 逻辑（必须全部满足）
        """
        # 验证严格短语
        for mark in strict_marks:
            if not PostValidator._verify_strict_phrase(hit, mark):
                return False
        
        # 验证 slop 短语
        for mark in slop_marks:
            if not PostValidator._verify_slop_phrase(hit, mark):
                return False
        
        # [OK] 验证 term 精确匹配
        for mark in term_marks:
            if not PostValidator._verify_term_exact(hit, mark):
                return False
        
        return True
    
    @staticmethod
    def _verify_strict_phrase(hit: Dict[str, Any], mark: PostFilterMark) -> bool:
        """
        验证严格短语匹配（slop=None 或 0）
        
        要求：短语必须是文档字段的连续子串（词与词之间紧密相连）
        
        示例:
            查询："quick fox"
            文档："the quick fox jumps" [OK]
            文档："the quick brown fox" [FAIL]
        """
        doc_value = hit["_source"].get(mark.field, "")
        
        if isinstance(doc_value, list):
            # 数组字段：检查是否有任何元素包含该短语作为子串
            return any(mark.phrase.lower() in str(item).lower() for item in doc_value)
        else:
            # 标量字段：使用正则表达式检查连续的单词序列
            text = str(doc_value)
            words = mark.phrase.split()
            
            if len(words) == 0:
                return True
            
            # 构建正则表达式：词 1\s+词 2\s+...
            pattern = r'\b' + r'\s+'.join(re.escape(word) for word in words) + r'\b'
            match = re.search(pattern, text, re.IGNORECASE)
            return match is not None
    
    @staticmethod
    def _verify_slop_phrase(hit: Dict[str, Any], mark: PostFilterMark) -> bool:
        """
        验证 slop 短语匹配（slop>0）
        
        允许短语中的词之间有间隔，但间隔词数不能超过 slop
        
        示例:
            查询："quick fox" slop=1
            文档："the quick brown fox jumps" [OK] (brown 是 1 个词)
            文档："the quick very brown fox" [FAIL] (very brown 是 2 个词)
        """
        if mark.slop is None or mark.slop == 0:
            # 理论上不应该调用这里，但做个 fallback
            return PostValidator._verify_strict_phrase(hit, mark)
        
        doc_value = hit["_source"].get(mark.field, "")
        text = str(doc_value)
        words = mark.phrase.split()
        
        if len(words) <= 1:
            # 单个词或空短语，直接返回 True
            return True
        
        # 找到所有词在文本中的位置
        all_positions = PostValidator._find_word_positions(text, words)
        if not all_positions:
            # 有词未出现，直接失败
            return False
        
        # 检查是否存在一种组合满足 slop 要求
        return PostValidator._check_position_combinations(text, all_positions, mark.slop)
    
    @staticmethod
    def _find_word_positions(text: str, words: List[str]) -> List[List[tuple]]:
        """
        找到每个词在文本中的所有出现位置
        
        :return: [[(start1, end1), ...], [(start2, end2), ...], ...]
        """
        all_positions = []
        for word in words:
            # 使用正则找到所有出现位置（基于单词边界，忽略大小写）
            pattern = r'\b' + re.escape(word) + r'\b'
            matches = [(m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE)]
            if not matches:
                return []  # 有词未出现，直接返回空
            all_positions.append(matches)
        
        return all_positions
    
    @staticmethod
    def _check_position_combinations(
        text: str,
        all_positions: List[List[tuple]],
        slop: int
    ) -> bool:
        """
        检查所有词的位置组合是否有一种满足 slop 要求
        
        :param text: 完整文本
        :param all_positions: [[(start1, end1), ...], [(start2, end2), ...], ...]
        :param slop: 允许的最大间隔词数
        :return: 是否满足
        """
        # 生成所有可能的组合
        for combination in product(*all_positions):
            if PostValidator._is_valid_combination(text, combination, slop):
                return True
        
        return False
    
    @staticmethod
    def _is_valid_combination(
        text: str,
        combination: List[tuple],
        slop: int
    ) -> bool:
        """
        验证单个组合是否满足 slop 要求
        
        算法：计算相邻词之间的间隔词数
        - 如果间隔 <= slop，则满足
        - 必须保持查询词的顺序（不能颠倒）
        
        :param text: 完整文本
        :param combination: [(start1, end1), (start2, end2), ...] - 按查询词顺序排列的位置
        :param slop: 允许的最大间隔词数
        :return: 是否满足
        """
        if not combination:
            return True
        
        # 计算相邻词的起始位置差
        for i in range(len(combination) - 1):
            curr_end = combination[i][1]  # 当前词的结束位置
            next_start = combination[i + 1][0]  # 下一个词的开始位置
            
            # 检查词序：下一个词必须在当前词之后
            if next_start < curr_end:
                return False  # 词序颠倒，不允许
            
            # 计算间隔的词数
            words_between = PostValidator._count_words_between(text, curr_end, next_start)
            
            if words_between > slop:
                return False
        
        return True
    
    @staticmethod
    def _count_words_between(text: str, start_pos: int, end_pos: int) -> int:
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
    
    @staticmethod
    def _verify_term_exact(hit: Dict[str, Any], mark: PostFilterMark) -> bool:
        """
        验证 term 精确匹配
        
        策略：
        - 从 _source 中获取字段值
        - 转换为字符串后进行大小写不敏感的精确匹配
        - 支持数组字段（检查是否有元素匹配）
        
        示例:
            查询：{"term": {"category": "electronics"}}
            文档：{"category": "electronics"} [OK]
            文档：{"category": "Electronics"} [OK] (忽略大小写)
            文档：{"category": "electronics store"} [FAIL] (不匹配)
        """
        doc_value = hit["_source"].get(mark.field)
        
        if doc_value is None:
            return False
        
        # 转换为小写字符串进行比较
        query_value = str(mark.phrase).lower()
        
        if isinstance(doc_value, list):
            # 数组字段：检查是否有任何元素精确匹配
            return any(str(item).lower() == query_value for item in doc_value)
        else:
            # 标量字段：精确匹配
            return str(doc_value).lower() == query_value


__all__ = ["PostValidator"]
