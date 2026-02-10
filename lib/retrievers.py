"""
Unified Retriever Module

Provides vector and full-text retrieval with shared infrastructure:
- GUC parameter lifecycle management (SET before query, RESET after)
- Connection pool integration (get → use → return)
- Parameter resolution (call-time overrides preset defaults)

Ref: https://docs.opengauss.org/zh/docs/latest/database_reference/datavec_vector_engine_parameters.html
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple

from psycopg2.extras import RealDictCursor
from psycopg2.vector_types import DistanceMetric, VectorDataType

logger = logging.getLogger(__name__)


# ========== Retrieval Results ==========

@dataclass
class RetrievalResult:
    """Single retrieval result"""
    id: Any
    score: float
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""


# ========== Retriever Base Class ==========

class BaseRetriever(ABC):
    """Retriever base class using Template Method pattern.

    Subclasses implement:
    - ``_get_guc_settings()`` — GUC parameters to SET before query
    - ``_build_query()``      — SQL string and parameter list construction
    - ``_build_result()``     — transform a single DB row into RetrievalResult
    - ``get_name()``          — retriever name identifier

    The ``retrieve()`` method orchestrates the full flow:
    resolve params → build query → SET GUCs → execute → RESET GUCs → build results
    """

    def __init__(
            self,
            id_column: str = "id",
            top_k: int = None,
            filter_condition: str = None,
            filter_params: Union[Dict, list, tuple] = None,
            output_columns: List[str] = None,
    ):
        self.id_column = id_column
        self.default_top_k = top_k
        self.default_filter = filter_condition
        self.default_filter_params = filter_params
        self.default_output_columns = output_columns

    # -- Shared helpers --

    def _resolve_params(self, top_k, filter_, filter_params, output_columns):
        """Resolve call-time parameters, falling back to preset defaults."""
        return (
            top_k if top_k is not None else (self.default_top_k or 10),
            filter_ if filter_ is not None else self.default_filter,
            filter_params if filter_params is not None else self.default_filter_params,
            output_columns if output_columns is not None else self.default_output_columns,
        )

    def _build_select_columns(self, output_columns: Optional[List[str]]) -> str:
        """Build SELECT column list, ensuring id_column is always included."""
        if not output_columns:
            return "*"
        cols = list(output_columns)
        if self.id_column not in cols:
            cols.insert(0, self.id_column)
        return ", ".join(f'"{c}"' for c in cols)

    @staticmethod
    def _inject_filter_params(params: list, filter_params, insert_at: int = 1):
        """Insert filter_params into the SQL params list at *insert_at*.

        Supports dict (values in insertion order), list, or tuple.
        """
        if filter_params is None:
            return
        values = list(filter_params.values()) if isinstance(filter_params, dict) else list(filter_params)
        params[insert_at:insert_at] = values

    # -- GUC lifecycle --

    def _get_guc_settings(self) -> Dict[str, Any]:
        """Return ``{guc_name: value}`` to SET before the query.

        Only entries where *value* is not ``None`` will be SET.
        All SET parameters are automatically RESET in the finally block.
        Override in subclasses.
        """
        return {}

    def _execute_with_guc(self, client, query: str, params: list) -> list:
        """Execute *query* wrapped in SET/RESET of GUC parameters."""
        conn = client.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        guc_set: List[str] = []

        try:
            for name, value in self._get_guc_settings().items():
                if value is not None:
                    cursor.execute(f"SET {name} = {value}")
                    guc_set.append(name)

            cursor.execute(query, params)
            return cursor.fetchall()
        finally:
            for name in guc_set:
                try:
                    cursor.execute(f"RESET {name}")
                except Exception:
                    pass
            cursor.close()
            client.return_connection(conn)

    # -- Template method --

    @abstractmethod
    def _build_query(self, table_name: str, top_k: int, filter_: Optional[str],
                     filter_params, output_columns: Optional[List[str]]) -> Tuple[str, list]:
        """Build ``(sql_string, param_list)``. Subclasses must implement."""

    @abstractmethod
    def _build_result(self, row: Dict, index: int) -> RetrievalResult:
        """Transform a single DB row dict into a ``RetrievalResult``."""

    def retrieve(
            self,
            client,
            table_name: str,
            top_k: int = None,
            filter_condition: str = None,
            filter_params: Union[Dict, list, tuple] = None,
            output_columns: List[str] = None,
            **kwargs,
    ) -> List[RetrievalResult]:
        """Execute retrieval (template method)."""
        top_k, filter_, filter_params, output_columns = self._resolve_params(
            top_k, filter_condition, filter_params, output_columns
        )
        query, params = self._build_query(table_name, top_k, filter_, filter_params, output_columns)
        rows = self._execute_with_guc(client, query, params)
        return [self._build_result(row, i) for i, row in enumerate(rows)]

    @abstractmethod
    def get_name(self) -> str:
        """Return a short identifier for this retriever (e.g. 'vector', 'fulltext')."""


# ========== Vector Retriever ==========

class VectorRetriever(BaseRetriever):
    """Vector retriever

    Supports HNSW, IVFFlat, DiskANN indexes, and RabitQ/PQ quantization accelerated queries.

    Usage examples::

        # RabitQ index
        VectorRetriever(query_vector, metric="cosine", ef_search=100,
                        rbq_query_bits=8, rbq_refinek=10)

        # HNSW-PQ index
        VectorRetriever(query_vector, metric="l2", ef_search=100,
                        hnsw_earlystop_threshold=320)

        # IVFFlat-PQ index
        VectorRetriever(query_vector, metric="l2", probes=10,
                        ivfpq_kreorder=100)

        # DiskANN index
        VectorRetriever(query_vector, metric="l2", diskann_probes=64)
    """

    def __init__(
            self,
            query_vector: List[float],
            vector_column: str = "embedding",
            metric: str = "cosine",
            *,
            id_column: str = "id",
            top_k: int = None,
            filter_condition: str = None,
            filter_params: Union[Dict, list, tuple] = None,
            output_columns: List[str] = None,
            use_index: bool = True,
            # Index scan parameters (GUC)
            ef_search: int = None,
            probes: int = None,
            # RabitQ — https://docs.opengauss.org/zh/docs/latest/datavec/RabitQ.html
            rbq_query_bits: int = None,
            rbq_refinek: float = None,
            rbq_sample_rows: int = None,
            # PQ — https://docs.opengauss.org/zh/docs/latest/datavec/pq.html
            hnsw_earlystop_threshold: int = None,
            ivfpq_kreorder: int = None,
            # DiskANN — https://docs.opengauss.org/zh/docs/latest/datavec/diskann.html
            diskann_probes: int = None,
    ):
        super().__init__(id_column, top_k, filter_condition, filter_params, output_columns)
        self.query_vector = query_vector
        self.vector_column = vector_column
        self.metric = metric
        self.use_index = use_index

        # GUC parameters: (guc_name, value, type_cast)
        self._guc_entries = [
            ("hnsw_ef_search", ef_search, int),
            ("ivfflat_probes", probes, int),
            ("rbq_query_bits", rbq_query_bits, int),
            ("rbq_refinek", rbq_refinek, float),
            ("rbq_sample_rows", rbq_sample_rows, int),
            ("hnsw_earlystop_threshold", hnsw_earlystop_threshold, int),
            ("ivfpq_kreorder", ivfpq_kreorder, int),
            ("diskann_probes", diskann_probes, int),
        ]

    def _get_guc_settings(self) -> Dict[str, Any]:
        return {
            name: cast(value)
            for name, value, cast in self._guc_entries
            if value is not None
        }

    def _compute_score(self, distance: float) -> float:
        """Compute normalized score based on distance metric.

        - L2 / L1:  distance >= 0, lower is more similar  → ``1 / (1 + d)``
        - cosine:    distance = 1 - cos_sim, range [0, 2]  → ``1 - d``
        - inner_product: ``<#>`` returns ``-ip``            → ``-d`` (= ip)
        """
        metric = self.metric.lower()
        if metric == "cosine":
            return 1.0 - distance
        if metric in ("inner_product", "ip"):
            return -distance
        return 1.0 / (1.0 + distance)

    def _get_operator(self) -> str:
        """Resolve distance operator from metric name via DistanceMetric enum.

        Delegates to ``DistanceMetric.for_vector_type().get_operator()`` so that
        the operator mapping is maintained in a single place (vector_types.py).
        """
        metric = DistanceMetric.for_vector_type(VectorDataType.VECTOR, self.metric)
        return metric.get_operator()

    def _build_query(self, table_name, top_k, filter_, filter_params, output_columns):
        operator = self._get_operator()
        select_cols = self._build_select_columns(output_columns)
        vector_str = "[" + ",".join(str(v) for v in self.query_vector) + "]"

        dist_expr = f'"{self.vector_column}" {operator} %s::vector'
        query_parts = [
            f"SELECT {select_cols}, {dist_expr} AS distance",
            f'FROM "{table_name}"',
        ]
        if filter_:
            query_parts.append(f"WHERE {filter_}")
        query_parts.append(f"ORDER BY {dist_expr}")
        query_parts.append(f"LIMIT {top_k}")

        query = " ".join(query_parts)
        params = [vector_str, vector_str]
        if filter_ and filter_params:
            self._inject_filter_params(params, filter_params)

        return query, params

    def _build_result(self, row, index):
        return RetrievalResult(
            id=row.get(self.id_column, index),
            score=self._compute_score(row["distance"]),
            data=dict(row),
            source="vector",
        )

    def get_name(self) -> str:
        return "vector"


# ========== Full-text Retriever ==========

class FullTextRetriever(BaseRetriever):
    """BM25 full-text retriever using openGauss BM25 index.

    Usage::

        retriever = FullTextRetriever("深度学习入门", text_column="content")
        results = retriever.retrieve(client, "documents", top_k=10)
    """

    def __init__(
            self,
            query_text: str,
            text_column: str = "content",
            *,
            id_column: str = "id",
            top_k: int = None,
            filter_condition: str = None,
            filter_params: Union[Dict, list, tuple] = None,
            output_columns: List[str] = None,
            use_bm25_taat: bool = False,
            bm25_topk: int = None,
            bm25_k1: float = None,
            bm25_b: float = None,
    ):
        super().__init__(id_column, top_k, filter_condition, filter_params, output_columns)
        self.query_text = query_text
        self.text_column = text_column
        self.use_bm25_taat = use_bm25_taat
        self.bm25_topk = bm25_topk
        self.bm25_k1 = bm25_k1
        self.bm25_b = bm25_b

    def _get_guc_settings(self) -> Dict[str, Any]:
        settings: Dict[str, Any] = {}
        if self.use_bm25_taat:
            settings["enable_bm25_taat"] = "on"
        if self.bm25_topk is not None:
            settings["bm25_topk"] = self.bm25_topk
        if self.bm25_k1 is not None:
            settings["bm25_k1"] = self.bm25_k1
        if self.bm25_b is not None:
            settings["bm25_b"] = self.bm25_b
        # Force index scan for BM25
        settings["enable_seqscan"] = "off"
        settings["enable_indexscan"] = "on"
        return settings

    def _build_query(self, table_name, top_k, filter_, filter_params, output_columns):
        select_cols = self._build_select_columns(output_columns)
        score_expr = f'"{self.text_column}" <&> %s'

        query_parts = [
            f"SELECT {select_cols}, {score_expr} AS score",
            f'FROM "{table_name}"',
        ]
        if filter_:
            query_parts.append(f"WHERE {filter_}")
        query_parts.append(f"ORDER BY {score_expr} DESC")
        query_parts.append(f"LIMIT {top_k}")

        query = " ".join(query_parts)
        params = [self.query_text, self.query_text]
        if filter_ and filter_params:
            self._inject_filter_params(params, filter_params)

        return query, params

    def _build_result(self, row, index):
        return RetrievalResult(
            id=row.get(self.id_column, index),
            score=float(row["score"]),
            data=dict(row),
            source="fulltext",
        )

    def get_name(self) -> str:
        return "fulltext"
