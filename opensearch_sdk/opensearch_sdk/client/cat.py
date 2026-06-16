from typing import Any, List, Dict


class CatClient:
    """
    Cat client for Opensearch兼容接口, compatible with OpenSearch cat operations.
    
    提供类似于 OpenSearch _cat API 的功能，用于获取索引等元数据信息。
    
    使用示例::
    
        client = OpenGauss(...)
        cat_client = client.cat
        indices = cat_client.indices(output_format='json')
    """
    
    def __init__(self, client: Any) -> None:
        """
        初始化 Cat 客户端
        
        :arg client: Opensearch 客户端实例
        """
        self.client = client
    
    def indices(self, output_format: str = "text") -> Any:
        """
        获取数据库中所有索引名称
        
        :arg output_format: 输出格式 ('json' 或 'text')
                      - 'json': 返回 [{"index": "name1"}, {"index": "name2"}, ...]
                      - 'text': 返回 [name1, name2, ...]
        
        :return: 索引名称列表
                  - JSON 格式：包含索引信息的字典列表
                  - Text 格式：纯索引名称列表
        
        使用示例::
        
            # 获取文本格式
            indices = client.cat.indices()
            
            # 获取 JSON 格式
            indices_json = client.cat.indices(output_format='json')
        """
        index_names = self.client.indices.get_all_index_names()
        
        if output_format == "json":
            return [{"index": name} for name in index_names]
        else:
            return index_names
    
    def __repr__(self) -> str:
        """返回客户端的字符串表示"""
        return f"<CatClient for {self.client.__class__.__name__}>"
