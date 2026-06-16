from typing import Any, Dict, List, Tuple


# 全局配置：是否启用 Python 端参数校验
ENABLE_PYTHON_VALIDATION = True
SUPPORTED_BASE_TYPES = {
    'text', 'keyword', 'long', 'integer', 'float',
    'boolean', 'date', 'float_vector', 'dense_vector', 'knn_vector', 'nested'
}
VECTOR_TYPES = {'float_vector', 'dense_vector', 'knn_vector'}


def set_validation_enabled(enabled: bool):
    """设置是否启用 Python 端参数校验"""
    global ENABLE_PYTHON_VALIDATION
    ENABLE_PYTHON_VALIDATION = enabled


def get_validation_enabled() -> bool:
    """获取当前 Python 端参数校验的启用状态"""
    return ENABLE_PYTHON_VALIDATION


def _is_valid_type(field_type: str) -> bool:
    return field_type in SUPPORTED_BASE_TYPES


def _validate_mapping_body(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("Mapping body must be a dictionary")
    if 'mappings' not in body:
        raise ValueError("Mapping must contain 'mappings' key")

    mappings = body['mappings']
    if not isinstance(mappings, dict):
        raise ValueError("'mappings' must be a dictionary")
    if 'properties' not in mappings:
        raise ValueError("Mapping must contain 'properties' key under 'mappings'")
    if not isinstance(mappings['properties'], dict):
        raise ValueError("'properties' must be a dictionary")
    if len(mappings['properties']) == 0:
        raise ValueError("'properties' cannot be empty")
    return mappings


def _normalize_properties(properties: dict, context: str) -> dict:
    from opensearch_sdk.client.utils import normalize_identifier

    normalized_properties = {}
    for field_name, field_props in properties.items():
        normalized_name = normalize_identifier(field_name, context)
        normalized_properties[normalized_name] = field_props
    return normalized_properties


def _replace_properties_if_normalized(container: dict, normalized_properties: dict) -> dict:
    properties = container['properties']
    if len(normalized_properties) != len(properties) or \
       set(normalized_properties.keys()) != set(properties.keys()):
        container['properties'] = normalized_properties
        return normalized_properties
    return properties


def _validate_field_config(field_name: str, field_props: dict) -> str:
    from opensearch_sdk.client.utils import normalize_identifier, _validate_identifier

    normalized_field = normalize_identifier(field_name, "Mapping field")
    _validate_identifier(normalized_field)

    if not isinstance(field_props, dict):
        raise ValueError(f"Field '{field_name}' configuration must be a dictionary")
    if 'type' not in field_props:
        raise ValueError(f"Field '{field_name}' must specify 'type'")

    field_type = field_props['type']
    if not isinstance(field_type, str):
        raise ValueError(f"Field '{field_name}' type must be a string")
    return field_type


def _validate_supported_type(field_name: str, field_type: str) -> None:
    if not _is_valid_type(field_type):
        raise ValueError(f"Field '{field_name}' has unsupported type '{field_type}'. "
                       f"Supported types: {', '.join(sorted(SUPPORTED_BASE_TYPES))}")


def _normalize_nested_field(field_name: str, field_props: dict) -> None:
    if 'properties' not in field_props:
        raise ValueError(f"Nested field '{field_name}' must contain 'properties' key")

    normalized_nested = _normalize_properties(
        field_props.get('properties', {}),
        f"Nested field '{field_name}'"
    )
    if len(normalized_nested) != len(field_props['properties']) or \
       set(normalized_nested.keys()) != set(field_props['properties'].keys()):
        field_props['properties'] = normalized_nested

    _validate_nested_properties(field_props['properties'], field_name)


def _apply_knn_similarity(field_props: dict) -> None:
    space_type = field_props.get('space_type')
    similarity = field_props.get('similarity')
    if space_type:
        space_to_similarity = {
            'l2': 'l2_norm',
            'cosinesimil': 'cosine',
            'innerproduct': 'dot_product'
        }
        field_props['similarity'] = space_to_similarity.get(space_type, 'cosine')
    elif similarity:
        valid_similarities = ['cosine', 'l2_norm', 'dot_product', 'l1', 'linf']
        if similarity not in valid_similarities:
            field_props['similarity'] = 'cosine'
    else:
        field_props['similarity'] = 'cosine'


def _apply_knn_encoder_config(field_props: dict, params: dict) -> None:
    if 'encoder' not in params:
        return
    encoder = params['encoder']
    encoder_name = encoder.get('name', '').lower()
    encoder_params = encoder.get('parameters', {})

    if encoder_name == 'pq':
        code_size = encoder_params.get('code_size', 8)
        field_props['_compress_config'] = {
            'enable_pq': True,
            'pq_m': encoder_params.get('m', 1),
            'pq_ksub': 2 ** code_size
        }
    elif encoder_name == 'rabitq':
        field_props['_compress_config'] = {
            'enable_rabitq': True,
            'rabitq_refine_type': encoder_params.get('refine_type', 'FP32'),
            'rabitq_fht': encoder_params.get('fht', False)
        }


def _apply_knn_method_config(field_props: dict) -> None:
    method = field_props.get('method', {})
    if isinstance(method, dict) and 'name' in method:
        field_props['_method_name'] = method['name'].lower()

    if not isinstance(method, dict) or 'parameters' not in method:
        return

    params = method['parameters']
    if field_props.get('_method_name') != 'ivf':
        field_props['index_options'] = {
            'm': params.get('m', 16),
            'ef_construction': params.get('ef_construction', 64)
        }
    else:
        field_props['_ivf_parameters'] = params
    _apply_knn_encoder_config(field_props, params)


def _normalize_knn_vector_config(field_props: dict) -> None:
    _apply_knn_similarity(field_props)
    _apply_knn_method_config(field_props)
    if field_props.get('index') is True:
        field_props['_needs_index'] = True


def _validate_vector_config(field_name: str, field_props: dict) -> None:
    from opensearch_sdk.client.constants import MAX_VECTOR_DIMENSION, MIN_VECTOR_DIMENSION

    dims = field_props.get('dims', field_props.get('dimension'))
    if dims is None:
        raise ValueError(f"Vector field '{field_name}' must specify 'dims' or 'dimension'")

    if not ENABLE_PYTHON_VALIDATION:
        return

    if not isinstance(dims, int) or dims < MIN_VECTOR_DIMENSION or dims > MAX_VECTOR_DIMENSION:
        raise ValueError(f"Vector field '{field_name}' dimension must be between {MIN_VECTOR_DIMENSION} and {MAX_VECTOR_DIMENSION}")

    if 'similarity' in field_props:
        valid_similarities = ['cosine', 'l2_norm', 'dot_product']
        similarity = field_props['similarity']
        if not isinstance(similarity, str):
            raise ValueError(f"Vector field '{field_name}' similarity must be a string")
        if similarity not in valid_similarities:
            raise ValueError(
                f"Vector field '{field_name}' has unsupported similarity '{similarity}'. "
                f"Supported values: {', '.join(valid_similarities)}"
            )

    if 'index_options' in field_props and not isinstance(field_props['index_options'], dict):
        raise ValueError(f"Vector field '{field_name}' index_options must be a dictionary")


def _validate_mapping_field(field_name: str, field_props: dict) -> None:
    field_type = _validate_field_config(field_name, field_props)
    if field_type == 'nested':
        _normalize_nested_field(field_name, field_props)
    else:
        _validate_supported_type(field_name, field_type)

    if field_type in VECTOR_TYPES:
        if field_type == 'knn_vector':
            _normalize_knn_vector_config(field_props)
        _validate_vector_config(field_name, field_props)


def validate_mapping_schema(body: dict) -> None:
    """验证 mapping 配置的 schema 合法性"""
    mappings = _validate_mapping_body(body)
    properties = _replace_properties_if_normalized(
        mappings,
        _normalize_properties(mappings['properties'], "Mapping field")
    )
    
    for field_name, field_props in properties.items():
        _validate_mapping_field(field_name, field_props)


def _validate_nested_properties(properties: dict, parent_path: str) -> None:
    """递归验证 nested properties 合法性"""
    from opensearch_sdk.client.utils import normalize_identifier, _validate_identifier
    
    normalized_properties = _normalize_properties(properties, f"Nested field '{parent_path}'")
    
    if len(normalized_properties) != len(properties) or \
       set(normalized_properties.keys()) != set(properties.keys()):
        for key in list(properties.keys()):
            del properties[key]
        properties.update(normalized_properties)
    
    for field_name, field_props in properties.items():
        full_path = f"{parent_path}.{field_name}"
        
        normalized_field = normalize_identifier(field_name, f"Nested field '{parent_path}'")
        _validate_identifier(normalized_field)
        
        if not isinstance(field_props, dict):
            raise ValueError(f"Field '{full_path}' configuration must be a dictionary")
        
        if 'type' not in field_props:
            raise ValueError(f"Field '{full_path}' must specify 'type'")
        
        field_type = field_props['type']
        
        if field_type == 'nested':
            raise ValueError(f"Nested nested fields are not supported: {full_path}")
        elif not _is_valid_type(field_type):
            raise ValueError(f"Field '{full_path}' has unsupported type '{field_type}'. "
                           f"Supported types: {', '.join(sorted(SUPPORTED_BASE_TYPES))}")


def expand_nested_fields(properties: dict, prefix: str = '') -> List[Tuple[str, str, Dict]]:
    """展开 nested 字段为扁平列列表（首值策略）"""
    from opensearch_sdk.client.constants import NESTED_FIELD_SEPARATOR
    
    fields: List[Tuple[str, str, Dict]] = []
    
    for field_name, field_props in properties.items():
        field_type = field_props.get('type', 'text')
        current_path = f"{prefix}{NESTED_FIELD_SEPARATOR}{field_name}" if prefix else field_name
        
        if field_type == 'nested':
            nested_properties = field_props.get('properties', {})
            nested_fields = expand_nested_fields(nested_properties, current_path)
            fields.extend(nested_fields)
        else:
            fields.append((current_path, field_type, field_props))
    
    return fields
