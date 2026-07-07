#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 混合检索使用示例
# 展示如何使用多种融合策略进行向量 + 全文的混合检索
#
# 依赖说明：
# - 基础功能：无需额外依赖
# - 模型重排序：需要安装 dashscope 包
#   安装命令：pip install dashscope
#   如不需要模型重排序，可以跳过相关测试

from utils import load_config
from opensearch_sdk import OpenGauss
from opensearch_sdk.retrieval import (
    VectorRetriever,
    FullTextRetriever,
    RRFFusion,
    WeightedFusion,
    ModelRerankFusion,
    DashScopeModel,
    IndexConfig,
    IndexType,
    trusted_sql
)

config = load_config()


def _create_bm25_index(client, index_name, column, index_name_suffix):
    """创建 BM25 索引的辅助函数"""
    index_config = IndexConfig(
        name=index_name_suffix,
        column=column,
        index_type=IndexType.BM25,
        parallel_workers=4
    )
    pre_sql = index_config.get_pre_create_sql(index_name)
    create_sql = index_config.to_sql(index_name)

    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            if pre_sql:
                cursor.execute(pre_sql)
            cursor.execute(create_sql)
            conn.commit()
        finally:
            cursor.close()


def _drop_bm25_index(client, index_name):
    """删除 BM25 索引的辅助函数"""
    drop_sql = f"DROP INDEX IF EXISTS {index_name}"
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(drop_sql)
            conn.commit()
        finally:
            cursor.close()


def _create_default_retrievers(query_vector=None, query_text=None, output_columns=None):
    """创建默认的检索器对"""
    if query_vector is None:
        query_vector = [0.85, 0.15, 0.0]
    if query_text is None:
        query_text = "Opensearch 向量数据库"
    if output_columns is None:
        output_columns = ['question', 'answer']

    vec_ret = VectorRetriever(
        query_vector=query_vector,
        metric="cosine",
        ef_search=100,
        output_columns=output_columns
    )

    ft_ret = FullTextRetriever(
        query_text=query_text,
        text_column='question',
        output_columns=output_columns
    )

    return [vec_ret, ft_ret]


def setup_test_data(client):
    """准备测试数据"""
    print("=== 准备测试数据 ===\n")

    mapping = {
        "mappings": {
            "properties": {
                "question": {"type": "text", "index": True},
                "answer": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 3
                }
            }
        }
    }

    try:
        client.indices.create(index='hybrid_test_index', body=mapping)
        print("[OK] 创建索引成功")

        try:
            _create_bm25_index(client, 'hybrid_test_index', 'question', 'idx_question_bm25')
            print("[OK] 创建 BM25 索引成功 (question 字段)")
        except Exception as e:
            print(f"[WARN] BM25 索引可能已存在：{e}")

    except Exception as e:
        print(f"[WARN] 索引可能已存在：{e}")

    test_docs = [
        {
            "id": "doc1",
            "data": {
                "question": "Opensearch 是什么数据库",
                "answer": "Opensearch 是基于 openGauss 的企业级向量数据库，支持 HNSW 索引和 BM25 全文检索",
                "embedding": [0.9, 0.1, 0.0]
            }
        },
        {
            "id": "doc2",
            "data": {
                "question": "如何安装 Opensearch",
                "answer": "可以通过 pip install opengauss-sdk 安装 Python SDK",
                "embedding": [0.1, 0.9, 0.0]
            }
        },
        {
            "id": "doc3",
            "data": {
                "question": "向量数据库的特点",
                "answer": "向量数据库支持相似度搜索，适用于推荐系统、图像检索等场景",
                "embedding": [0.0, 0.1, 0.9]
            }
        },
        {
            "id": "doc4",
            "data": {
                "question": "Opensearch 支持哪些索引类型",
                "answer": "支持 HNSW、IVFFlat、DiskANN 等向量索引，以及 BM25 全文索引",
                "embedding": [0.8, 0.2, 0.0]
            }
        },
        {
            "id": "doc5",
            "data": {
                "question": "什么是混合检索",
                "answer": "混合检索结合了向量检索和全文检索的优势，可以提高搜索准确率",
                "embedding": [0.7, 0.3, 0.0]
            }
        }
    ]

    for doc in test_docs:
        try:
            client.index('hybrid_test_index', doc["id"], doc["data"])
            print(f"[OK] 插入文档 {doc['id']}")
        except Exception as e:
            print(f"[WARN] 插入文档失败 {doc['id']}: {e}")

    print("\n测试数据准备完成\n")


def example_rrf_fusion(client):
    """示例 1: RRF 融合（Reciprocal Rank Fusion）"""
    print("=" * 60)
    print("示例 1: RRF 融合（Reciprocal Rank Fusion）")
    print("=" * 60)

    retrievers = _create_default_retrievers()

    results = client.multi.hybrid_search(
        "hybrid_test_index",
        retrievers=retrievers,
        top_k=5,
        fusion_strategy=RRFFusion(k=60, weights=[0.5, 0.5])
    )

    print(f"\n查询向量：[0.85, 0.15, 0.0]")
    print(f"查询文本：\"Opensearch 向量数据库\"")
    print(f"融合策略：RRF (k=60, weights=[0.5, 0.5])")
    print(f"\n返回 {len(results)} 个结果:")

    for i, result in enumerate(results, 1):
        print(f"\n{i}. ID={result.get('id')}")
        print(f"   RRF 分数：{result.get('rrf_score', 0):.4f}")
        print(f"   问题：{result.get('question', 'N/A')}")
        print(f"   答案：{result.get('answer', 'N/A')[:50]}...")


def example_weighted_fusion(client):
    """示例 2: 加权融合（Weighted Fusion）"""
    print("\n" + "=" * 60)
    print("示例 2: 加权融合（Weighted Fusion）")
    print("=" * 60)

    retrievers = _create_default_retrievers()

    results = client.multi.hybrid_search(
        "hybrid_test_index",
        retrievers=retrievers,
        top_k=5,
        fusion_strategy=WeightedFusion(weights=[0.7, 0.3])
    )

    print(f"\n查询向量：[0.85, 0.15, 0.0]")
    print(f"查询文本：\"Opensearch 向量数据库\"")
    print(f"融合策略：加权融合 (weights=[0.7, 0.3]) - 向量权重更高")
    print(f"\n返回 {len(results)} 个结果:")

    for i, result in enumerate(results, 1):
        print(f"\n{i}. ID={result.get('id')}")
        print(f"   加权分数：{result.get('weighted_score', 0):.4f}")
        print(f"   问题：{result.get('question', 'N/A')}")
        print(f"   答案：{result.get('answer', 'N/A')[:50]}...")


def example_model_rerank(client):
    """示例 3: 模型重排序融合（Model Rerank Fusion）"""
    print("\n" + "=" * 60)
    print("示例 3: 模型重排序融合（Model Rerank Fusion）")
    print("=" * 60)

    try:
        model = DashScopeModel(api_key="sk-demo-key")
        retrievers = _create_default_retrievers()

        results = client.multi.hybrid_search(
            "hybrid_test_index",
            retrievers=retrievers,
            top_k=5,
            fusion_strategy=ModelRerankFusion(
                model=model,
                query="Opensearch 向量数据库特性"
            )
        )

        print(f"\n查询向量：[0.85, 0.15, 0.0]")
        print(f"查询文本：\"Opensearch 向量数据库特性\"")
        print(f"融合策略：DashScope 模型重排序")
        print(f"\n返回 {len(results)} 个结果:")

        for i, result in enumerate(results, 1):
            print(f"\n{i}. ID={result.get('id')}")
            if 'rerank_score' in result:
                print(f"   重排序分数：{result.get('rerank_score', 0):.4f}")
            print(f"   问题：{result.get('question', 'N/A')}")
            print(f"   答案：{result.get('answer', 'N/A')[:50]}...")

    except Exception as e:
        print(f"[WARN] 模型重排序失败（可能是 API key 无效）: {e}")
        print("提示：需要使用真实的 DashScope API key 才能测试此功能")


def example_custom_retriever_config(client):
    """示例 4: 自定义检索器配置（带过滤条件）"""
    print("\n" + "=" * 60)
    print("示例 4: 自定义检索器配置（带过滤条件）")
    print("=" * 60)

    vec_ret = VectorRetriever(
        query_vector=[0.85, 0.15, 0.0],
        metric="cosine",
        ef_search=100,
        filter_condition=trusted_sql("id IN ('doc1', 'doc4', 'doc5')"),
        output_columns=['question', 'answer']
    )

    ft_ret = FullTextRetriever(
        query_text="数据库",
        text_column='question',
        bm25_k1=1.5,
        bm25_b=0.75,
        output_columns=['question', 'answer']
    )

    retrievers = [vec_ret, ft_ret]

    results = client.multi.hybrid_search(
        "hybrid_test_index",
        retrievers=retrievers,
        top_k=5,
        fusion_strategy=RRFFusion(k=60)
    )

    print(f"\n查询向量：[0.85, 0.15, 0.0] (过滤条件：id IN ('doc1', 'doc4', 'doc5'))")
    print(f"查询文本：\"数据库\" (BM25 k1=1.5, b=0.75)")
    print(f"融合策略：RRF (k=60)")
    print(f"\n返回 {len(results)} 个结果:")

    for i, result in enumerate(results, 1):
        print(f"\n{i}. ID={result.get('id')}")
        print(f"   RRF 分数：{result.get('rrf_score', 0):.4f}")
        print(f"   问题：{result.get('question', 'N/A')}")


def example_parallel_vs_sequential(client):
    """示例 5: 并行 vs 串行执行对比"""
    print("\n" + "=" * 60)
    print("示例 5: 并行 vs 串行执行对比")
    print("=" * 60)

    import time

    retrievers = _create_default_retrievers()

    start = time.time()
    results_parallel = client.multi.hybrid_search(
        "hybrid_test_index",
        retrievers=retrievers,
        top_k=5,
        parallel=True
    )
    time_parallel = time.time() - start

    start = time.time()
    results_sequential = client.multi.hybrid_search(
        "hybrid_test_index",
        retrievers=retrievers,
        top_k=5,
        parallel=False
    )
    time_sequential = time.time() - start

    print(f"\n并行执行时间：{time_parallel:.4f} 秒")
    print(f"串行执行时间：{time_sequential:.4f} 秒")
    print(f"加速比：{time_sequential / time_parallel:.2f}x")
    print(f"\n并行结果数：{len(results_parallel)}")
    print(f"串行结果数：{len(results_sequential)}")


def cleanup(client):
    """清理测试数据"""
    print("\n" + "=" * 60)
    print("清理测试数据")
    print("=" * 60)

    try:
        _drop_bm25_index(client, 'idx_question_bm25')
        client.indices.delete('hybrid_test_index')
        print("[OK] 清理测试数据成功")
    except Exception as e:
        print(f"[WARN] 清理失败：{e}")


def main():
    """主函数"""
    print("=" * 60)
    print("Opensearch 混合检索示例")
    print("=" * 60)

    client = OpenGauss(
        hosts=[{'host': config['host'], 'port': config['port']}],
        database=config['database'],
        user=config['user'],
        password=config['password']
    )

    try:
        setup_test_data(client)

        example_rrf_fusion(client)
        example_weighted_fusion(client)
        example_model_rerank(client)
        example_custom_retriever_config(client)
        example_parallel_vs_sequential(client)

        print("\n" + "=" * 60)
        print("所有示例运行完成!")
        print("=" * 60)

    finally:
        cleanup(client)
        client.close()
        print("\n数据库连接已关闭")


if __name__ == "__main__":
    main()
