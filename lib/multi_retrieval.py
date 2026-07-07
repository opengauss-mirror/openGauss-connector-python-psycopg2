import logging
import math
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from psycopg2.retrievers import RetrievalResult
from psycopg2.vector_types import TrustedSQL, normalize_non_negative_int

if TYPE_CHECKING:
    from psycopg2.models import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class RetrievalPath:
    """Single retrieval path result."""
    name: str
    results: List[RetrievalResult]


# ========== Fusion Strategies ==========

class FusionStrategy(ABC):
    """Base class for fusion strategies.

    Subclasses can choose whether to use weights:
    - RRFFusion / WeightedFusion: require weights
    - LearningToRankFusion: do not require weights (model determines ranking)
    """

    def __init__(self, weights: List[float] = None):
        """
        Args:
            weights: Optional weight list. Auto-distributed evenly if not provided.
                     Each weight must be in [0, 1] and sum to 1.
        """
        if weights is not None:
            for w in weights:
                if not 0 <= w <= 1:
                    raise ValueError(
                        f"Each weight must be in [0, 1], got {w}"
                    )
            total = sum(weights)
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"Weights must sum to 1, got {weights} (sum={total:.4f})"
                )
        self.weights = weights

    def get_weights(self, num_paths: int) -> List[float]:
        if self.weights is not None:
            if len(self.weights) != num_paths:
                raise ValueError(
                    f"weights length ({len(self.weights)}) != "
                    f"number of retrievers ({num_paths})"
                )
            return self.weights
        # Auto-distribute evenly (sum to 1)
        return [1.0 / num_paths] * num_paths

    # Subclasses set this to tag fused results (e.g. 'rrf_fused', 'weighted_fused')
    _fuse_source: str = "fused"

    def _accumulate_score(
            self,
            score_map: Dict[Any, float],
            data_map: Dict[Any, Dict],
            doc_id: Any,
            score: float,
            data: Dict
    ):
        """Accumulate score and merge data for a document.

        If the document already exists, adds score and merges new data fields
        without overwriting existing ones.
        """
        if doc_id in score_map:
            score_map[doc_id] += score
            for key, value in data.items():
                if key not in data_map[doc_id]:
                    data_map[doc_id][key] = value
        else:
            score_map[doc_id] = score
            data_map[doc_id] = dict(data)

    def _build_sorted_results(
            self,
            score_map: Dict[Any, float],
            data_map: Dict[Any, Dict],
            top_k: int,
            source: str
    ) -> List[RetrievalResult]:
        """Sort by score descending and build RetrievalResult list."""
        sorted_ids = sorted(score_map, key=score_map.get, reverse=True)
        return [
            RetrievalResult(
                id=doc_id,
                score=score_map[doc_id],
                data=data_map[doc_id],
                source=source
            )
            for doc_id in sorted_ids[:top_k]
        ]

    @abstractmethod
    def _score_path(self, path: RetrievalPath, weight: float,
                    score_map: Dict, data_map: Dict):
        """Score a single retrieval path. Subclasses must implement."""

    def fuse(
            self,
            paths: List[RetrievalPath],
            top_k: int = 10
    ) -> List[RetrievalResult]:
        """Fuse multi-path retrieval results (template method).

        Iterates over paths with weights, delegates per-path scoring
        to ``_score_path()``, then sorts and returns top-k results.
        """
        if not paths:
            return []

        weights = self.get_weights(len(paths))
        score_map: Dict[Any, float] = {}
        data_map: Dict[Any, Dict] = {}

        for path, weight in zip(paths, weights):
            self._score_path(path, weight, score_map, data_map)

        return self._build_sorted_results(score_map, data_map, top_k, self._fuse_source)


class RRFFusion(FusionStrategy):
    """Reciprocal Rank Fusion.

    RRF formula: score = Σ (weight / (k + rank))

    Examples:
        # Default even weights
        fusion = RRFFusion(k=60)

        # Custom weights
        fusion = RRFFusion(k=60, weights=[0.6, 0.4])
    """

    _fuse_source = "rrf_fused"

    def __init__(self, k: int = 60, weights: List[float] = None):
        super().__init__(weights)
        self.k = k

    def _score_path(self, path: RetrievalPath, weight: float,
                    score_map: Dict, data_map: Dict):
        """Compute RRF scores for a single retrieval path."""
        for rank, result in enumerate(path.results, 1):
            rrf_score = weight / (self.k + rank)
            self._accumulate_score(score_map, data_map, result.id, rrf_score, result.data)


class NormMethod(Enum):
    """Score normalization method."""
    ARCTAN = "arctan"      # arctan normalization
    MIN_MAX = "min_max"    # min-max normalization
    NONE = "none"          # no normalization


class WeightedFusion(FusionStrategy):
    """Weighted score fusion.

    Normalizes scores from each path then computes weighted sum.

    Normalization methods:
    - arctan: normalize to [0, 1] using arctan function (default)
    - min_max: normalize to [0, 1] using min-max scaling
    - none: use raw scores directly (when scores are already on the same scale)

    Examples:
        # Default arctan normalization
        fusion = WeightedFusion(weights=[0.7, 0.3])

        # Min-max normalization
        fusion = WeightedFusion(weights=[0.7, 0.3], norm_method=NormMethod.MIN_MAX)

        # No normalization (scores already on the same scale)
        fusion = WeightedFusion(weights=[0.7, 0.3], norm_method=NormMethod.NONE)
    """

    _fuse_source = "weighted_fused"

    def __init__(
            self,
            weights: List[float] = None,
            norm_method: NormMethod = NormMethod.ARCTAN
    ):
        """
        Args:
            weights: Optional weight list. Auto-distributed evenly if not provided.
            norm_method: Normalization method, defaults to arctan.
        """
        super().__init__(weights)
        self.norm_method = norm_method

    def _normalize_score(self, score: float, min_score: float = None, score_range: float = None) -> float:
        """Normalize score to [0, 1].

        Args:
            score: Raw score.
            min_score: Minimum score (required for min_max method).
            score_range: Score range (required for min_max method).

        Returns:
            Normalized score.
        """
        if self.norm_method == NormMethod.ARCTAN:
            return (math.atan(score) / math.pi) + 0.5
        elif self.norm_method == NormMethod.MIN_MAX:
            if score_range is not None and score_range > 0:
                return (score - min_score) / score_range
            # All scores are identical; normalize to 0.5 (midpoint)
            return 0.5
        else:
            return score

    def _compute_range(self, results: List[RetrievalResult]):
        """Compute min_score and score_range for min_max normalization."""
        if self.norm_method != NormMethod.MIN_MAX:
            return None, None
        scores = [r.score for r in results]
        min_score = min(scores)
        return min_score, max(scores) - min_score

    def _score_path(self, path: RetrievalPath, weight: float,
                    score_map: Dict, data_map: Dict):
        """Normalize and weight scores for a single retrieval path."""
        if not path.results:
            return
        min_score, score_range = self._compute_range(path.results)
        for result in path.results:
            normalized = self._normalize_score(result.score, min_score, score_range)
            self._accumulate_score(
                score_map, data_map,
                result.id, normalized * weight, result.data
            )


class ModelRerankFusion(FusionStrategy):
    """Model-based reranking fusion strategy.

    Uses a model's rerank capability to semantically reorder multi-path recall results.
    Unlike RRF/Weighted fusion which score per-path independently, this strategy:
    1. Merges multi-path recall results (deduplicate)
    2. Extracts document text
    3. Calls model rerank API in a single batch
    4. Returns results sorted by semantic relevance

    Example:
        >>> from psycopg2.models import create_model
        >>>
        >>> model = create_model("cohere", api_key="xxx")
        >>> fusion = ModelRerankFusion(model=model, query="machine learning")
        >>>
        >>> results = client.hybrid_search(
        ...     "documents",
        ...     retrievers=[vec_ret, ft_ret],
        ...     fusion_strategy=fusion
        ... )
    """

    _fuse_source = "model_rerank"

    def __init__(
            self,
            model: "BaseModel",
            query: str,
            text_field: str = "content",
            fallback_to_rrf: bool = True
    ):
        """
        Args:
            model: Pre-constructed model instance (must support rerank).
            query: Query text (used for rerank).
            text_field: Text field name used for rerank input.
            fallback_to_rrf: Whether to fall back to RRF if rerank fails.
        """
        super().__init__(weights=None)

        self.model = model
        self.query = query
        self.text_field = text_field
        self.fallback_to_rrf = fallback_to_rrf

    def _extract_text(self, data: Dict[str, Any]) -> str:
        """Extract text from document data."""
        return data.get(self.text_field, str(data))

    @staticmethod
    def _update_merged_entry(entry: Dict, result: 'RetrievalResult') -> None:
        """Update an existing merged entry with a new result.

        Keeps the highest score and merges data fields without
        overwriting existing ones (consistent with base class
        ``_accumulate_score``).
        """
        if result.score > entry["score"]:
            entry["score"] = result.score
        # Merge data without overwriting (consistent with base class)
        for key, value in result.data.items():
            if key not in entry["data"]:
                entry["data"][key] = value

    def _merge_results(self, paths: List[RetrievalPath]) -> Dict[Any, Dict]:
        """Merge multi-path recall results (deduplicate, keep highest score).

        Data merge follows the same convention as the base class
        ``_accumulate_score``: new fields are added but existing fields
        are never overwritten.
        """
        merged = {}

        for path in paths:
            for result in path.results:
                doc_id = result.id

                if doc_id not in merged:
                    merged[doc_id] = {
                        "data": dict(result.data),
                        "score": result.score,
                    }
                else:
                    self._update_merged_entry(merged[doc_id], result)

        return merged

    def _score_path(self, path: RetrievalPath, weight: float,
                    score_map: Dict, data_map: Dict):
        """Not used — ModelRerankFusion overrides fuse() directly."""
        raise NotImplementedError(
            "ModelRerankFusion uses model rerank instead of per-path scoring"
        )

    def fuse(
            self,
            paths: List[RetrievalPath],
            top_k: int = 10
    ) -> List[RetrievalResult]:
        """Fuse results using model rerank.

        Overrides the base template method because reranking requires
        a single batch call across all merged documents.

        Args:
            paths: Multi-path retrieval results.
            top_k: Maximum number of results to return.

        Returns:
            Fused retrieval result list.
        """
        if not paths:
            return []

        # 1. Merge results
        merged = self._merge_results(paths)

        if not merged:
            return []

        # 2. Prepare documents
        doc_ids = list(merged.keys())
        documents = [self._extract_text(merged[did]["data"]) for did in doc_ids]

        # 3. Call model rerank
        try:
            rerank_results = self.model.rerank(
                query=self.query,
                documents=documents,
                top_n=top_k
            )
        except Exception as e:
            logger.warning(f"Model rerank failed: {e}")
            if self.fallback_to_rrf:
                logger.info("Falling back to RRF fusion")
                return RRFFusion(k=60).fuse(paths, top_k)
            raise

        # 4. Build results (keep data clean, consistent with other fusions)
        results = []
        for r in rerank_results:
            idx = r["index"]
            doc_id = doc_ids[idx]
            score = r["score"]

            results.append(RetrievalResult(
                id=doc_id,
                score=score,
                data=merged[doc_id]["data"],
                source=self._fuse_source
            ))

        return results[:top_k]


# ========== Multi-Path Retrieval Engine ==========

class MultiRetrievalEngine:
    """Multi-path retrieval engine.

    Examples:
        # 1. Create retrievers
        vector_ret = VectorRetriever(query_vector, metric="cosine")
        text_ret = FullTextRetriever(query_text)

        # 2. Create engine (weights configured in fusion strategy)
        engine = MultiRetrievalEngine(
            retrievers=[vector_ret, text_ret],
            fusion_strategy=RRFFusion(k=60, weights=[0.6, 0.4])
        )

        # 3. Execute search
        results = engine.search(client, "documents", top_k=10)

        # Example 2: default even weights
        engine = MultiRetrievalEngine(
            retrievers=[vector_ret, text_ret],
            fusion_strategy=RRFFusion()  # auto even [0.5, 0.5]
        )
    """

    # Default per-retriever timeout in seconds
    DEFAULT_TIMEOUT = 30

    def __init__(
            self,
            retrievers: List,
            fusion_strategy: FusionStrategy = None
    ):
        if not retrievers:
            raise ValueError("retrievers list must not be empty")
        self.retrievers = retrievers
        self.fusion_strategy = fusion_strategy or RRFFusion()

    def search(
            self,
            client,
            table_name: str,
            top_k: int = 10,
            filter_condition: Optional[TrustedSQL] = None,
            filter_params: Dict = None,
            output_columns: List[str] = None,
            per_path_top_k: int = None,
            parallel: bool = True,
            max_workers: int = None,
            timeout: float = None,
            **kwargs
    ) -> List[Dict]:
        """Execute multi-path retrieval with optional parallelism.

        Args:
            client: Database client.
            table_name: Table name.
            top_k: Number of final results to return.
            filter_condition: SQL WHERE clause created with trusted_sql().
            filter_params: Parameters for filter condition.
            output_columns: Columns to include in output.
            per_path_top_k: Results per retrieval path (defaults to top_k * 2).
            parallel: Whether to run in parallel (default True, uses connection pool).
            max_workers: Max thread count (defaults to number of retrievers).
            timeout: Per-retriever timeout in seconds (default 30s).
            **kwargs: Extra arguments passed to each retriever.

        Returns:
            Fused results as list of dicts.
        """
        top_k = normalize_non_negative_int(top_k, "top_k")
        if per_path_top_k is None:
            per_path_top_k = top_k * 2
        else:
            per_path_top_k = normalize_non_negative_int(per_path_top_k, "per_path_top_k")

        if timeout is None:
            timeout = self.DEFAULT_TIMEOUT

        # Build shared retrieve kwargs
        retrieve_kwargs = dict(
            client=client,
            table_name=table_name,
            top_k=per_path_top_k,
            filter_condition=filter_condition,
            filter_params=filter_params,
            output_columns=output_columns,
            **kwargs
        )

        if parallel:
            paths = self._search_parallel(retrieve_kwargs, max_workers, timeout)
        else:
            paths = self._search_sequential(retrieve_kwargs)

        if not paths:
            return []

        # Fuse results
        fused_results = self.fusion_strategy.fuse(paths, top_k)

        # Convert to dict format
        # r.data is expanded first so that fusion metadata (id, score, source)
        # always takes precedence over same-named keys in r.data.
        return [
            {
                **r.data,
                'id': r.id,
                'score': r.score,
                'source': r.source,
            }
            for r in fused_results
        ]

    @staticmethod
    def _safe_retrieve(retriever, retrieve_kwargs: Dict) -> RetrievalPath:
        """Execute a single retriever, returning empty path on failure."""
        try:
            results = retriever.retrieve(**retrieve_kwargs)
            return RetrievalPath(name=retriever.get_name(), results=results)
        except Exception as e:
            logger.warning(f"{retriever.get_name()} retrieval failed: {e}")
            return RetrievalPath(name=retriever.get_name(), results=[])

    def _search_sequential(self, retrieve_kwargs: Dict) -> List[RetrievalPath]:
        """Execute each retriever sequentially.

        Note: Failed retrievers produce an empty-result path (not skipped)
        to preserve positional alignment with weights.
        """
        return [
            self._safe_retrieve(retriever, retrieve_kwargs)
            for retriever in self.retrievers
        ]

    def _search_parallel(
            self,
            retrieve_kwargs: Dict,
            max_workers: int = None,
            timeout: float = None
    ) -> List[RetrievalPath]:
        """Execute each retriever in parallel using a thread pool.

        Note: Failed/timed-out retrievers produce an empty-result path (not skipped)
        to preserve positional alignment with weights.
        """
        if max_workers is None:
            max_workers = len(self.retrievers)

        paths: List[Optional[RetrievalPath]] = [None] * len(self.retrievers)

        # Each retriever acquires an independent connection from the pool
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._safe_retrieve, retriever, retrieve_kwargs)
                for retriever in self.retrievers
            ]

            # Collect results in submission order to preserve retriever alignment
            for i, future in enumerate(futures):
                try:
                    paths[i] = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    name = self.retrievers[i].get_name()
                    logger.warning(f"{name} retrieval timed out after {timeout}s")
                    paths[i] = RetrievalPath(name=name, results=[])
                except Exception as e:
                    name = self.retrievers[i].get_name()
                    logger.warning(f"{name} retrieval task failed: {e}")
                    paths[i] = RetrievalPath(name=name, results=[])

        return paths
