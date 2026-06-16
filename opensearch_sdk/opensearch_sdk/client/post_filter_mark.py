from dataclasses import dataclass, field
from typing import Any, Dict, Optional
try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


@dataclass
class PostFilterMark:
    """
    后过滤标记
    
    用于标识某个查询条件是否需要 Python 层后过滤
    
    示例:
        # Match Phrase 严格匹配
        mark = PostFilterMark(
            filter_type="match_phrase_strict",
            field="title",
            phrase="quick fox",
            slop=None
        )
        
        # Match Phrase 宽松匹配（slop>0）
        mark = PostFilterMark(
            filter_type="match_phrase_slop",
            field="title",
            phrase="quick fox",
            slop=1
        )
    """
    
    # 标记类型
    filter_type: Literal[
        "match_phrase_strict", 
        "match_phrase_slop",
        "term_exact"  # [OK] term 精确匹配验证
    ]
    
    # 查询信息
    field: str
    phrase: str
    
    # slop参数（OpenSearch 标准）
    # None 或 0 表示严格匹配
    slop: Optional[int] = None
    
    # 所在嵌套层级（0 表示顶层）
    nesting_level: int = 0
    
    # 所属 bool 子句类型
    bool_type: Optional[Literal["must", "should", "must_not", "filter"]] = None
    
    # 是否需要后过滤
    # - match_phrase_strict in must: True
    # - match_phrase_strict in should: False (SQL 可处理)
    # - match_phrase_slop (anywhere): True (SQL 无法表达)
    # - match_phrase in must_not: False (SQL 已处理)
    requires_post_filter: bool = True
    
    def __post_init__(self):
        """初始化后的自动处理"""
        # 根据规则自动设置 requires_post_filter
        if self.bool_type == "must_not":
            # Must Not 中的条件不需要后过滤（SQL 已处理）
            self.requires_post_filter = False
        elif self.filter_type == "match_phrase_slop":
            # Slop > 0 必须后过滤（SQL 无法表达）
            self.requires_post_filter = True
        elif self.filter_type == "match_phrase_strict" and self.bool_type == "should":
            # Should 中的严格短语可选（SQL 可处理 OR 逻辑）
            self.requires_post_filter = False
        elif self.filter_type == "term_exact":
            # [OK] term 精确匹配：顶层查询需要后过滤，bool 中不需要
            self.requires_post_filter = (self.bool_type is None)
        else:
            # 其他情况需要后过滤
            self.requires_post_filter = True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "filter_type": self.filter_type,
            "field": self.field,
            "phrase": self.phrase,
            "slop": self.slop,
            "nesting_level": self.nesting_level,
            "bool_type": self.bool_type,
            "requires_post_filter": self.requires_post_filter
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PostFilterMark":
        """从字典创建"""
        return cls(**data)


__all__ = ["PostFilterMark"]
