"""
Vector Database Type Definition Module

Provides data types, enumerations, and data classes related to vector retrieval and full-text search.
"""

import math
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field


PARALLEL_WORKERS_MIN = 1
PARALLEL_WORKERS_MAX = 32


@dataclass(frozen=True)
class TrustedSQL:
    """Explicit wrapper marking a SQL fragment as caller-owned and trusted.

    APIs that accept raw SQL fragments (WHERE conditions, ORDER BY clauses,
    partial-index predicates) cannot be parameterized, so they require a
    ``TrustedSQL`` instead of a plain string. Wrapping a value is an explicit,
    auditable assertion that the fragment was built entirely by trusted code.
    """
    sql: str


def trusted_sql(sql_text: str) -> TrustedSQL:
    """Mark a SQL fragment as trusted so it may be embedded verbatim.

    This is NOT a sanitizer: it performs no escaping or validation of the SQL.
    The wrapped text is inserted into the query as-is. Only pass fragments that
    are fully constructed by trusted code. Never interpolate external or
    user-supplied input into the string handed to this function — doing so
    reopens the SQL injection hole this trust boundary exists to close. Bind
    dynamic values as query parameters instead.
    """
    if not isinstance(sql_text, str):
        raise TypeError("trusted SQL fragment must be a string")
    return TrustedSQL(sql_text)


def require_trusted_sql(value: Any, name: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, TrustedSQL):
        return value.sql
    raise ValueError(f"{name} must be created with trusted_sql()")


def quote_identifier(name: Any) -> str:
    if not isinstance(name, str):
        raise TypeError("SQL identifier must be a string")
    if "\x00" in name:
        raise ValueError("SQL identifier cannot contain NUL")
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    if "\x00" in value:
        raise ValueError("SQL literal cannot contain NUL")
    escaped = value.replace("\\", "\\\\").replace("'", "''")
    return "E'" + escaped + "'"


_SQL_DEFAULT_KEYWORDS = {
    'CURRENT_TIMESTAMP', 'CURRENT_DATE', 'CURRENT_TIME',
    'NOW()', 'LOCALTIME', 'LOCALTIMESTAMP',
    'NULL', 'TRUE', 'FALSE',
}


def normalize_non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a non-negative integer")
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return int(value)


def _positive_int_sql(value: Any, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return str(int(value))


def _number_sql(value: Any, name: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if isinstance(value, int):
        return str(int(value))
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return str(normalized)


class ColumnType(Enum):
    """Column type enumeration"""
    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    SMALLINT = "SMALLINT"
    REAL = "REAL"
    DOUBLE_PRECISION = "DOUBLE PRECISION"
    CHAR = "CHAR"              # Fixed-length character type
    VARCHAR = "VARCHAR"        # Variable-length character type
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    TIMESTAMP = "TIMESTAMP"
    TIMESTAMPTZ = "TIMESTAMPTZ"
    DATE = "DATE"
    TIME = "TIME"
    JSON = "JSON"
    JSONB = "JSONB"
    VECTOR = "VECTOR"          # Standard vector type, dimension limit 2000
    BIT = "BIT"                # Binary vector type, dimension limit 64000
    SPARSEVEC = "SPARSEVEC"    # Sparse vector type, dimension limit 1 billion, non-zero elements 1000
    TSVECTOR = "TSVECTOR"
    ARRAY = "ARRAY"


class IndexType(Enum):
    """Index type enumeration"""
    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GIST = "gist"
    BM25 = "bm25"
    IVFFLAT = "ivfflat"
    HNSW = "hnsw"
    DISKANN = "diskann"  # DiskANN based approximate nearest neighbor search (vector only, max dim 1536)


class VectorDataType(Enum):
    """Vector data type enumeration"""
    VECTOR = "vector"        # Standard vector type, dimension limit 2000
    HALFVEC = "halfvec"      # Half-precision vector type, dimension limit 4000
    BIT = "bit"              # Binary vector type, dimension limit 64000
    SPARSEVEC = "sparsevec"  # Sparse vector type, dimension limit 1 billion


class DistanceMetric(Enum):
    """Distance metric enumeration

    Supported vector type and distance function combinations:
    - vector: l2, ip, cosine, l1
    - halfvec: l2, ip, cosine
    - bit: hamming, jaccard
    - sparsevec: l2, ip, cosine, l1
    """
    # Distance metrics for vector type
    L2 = "vector_l2_ops"
    INNER_PRODUCT = "vector_ip_ops"
    COSINE = "vector_cosine_ops"
    L1 = "vector_l1_ops"  # L1 distance (Manhattan distance)

    # Distance metrics for halfvec type
    HALFVEC_L2 = "halfvec_l2_ops"
    HALFVEC_IP = "halfvec_ip_ops"
    HALFVEC_COSINE = "halfvec_cosine_ops"

    # Distance metrics for bit type
    BIT_HAMMING = "bit_hamming_ops"    # Hamming distance
    BIT_JACCARD = "bit_jaccard_ops"    # Jaccard distance

    # Distance metrics for sparsevec type
    SPARSEVEC_L2 = "sparsevec_l2_ops"
    SPARSEVEC_IP = "sparsevec_ip_ops"
    SPARSEVEC_COSINE = "sparsevec_cosine_ops"
    SPARSEVEC_L1 = "sparsevec_l1_ops"

    def get_operator(self) -> str:
        """Get the corresponding operator"""
        operators = {
            "vector_l2_ops": "<->",
            "vector_ip_ops": "<#>",
            "vector_cosine_ops": "<=>",
            "vector_l1_ops": "<+>",
            "halfvec_l2_ops": "<->",
            "halfvec_ip_ops": "<#>",
            "halfvec_cosine_ops": "<=>",
            "bit_hamming_ops": "<~>",
            "bit_jaccard_ops": "<%>",
            "sparsevec_l2_ops": "<->",
            "sparsevec_ip_ops": "<#>",
            "sparsevec_cosine_ops": "<=>",
            "sparsevec_l1_ops": "<+>"
        }
        return operators.get(self.value, "<->")

    @classmethod
    def for_vector_type(cls, vector_type: VectorDataType, distance: str) -> 'DistanceMetric':
        """Get the corresponding metric based on vector type and distance type"""
        distance = distance.lower()
        if vector_type == VectorDataType.HALFVEC:
            mapping = {
                "l2": cls.HALFVEC_L2,
                "ip": cls.HALFVEC_IP,
                "inner_product": cls.HALFVEC_IP,
                "cosine": cls.HALFVEC_COSINE
            }
        elif vector_type == VectorDataType.BIT:
            mapping = {
                "hamming": cls.BIT_HAMMING,
                "jaccard": cls.BIT_JACCARD
            }
        elif vector_type == VectorDataType.SPARSEVEC:
            mapping = {
                "l2": cls.SPARSEVEC_L2,
                "ip": cls.SPARSEVEC_IP,
                "inner_product": cls.SPARSEVEC_IP,
                "cosine": cls.SPARSEVEC_COSINE,
                "l1": cls.SPARSEVEC_L1
            }
        else:
            mapping = {
                "l2": cls.L2,
                "ip": cls.INNER_PRODUCT,
                "inner_product": cls.INNER_PRODUCT,
                "cosine": cls.COSINE,
                "l1": cls.L1
            }
        return mapping.get(distance, cls.L2)


class RabitQRefineType(Enum):
    """RabitQ refinement type enumeration

    RabitQ is openGauss's binary quantization method, supporting combination with HNSW/IVFFLAT
    Reference: https://docs.opengauss.org/zh/docs/latest/datavec/RabitQ.html
    """
    NONE = "none"    # No refinement
    SQ8 = "SQ8"      # 8-bit scalar quantization refinement
    FP32 = "FP32"    # 32-bit floating-point refinement (better effect, smaller storage)


@dataclass
class ColumnSchema:
    """Column schema definition"""
    name: str
    type: ColumnType
    nullable: bool = True
    primary_key: bool = False
    unique: bool = False
    default: Any = None

    # Vector field specific parameters
    dimension: Optional[int] = None

    # VARCHAR/CHAR specific parameters
    max_length: Optional[int] = None

    # ARRAY specific parameters
    array_element_type: Optional[ColumnType] = None

    # Comment
    comment: Optional[str] = None

    # Types that require a dimension parameter
    _DIMENSION_TYPES = {ColumnType.VECTOR, ColumnType.BIT, ColumnType.SPARSEVEC}
    # Types that accept an optional max_length
    _LENGTH_TYPES = {ColumnType.CHAR, ColumnType.VARCHAR}

    def _type_sql(self) -> str:
        """Generate the SQL type fragment for this column."""
        if self.type in self._DIMENSION_TYPES:
            if not self.dimension:
                raise ValueError(f"{self.type.value} column '{self.name}' requires dimension")
            return f"{self.type.value}({_positive_int_sql(self.dimension, 'dimension')})"

        if self.type in self._LENGTH_TYPES:
            return f"{self.type.value}({_positive_int_sql(self.max_length, 'max_length')})" if self.max_length else self.type.value

        if self.type == ColumnType.ARRAY:
            if not self.array_element_type:
                raise ValueError(f"ARRAY column '{self.name}' requires array_element_type")
            return f"{self.array_element_type.value}[]"

        return self.type.value

    def to_sql(self) -> str:
        """Convert to SQL definition"""
        sql_parts = [quote_identifier(self.name), self._type_sql()]

        # Constraints
        if self.primary_key:
            sql_parts.append("PRIMARY KEY")
        if self.unique and not self.primary_key:
            sql_parts.append("UNIQUE")
        if not self.nullable:
            sql_parts.append("NOT NULL")
        if self.default is not None:
            sql_parts.append(f"DEFAULT {self._format_default()}")

        return " ".join(sql_parts)

    def _format_default(self) -> str:
        """Format default value"""
        if isinstance(self.default, bool):
            return str(self.default).upper()
        elif isinstance(self.default, (int, float)):
            return _number_sql(self.default, "default")
        elif isinstance(self.default, TrustedSQL):
            return self.default.sql
        elif isinstance(self.default, str):
            default_upper = self.default.upper()
            if default_upper in _SQL_DEFAULT_KEYWORDS:
                return default_upper
            return quote_literal(self.default)
        else:
            raise ValueError("default must be bool, number, string, or TrustedSQL")


@dataclass
class TableSchema:
    """Table schema definition"""
    columns: List[ColumnSchema]
    primary_key: Optional[Union[str, List[str]]] = None
    indexes: Optional[List['IndexConfig']] = None
    comment: Optional[str] = None

    def validate(self):
        """Validate schema validity"""
        pk_columns = [col for col in self.columns if col.primary_key]
        if not pk_columns and not self.primary_key:
            raise ValueError("Table must have at least one primary key")

        column_names = [col.name for col in self.columns]
        if len(column_names) != len(set(column_names)):
            raise ValueError("Column names must be unique")

        for col in self.columns:
            if col.type in (ColumnType.VECTOR, ColumnType.BIT, ColumnType.SPARSEVEC) and not col.dimension:
                raise ValueError(f"{col.type.value} column '{col.name}' must specify dimension")

    def get_column(self, name: str) -> Optional[ColumnSchema]:
        """Get column by name"""
        for col in self.columns:
            if col.name == name:
                return col
        return None


@dataclass
class IndexConfig:
    """Index configuration

    Supports HNSW, IVFFlat, BM25 and other index types, as well as RabitQ quantization compression

    RabitQ usage examples:
        # HNSW-RABITQ index
        config = IndexConfig(
            name="idx_embedding_hnsw_rbq",
            column="embedding",
            index_type=IndexType.HNSW,
            metric=DistanceMetric.COSINE,
            m=16,
            ef_construction=64,
            enable_rabitq=True,
            rabitq_refine_type=RabitQRefineType.FP32,
            rabitq_fht=True
        )

        # IVF-RABITQ index
        config = IndexConfig(
            name="idx_embedding_ivf_rbq",
            column="embedding",
            index_type=IndexType.IVFFLAT,
            metric=DistanceMetric.COSINE,
            lists=200,
            enable_rabitq=True,
            rabitq_refine_type=RabitQRefineType.FP32
        )
    """
    name: str
    column: Union[str, List[str]]  # Supports single or multi-column indexes
    index_type: IndexType

    # Vector index parameters
    metric: Optional[DistanceMetric] = None
    lists: Optional[int] = None  # IVFFlat parameter: number of cluster centers
    probes: Optional[int] = None  # IVFFlat query parameter
    m: Optional[int] = None      # HNSW parameter: maximum connections per layer 2~100 (default 16)
    ef_construction: Optional[int] = None  # HNSW construction parameter 4~1000 (default 64)
    ef_search: Optional[int] = None        # HNSW query parameter

    # RabitQ quantization parameters (openGauss DataVec)
    # Reference: https://docs.opengauss.org/zh/docs/latest/datavec/RabitQ.html
    enable_rabitq: bool = False  # Whether to enable RabitQ quantization compression
    rabitq_refine_type: Optional['RabitQRefineType'] = None  # Refinement type: SQ8, FP32, none
    rabitq_fht: Optional[bool] = None  # Whether to use FHT random rotation (defaults to RANDOM)

    # LSG local scaling graph parameters (openGauss DataVec, HNSW only)
    # Reference: https://docs.opengauss.org/zh/docs/latest/datavec/lsg.html
    enable_lsg: bool = False     # Whether to enable LSG local scaling graph algorithm
    lsg_degree: Optional[int] = None   # Number of nearest neighbors when calculating node isolation degree 32~128 (default 96)
    lsg_alpha: Optional[float] = None  # LSG scaling smoothness 0~3.0 (default 2.0)

    # PQ quantization parameters (openGauss DataVec, supports HNSW/IVFFlat/DiskANN)
    # Reference: https://docs.opengauss.org/zh/docs/latest/datavec/pq.html
    enable_pq: bool = False               # Whether to enable PQ quantization compression
    pq_m: Optional[int] = None            # Number of subspaces to split 1~2000 (default 8), HNSW recommends dim/4, DiskANN recommends dim/8
    pq_ksub: Optional[int] = None         # Number of cluster centers per subspace 1~256 (default 256)
    by_residual: Optional[bool] = None    # IVFFlat-PQ: Enable residual computation (improves accuracy)

    # MMAP memory mapping acceleration (Beta, HNSW only)
    # Reference: https://docs.opengauss.org/zh/docs/latest/datavec/pq.html
    use_mmap: bool = False                # Whether to enable MMAP acceleration (index creation option)

    # DiskANN index parameters (openGauss DataVec)
    # Reference: https://docs.opengauss.org/zh/docs/latest/datavec/diskann.html
    index_size: Optional[int] = None      # DiskANN index construction parameter, 16~1000 (default 100)

    # BM25 index parameters (openGauss native)
    parallel_workers: Optional[int] = None  # Number of parallel construction threads (1-32)

    # General parameters
    unique: bool = False
    where: Optional[TrustedSQL] = None  # Partial index condition (trusted SQL)

    # -- Helper methods to keep to_sql() cyclomatic complexity low --

    def _column_str(self) -> str:
        """Format column name(s) for SQL."""
        if isinstance(self.column, str):
            return quote_identifier(self.column)
        return ", ".join(quote_identifier(c) for c in self.column)

    def _require_metric(self) -> None:
        """Raise if metric is not set (required for vector indexes)."""
        if not self.metric:
            raise ValueError(f"{self.index_type.value} index requires metric parameter")

    def _rabitq_params(self) -> List[str]:
        """Collect RabitQ WITH-clause params."""
        params = ["enable_rabitq = on"]
        if self.rabitq_refine_type and self.rabitq_refine_type != RabitQRefineType.NONE:
            params.append(f"rabitq_refine_type = '{self.rabitq_refine_type.value}'")
        if self.rabitq_fht is not None:
            params.append(f"rabitq_fht = {'on' if self.rabitq_fht else 'off'}")
        return params

    def _pq_params(self, include_residual: bool = False) -> List[str]:
        """Collect PQ WITH-clause params."""
        params = ["enable_pq = on"]
        if self.pq_m is not None:
            params.append(f"pq_m = {_positive_int_sql(self.pq_m, 'pq_m')}")
        if self.pq_ksub is not None:
            params.append(f"pq_ksub = {_positive_int_sql(self.pq_ksub, 'pq_ksub')}")
        if include_residual and self.by_residual is not None:
            params.append(f"by_residual = {'on' if self.by_residual else 'off'}")
        return params

    def _quantization_params(self, include_lsg: bool = False,
                             include_residual: bool = False) -> List[str]:
        """Collect mutually-exclusive quantization params (RabitQ / PQ / LSG)."""
        if self.enable_rabitq:
            return self._rabitq_params()
        if self.enable_pq:
            return self._pq_params(include_residual=include_residual)
        if include_lsg and self.enable_lsg:
            params = ["enable_lsg = on"]
            if self.lsg_degree is not None:
                params.append(f"lsg_degree = {_positive_int_sql(self.lsg_degree, 'lsg_degree')}")
            if self.lsg_alpha is not None:
                params.append(f"lsg_alpha = {_number_sql(self.lsg_alpha, 'lsg_alpha')}")
            return params
        return []

    def _build_ivfflat(self) -> str:
        """Build USING + WITH clause for IVFFlat index."""
        self._require_metric()
        using = f"USING ivfflat ({self._column_str()} {self.metric.value})"

        params = []
        if self.lists:
            params.append(f"lists = {_positive_int_sql(self.lists, 'lists')}")
        params.extend(self._quantization_params(include_residual=True))

        return f"{using} WITH ({', '.join(params)})" if params else using

    def _build_hnsw(self) -> str:
        """Build USING + WITH clause for HNSW index."""
        self._require_metric()
        using = f"USING hnsw ({self._column_str()} {self.metric.value})"

        params = []
        if self.m:
            params.append(f"m = {_positive_int_sql(self.m, 'm')}")
        if self.ef_construction:
            params.append(f"ef_construction = {_positive_int_sql(self.ef_construction, 'ef_construction')}")
        params.extend(self._quantization_params(include_lsg=True))
        if self.use_mmap:
            params.append("use_mmap = true")

        return f"{using} WITH ({', '.join(params)})" if params else using

    def _build_diskann(self) -> str:
        """Build USING + WITH clause for DiskANN index."""
        self._require_metric()
        using = f"USING diskann ({self._column_str()} {self.metric.value})"

        params = []
        if self.index_size is not None:
            params.append(f"index_size = {_positive_int_sql(self.index_size, 'index_size')}")
        if self.enable_pq:
            params.append("enable_pq = on")
            if self.pq_m is not None:
                params.append(f"pq_m = {_positive_int_sql(self.pq_m, 'pq_m')}")

        return f"{using} WITH ({', '.join(params)})" if params else using

    def _build_generic(self) -> str:
        """Build USING clause for BM25 / GIN / GIST / BTREE / HASH etc."""
        return f"USING {self.index_type.value} ({self._column_str()})"

    # Index-type -> builder dispatch table
    _INDEX_BUILDERS = {
        IndexType.IVFFLAT: _build_ivfflat,
        IndexType.HNSW: _build_hnsw,
        IndexType.DISKANN: _build_diskann,
    }

    def to_sql(self, table_name: str) -> str:
        """Convert to CREATE INDEX SQL"""
        sql_parts = ["CREATE"]
        if self.unique:
            sql_parts.append("UNIQUE")
        sql_parts.extend(["INDEX", quote_identifier(self.name), f"ON {quote_identifier(table_name)}"])

        # Dispatch to the appropriate builder, or fall back to generic
        builder = self._INDEX_BUILDERS.get(self.index_type, IndexConfig._build_generic)
        sql_parts.append(builder(self))

        if self.where:
            sql_parts.append(f"WHERE {require_trusted_sql(self.where, 'where')}")

        return " ".join(sql_parts)

    def get_pre_create_sql(self, table_name: str) -> Optional[str]:
        """Get SQL statement that must be executed BEFORE CREATE INDEX.

        In openGauss, parallel index construction for ALL index types
        (HNSW, IVFFlat, DiskANN, BM25) is configured via ALTER TABLE, NOT
        via the WITH clause of CREATE INDEX.

        References:
          - BM25:    https://docs.opengauss.org/zh/docs/latest/datavec/bm25_usage_guide.html
          - DiskANN: https://docs.opengauss.org/zh/docs/latest/datavec/diskann.html
          - RabitQ:  https://docs.opengauss.org/zh/docs/latest/datavec/RabitQ.html

        Returns:
            ALTER TABLE SQL string, or None if not needed
        """
        if self.parallel_workers is not None:
            if isinstance(self.parallel_workers, bool) or not isinstance(self.parallel_workers, int):
                raise ValueError("parallel_workers must be an integer")
            if (self.parallel_workers < PARALLEL_WORKERS_MIN or
                    self.parallel_workers > PARALLEL_WORKERS_MAX):
                raise ValueError(
                    "parallel_workers must be between "
                    f"{PARALLEL_WORKERS_MIN} and {PARALLEL_WORKERS_MAX}")
            workers = _positive_int_sql(self.parallel_workers, 'parallel_workers')
            return f'ALTER TABLE {quote_identifier(table_name)} SET(parallel_workers={workers})'
        return None


@dataclass
class SearchResult:
    """Search result"""
    id: Any
    distance: Optional[float] = None  # Vector distance
    score: Optional[float] = None     # Full-text score
    rank: Optional[float] = None      # Fusion ranking
    data: Dict[str, Any] = field(default_factory=dict)  # Actual data
    highlighted: Optional[str] = None  # Highlighted text

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary

        Note: metadata keys (id, distance, score, rank, highlighted) take
        precedence over same-named keys in self.data to avoid silent overwrites.
        """
        result = dict(self.data)  # data first, metadata overwrites
        result["id"] = self.id
        if self.distance is not None:
            result["distance"] = self.distance
        if self.score is not None:
            result["score"] = self.score
        if self.rank is not None:
            result["rank"] = self.rank
        if self.highlighted:
            result["highlighted"] = self.highlighted
        return result


# Exception class definitions
class VectorDBException(Exception):
    """Vector database exception base class"""
    pass


class TableNotFoundException(VectorDBException):
    """Table not found exception"""
    pass


class IndexNotFoundException(VectorDBException):
    """Index not found exception"""
    pass


class InvalidSchemaException(VectorDBException):
    """Invalid schema exception"""
    pass


class InvalidQueryException(VectorDBException):
    """Invalid query exception"""
    pass
