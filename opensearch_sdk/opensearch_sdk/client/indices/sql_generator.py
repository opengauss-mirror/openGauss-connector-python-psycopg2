from typing import Any, Dict, List, Tuple
from psycopg2 import sql
from opensearch_sdk.client.utils import normalize_identifier
from opensearch_sdk.client.constants import (
    MAX_VECTOR_DIMENSION, 
    MIN_VECTOR_DIMENSION,
    DEFAULT_IVF_NLIST,
    DEFAULT_IVF_NPROBES,
    DEFAULT_HNSW_M,
    DEFAULT_HNSW_EF_CONSTRUCTION
)
from opensearch_sdk.client.indices.helpers import validate_mapping_schema, expand_nested_fields


def generate_create_table_sql(
    validated_index: str,
    body: Dict[str, Any]
) -> Tuple[sql.Composable, List[Tuple[str, str, Dict]]]:
    """
    生成 CREATE TABLE SQL 语句
    
    :param validated_index: 标准化后的索引名
    :param body: mapping body
    :return: (SQL语句, 需要索引的字段列表)
    """
    # 验证并预处理mapping
    validate_mapping_schema(body)
    
    settings = body.get('settings', {})
    mappings = body.get('mappings', {})
    properties = mappings.get('properties', {})
    
    # 解析 BM25 配置
    bm25_config = _parse_bm25_config(settings)
    
    # 构建列定义
    columns = [sql.SQL("id VARCHAR PRIMARY KEY")]
    fields_to_index = []
    
    if properties:
        # 展开 nested 字段
        flat_fields = expand_nested_fields(properties)
        
        for field_name, field_type, field_props in flat_fields:
            validated_field = normalize_identifier(field_name, "Index column")
            
            # 检查是否需要创建索引
            should_index = field_props.get('index', True)
            if should_index:
                fields_to_index.append((field_name, field_type, field_props))
            
            # 映射字段类型到 Opensearch 类型
            column_type = _map_field_type(field_name, field_type, field_props)
            columns.append(sql.SQL("{} {}").format(
                sql.Identifier(validated_field), 
                sql.SQL(column_type)
            ))
    
    # 生成 CREATE TABLE SQL（去掉 IF NOT EXISTS，让重复创建时抛出异常）
    columns_clause = sql.SQL(", ").join(columns)
    create_table_sql = sql.SQL("CREATE TABLE {} ({})").format(
        sql.Identifier(validated_index),
        columns_clause
    )
    
    return create_table_sql, fields_to_index, bm25_config


def _map_field_type(field_name: str, field_type: str, field_props: Dict) -> str:
    """
    映射字段类型到 Opensearch 类型
    
    Args:
        field_name: 字段名（用于智能识别数组字段）
        field_type: OpenSearch 字段类型
        field_props: 字段属性
        
    Returns:
        Opensearch 列类型字符串
    """
    # [OK] 智能数组识别：如果字段名以 list/List 结尾，强制使用 TEXT 类型
    if field_name.endswith('list') or field_name.endswith('List'):
        return 'TEXT'
    
    type_map = {
        'text': 'TEXT',
        'keyword': 'TEXT',  # keyword 使用 TEXT + BM25 索引
        'long': 'BIGINT',
        'integer': 'INTEGER',
        'short': 'SHORTINT',
        'byte': 'TINYINT',
        'float': 'FLOAT4',
        'double': 'FLOAT8',
        'boolean': 'BOOLEAN',
        'date': 'TIMESTAMP',
    }
    
    if field_type in type_map:
        return type_map[field_type]
    elif field_type in ['float_vector', 'dense_vector', 'knn_vector']:
        dims = field_props.get('dims', field_props.get('dimension', 128))
        if not isinstance(dims, int) or dims < MIN_VECTOR_DIMENSION or dims > MAX_VECTOR_DIMENSION:
            dims = 128
        return f'VECTOR({dims})'
    else:
        return 'TEXT'  # Default fallback


def _bm25_config_entry(sim_config: Dict) -> Dict:
    if not isinstance(sim_config, dict) or sim_config.get('type') != 'BM25':
        return None

    k1 = sim_config.get('k1')
    b = sim_config.get('b')
    if k1 is None and b is None:
        return None

    return {
        'k1': float(k1) if k1 else 1.2,
        'b': float(b) if b else 0.75
    }


def _parse_bm25_config(settings: Dict) -> Dict:
    """解析 BM25 配置"""
    bm25_config = {}
    similarity_configs = settings.get('similarity', {})
    for sim_name, sim_config in similarity_configs.items():
        config_entry = _bm25_config_entry(sim_config)
        if config_entry:
            bm25_config[sim_name] = config_entry
    return bm25_config


def generate_index_sql(
    validated_index: str,
    field_name: str,
    field_type: str,
    field_props: Dict
) -> sql.Composable:
    """
    生成索引创建 SQL
    
    :param validated_index: 索引名
    :param field_name: 字段名
    :param field_type: 字段类型
    :param field_props: 字段属性
    :return: 索引创建 SQL
    """
    validated_field = normalize_identifier(field_name, "Index column")
    
    if field_type in ['text', 'keyword']:
        # BM25 全文索引
        index_name = sql.Identifier(f"idx_{validated_index}_{validated_field}_bm25")
        return sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING bm25({})").format(
            index_name,
            sql.Identifier(validated_index),
            sql.Identifier(validated_field)
        )
    elif field_type in ['long', 'integer', 'float', 'date', 'boolean']:
        # B-tree 索引
        index_suffix = {
            'long': 'numeric',
            'integer': 'numeric',
            'float': 'float',
            'date': 'datetime',
            'boolean': 'bool'
        }.get(field_type, 'btree')
        
        index_name = sql.Identifier(f"idx_{validated_index}_{validated_field}_{index_suffix}")
        return sql.SQL("CREATE INDEX IF NOT EXISTS {} ON {} USING btree({})").format(
            index_name,
            sql.Identifier(validated_index),
            sql.Identifier(validated_field)
        )
    elif field_type in ['float_vector', 'dense_vector', 'knn_vector']:
        # 向量索引（HNSW 或 IVF）
        return _generate_vector_index_sql(validated_index, validated_field, field_props)
    
    return None


def _generate_vector_index_sql(
    validated_index: str,
    validated_field: str,
    field_props: Dict
) -> sql.Composable:
    """生成向量索引 SQL"""
    # 提取 similarity 参数
    similarity = field_props.get('similarity', 'cosine')
    similarity_map = {
        'cosine': 'vector_cosine_ops',
        'l2_norm': 'vector_l2_ops',
        'dot_product': 'vector_ip_ops'
    }
    operator = similarity_map.get(similarity, 'vector_cosine_ops')
    
    # 检测索引类型
    method_name = field_props.get('_method_name', '')
    
    if method_name == 'ivf':
        return _generate_ivf_index_sql(validated_index, validated_field, field_props, operator)
    else:
        return _generate_hnsw_index_sql(validated_index, validated_field, field_props, operator)


def _generate_ivf_index_sql(
    validated_index: str,
    validated_field: str,
    field_props: Dict,
    operator: str
) -> sql.Composable:
    """生成 IVF 索引 SQL"""
    index_name = sql.Identifier(f"idx_{validated_index}_{validated_field}_ivf")
    
    # 提取 IVF 参数
    parameters = field_props.get('_ivf_parameters', {})
    lists = parameters.get('nlist', DEFAULT_IVF_NLIST)
    
    # 检查压缩配置
    compress_config = field_props.get('_compress_config', {})
    
    # 构建 WITH 子句
    with_params = [f"lists = {lists}"]
    
    if compress_config.get('enable_pq'):
        pq_m = compress_config.get('pq_m', 8)
        pq_ksub = compress_config.get('pq_ksub', 256)
        with_params.extend([
            "enable_pq = on",
            f"pq_m = {pq_m}",
            f"pq_ksub = {pq_ksub}"
        ])
    elif compress_config.get('enable_rabitq'):
        refine_type = compress_config.get('rabitq_refine_type', 'FP32')
        fht_enabled = compress_config.get('rabitq_fht', False)
        with_params.extend([
            "enable_rabitq = on",
            f"rabitq_refine_type = '{refine_type}'",
            f"rabitq_fht = {'on' if fht_enabled else 'off'}"
        ])
    
    with_clause = ", ".join(with_params)
    return sql.SQL(
        "CREATE INDEX IF NOT EXISTS {} ON {} USING ivfflat({} {}) WITH ({})"
    ).format(
        index_name,
        sql.Identifier(validated_index),
        sql.Identifier(validated_field),
        sql.SQL(operator),
        sql.SQL(with_clause)
    )


def _generate_hnsw_index_sql(
    validated_index: str,
    validated_field: str,
    field_props: Dict,
    operator: str
) -> sql.Composable:
    """生成 HNSW 索引 SQL"""
    index_name = sql.Identifier(f"idx_{validated_index}_{validated_field}_hnsw")
    
    # 提取 HNSW 参数
    index_options = field_props.get('index_options', {})
    m = index_options.get('m', DEFAULT_HNSW_M)
    ef_construction = index_options.get('ef_construction', DEFAULT_HNSW_EF_CONSTRUCTION)
    
    return sql.SQL(
        "CREATE INDEX IF NOT EXISTS {} ON {} USING hnsw({} {}) WITH (m={}, ef_construction={})"
    ).format(
        index_name,
        sql.Identifier(validated_index),
        sql.Identifier(validated_field),
        sql.SQL(operator),
        sql.Literal(m),
        sql.Literal(ef_construction)
    )


def generate_bm25_set_sql(bm25_config: Dict) -> List[sql.Composable]:
    """生成 BM25 参数设置 SQL"""
    set_statements = []
    for sim_name, config in bm25_config.items():
        k1 = config.get('k1', 1.2)
        b = config.get('b', 0.75)
        
        set_statements.append(sql.SQL("SET bm25_k1 = {}").format(sql.Literal(k1)))
        set_statements.append(sql.SQL("SET bm25_b = {}").format(sql.Literal(b)))
    
    return set_statements


def generate_mapping_comment_sql(validated_index: str, body: Dict) -> str:
    """生成存储 mapping 到 pg_description 的 SQL"""
    import json as json_module
    
    # 提取完整的 mapping 信息
    mappings = body.get('mappings', {})
    properties = mappings.get('properties', {})
    
    complete_mapping = {
        'properties': {},
        'dynamic_templates': mappings.get('dynamic_templates', [])
    }
    
    for field_name, field_props in properties.items():
        if isinstance(field_props, dict):
            complete_mapping['properties'][field_name] = {
                'type': field_props.get('type', 'text'),
                'dims': field_props.get('dims', field_props.get('dimension')),
                'similarity': field_props.get('similarity'),
                'index_options': field_props.get('index_options')
            }
            # 移除 None 值
            complete_mapping['properties'][field_name] = {
                k: v for k, v in complete_mapping['properties'][field_name].items() if v is not None
            }
    
    mapping_json = json_module.dumps(complete_mapping)
    return mapping_json, len(complete_mapping['properties']), len(complete_mapping['dynamic_templates'])
