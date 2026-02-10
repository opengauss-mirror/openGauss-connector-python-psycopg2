from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from enum import Enum
import os
import logging

logger = logging.getLogger(__name__)


class ModelCapability(Enum):
    """模型能力枚举"""
    EMBED = "embed"       # 文本嵌入
    RERANK = "rerank"     # 重排序
    CHAT = "chat"         # 对话/生成


class BaseModel(ABC):
    """模型基类
    
    提供统一的模型访问接口，包括：
    - embed: 文本嵌入
    - rerank: 文本重排序
    - chat: 对话/生成
    
    子类需要实现具体的 API 调用逻辑。
    """
    
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        chat_model: str = None,
        embed_model: str = None,
        rerank_model: str = None,
        timeout: int = 30,
        max_retries: int = 3,
        **kwargs
    ):
        """
        Args:
            api_key: API 密钥
            base_url: API 基础 URL（可选，用于自定义端点）
            chat_model: 默认模型名称（用于 chat）
            embed_model: 嵌入模型名称
            rerank_model: 重排序模型名称
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            **kwargs: 额外配置
        """
        self.api_key = api_key or os.getenv(self._get_api_key_env_name(), "")
        self.base_url = base_url or self._get_default_base_url()
        self.chat_model = chat_model or self._get_default_model()
        self.embed_model = embed_model or self._get_default_embed_model()
        self.rerank_model = rerank_model or self._get_default_rerank_model()
        self.timeout = timeout
        self.max_retries = max_retries
        self.extra = kwargs
        
        # 延迟初始化的客户端
        self._client = None
    
    @property
    @abstractmethod
    def provider(self) -> str:
        """返回提供商名称"""
        pass
    
    @property
    def capabilities(self) -> List[ModelCapability]:
        """返回模型支持的能力列表"""
        caps = []
        if self.embed_model:
            caps.append(ModelCapability.EMBED)
        if self.rerank_model:
            caps.append(ModelCapability.RERANK)
        if self.chat_model:
            caps.append(ModelCapability.CHAT)
        return caps
    
    def _get_api_key_env_name(self) -> str:
        """获取 API Key 的环境变量名"""
        return f"{self.provider.upper()}_API_KEY"
    
    def _get_default_base_url(self) -> str:
        """获取默认 API 基础 URL"""
        return ""
    
    def _get_default_model(self) -> str:
        """获取默认 chat 模型"""
        return ""
    
    def _get_default_embed_model(self) -> str:
        """获取默认嵌入模型"""
        return ""
    
    def _get_default_rerank_model(self) -> str:
        """获取默认重排序模型"""
        return ""
    
    # ========== 核心接口 ==========
    
    @abstractmethod
    def embed(
        self,
        texts: Union[str, List[str]],
        **kwargs
    ) -> List[List[float]]:
        """文本嵌入
        
        Args:
            texts: 单个文本或文本列表
            **kwargs: 额外参数
            
        Returns:
            嵌入向量列表
        """
        pass
    
    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """文本重排序
        
        Args:
            query: 查询文本
            documents: 待排序的文档列表
            top_n: 返回的最大结果数
            **kwargs: 额外参数
            
        Returns:
            排序后的结果列表，每个元素包含:
            - index: 原始索引
            - score: 相关性分数
            - text: 文档文本（可选）
        """
        pass
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """对话/生成
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            **kwargs: 额外参数（temperature, max_tokens 等）
            
        Returns:
            生成的文本
        """
        pass
    
    # ========== 便捷方法 ==========
    
    def embed_single(self, text: str, **kwargs) -> List[float]:
        """嵌入单个文本"""
        result = self.embed([text], **kwargs)
        return result[0] if result else []
    
    def rerank_with_scores(
        self,
        query: str,
        documents: List[str],
        **kwargs
    ) -> List[float]:
        """返回重排序分数列表（按原始顺序）"""
        results = self.rerank(query, documents, **kwargs)
        scores = [0.0] * len(documents)
        for r in results:
            scores[r["index"]] = r["score"]
        return scores
    
    def generate(self, prompt: str, **kwargs) -> str:
        """简单文本生成（单轮对话）"""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider}, model={self.chat_model})"


# ==================== OpenAI 实现 ====================

class OpenAIModel(BaseModel):
    """OpenAI 模型实现
    
    支持:
    - Chat: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo
    - Embed: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
    
    Example:
        >>> model = OpenAIModel(api_key="sk-xxx")
        >>> embeddings = model.embed(["Hello, world!"])
        >>> response = model.chat([{"role": "user", "content": "Hi"}])
    """
    
    @property
    def provider(self) -> str:
        return "openai"
    
    def _get_default_base_url(self) -> str:
        return "https://api.openai.com/v1"
    
    def _get_default_model(self) -> str:
        return "gpt-4o-mini"
    
    def _get_default_embed_model(self) -> str:
        return "text-embedding-3-small"
    
    @property
    def client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=self.timeout,
                    max_retries=self.max_retries
                )
            except ImportError:
                raise ImportError("OpenAI requires openai package. Install with: pip install openai")
        return self._client
    
    def embed(
        self,
        texts: Union[str, List[str]],
        model: str = None,
        **kwargs
    ) -> List[List[float]]:
        """使用 OpenAI 嵌入模型"""
        if isinstance(texts, str):
            texts = [texts]
        
        response = self.client.embeddings.create(
            model=model or self.embed_model,
            input=texts,
            **kwargs
        )
        
        return [item.embedding for item in response.data]
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """OpenAI 不支持 rerank。

        Raises:
            NotImplementedError: 始终抛出,提示使用支持 rerank 的模型。
        """
        raise NotImplementedError(
            "OpenAI does not provide a rerank API. "
            "Use a provider with native rerank support "
            "(e.g. DashScope with gte-rerank-v2, Cohere, Jina)."
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = None,
        max_tokens: int = None,
        top_p: float = None,
        frequency_penalty: float = None,
        presence_penalty: float = None,
        response_format: Dict = None,
        **kwargs
    ) -> str:
        """使用 OpenAI Chat Completions API

        Args:
            messages: 消息列表
            model: 模型名称,默认为 gpt-4o-mini
            temperature: 采样温度 [0, 2]
            max_tokens: 最大生成 token 数
            top_p: 核采样概率阈值
            frequency_penalty: 频率惩罚 [-2.0, 2.0]
            presence_penalty: 存在惩罚 [-2.0, 2.0]
            response_format: 输出格式,如 {"type": "json_object"}
            **kwargs: 额外参数 (如 tools, seed, stop 等)

        Returns:
            生成的文本
        """
        params = {
            "model": model or self.chat_model,
            "messages": messages,
        }

        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if top_p is not None:
            params["top_p"] = top_p
        if frequency_penalty is not None:
            params["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            params["presence_penalty"] = presence_penalty
        if response_format is not None:
            params["response_format"] = response_format

        params.update(kwargs)

        response = self.client.chat.completions.create(**params)

        return response.choices[0].message.content


# ==================== DashScope ====================

class DashScopeModel(BaseModel):
    """阿里云 DashScope (千问) 模型实现

    支持:
    - Chat: qwen-max, qwen-plus, qwen-turbo 等 (Generation API)
    - Embed: text-embedding-v3 (TextEmbedding API)
    - Rerank: qwen3-rerank, gte-rerank-v2 (TextReRank API)

    文档:
    - Chat: https://help.aliyun.com/zh/model-studio/qwen-api-via-dashscope
    - Rerank: https://help.aliyun.com/zh/model-studio/text-rerank-api

    Example:
        >>> model = DashScopeModel(api_key="sk-xxx")
        >>> response = model.chat([{"role": "user", "content": "你好"}])
        >>> embeddings = model.embed(["Hello, world!"])
        >>> results = model.rerank("查询", ["文档1", "文档2"])
    """

    @property
    def provider(self) -> str:
        return "dashscope"

    def _get_api_key_env_name(self) -> str:
        return "DASHSCOPE_API_KEY"

    def _get_default_base_url(self) -> str:
        # 华北2(北京)地域
        return "https://dashscope.aliyuncs.com/api/v1"

    def _get_default_model(self) -> str:
        return "qwen-plus"

    def _get_default_embed_model(self) -> str:
        return "text-embedding-v3"

    def _get_default_rerank_model(self) -> str:
        return "gte-rerank-v2"

    @staticmethod
    def _ensure_dashscope():
        """确保 dashscope 包已安装"""
        try:
            import dashscope  # noqa: F401
        except ImportError:
            raise ImportError(
                "DashScopeModel requires dashscope package. "
                "Install with: pip/pip3 install -U dashscope"
            )

    def embed(
        self,
        texts: Union[str, List[str]],
        model: str = None,
        text_type: str = "document",
        **kwargs
    ) -> List[List[float]]:
        """使用 DashScope TextEmbedding API

        Args:
            texts: 文本或文本列表
            model: 模型名称,默认为 text-embedding-v3
            text_type: 文本类型,可选 "query" 或 "document"
            **kwargs: 额外参数

        Returns:
            嵌入向量列表
        """
        self._ensure_dashscope()
        from dashscope import TextEmbedding

        if isinstance(texts, str):
            texts = [texts]

        response = TextEmbedding.call(
            api_key=self.api_key,
            model=model or self.embed_model,
            input=texts,
            text_type=text_type,
            **kwargs
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope embedding failed: {response.code} - {response.message}"
            )

        return [item['embedding'] for item in response.output['embeddings']]

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """使用 DashScope TextReRank API

        文档: https://help.aliyun.com/zh/model-studio/text-rerank-api

        Args:
            query: 查询文本
            documents: 待排序的文档列表
            top_n: 返回的最大结果数
            **kwargs: 额外参数 (如 return_documents, instruct)

        Returns:
            排序后的结果列表,每个元素包含 index 和 score
        """
        self._ensure_dashscope()
        from dashscope import TextReRank

        model = kwargs.pop("model", None) or self.rerank_model

        params = dict(
            api_key=self.api_key,
            model=model,
            query=query,
            documents=documents,
            **kwargs
        )
        if top_n is not None:
            params["top_n"] = top_n

        response = TextReRank.call(**params)

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope rerank failed: {response.code} - {response.message}"
            )

        # 统一输出格式: relevance_score -> score
        return [
            {
                "index": r["index"],
                "score": r["relevance_score"],
            }
            for r in response.output["results"]
        ]

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        top_k: int = None,
        max_tokens: int = None,
        repetition_penalty: float = None,
        enable_search: bool = False,
        stream: bool = False,
        result_format: str = "message",
        **kwargs
    ) -> str:
        """使用 DashScope Generation API

        文档: https://help.aliyun.com/zh/model-studio/qwen-api-via-dashscope

        Args:
            messages: 消息列表,格式为 [{"role": "user", "content": "..."}]
            model: 模型名称,默认为 qwen-plus
            temperature: 采样温度 [0, 2),控制随机性
            top_p: 核采样概率阈值 (0, 1.0]
            top_k: 候选 token 数量
            max_tokens: 最大生成 token 数
            repetition_penalty: 重复度惩罚 (>0)
            enable_search: 是否启用联网搜索
            stream: 是否流式输出 (启用时自动开启 incremental_output)
            result_format: 返回格式 "message" 或 "text"
            **kwargs: 额外参数 (如 enable_thinking, tools 等)

        Returns:
            生成的文本
        """
        self._ensure_dashscope()
        from dashscope import Generation

        # 构建参数
        params = {
            "api_key": self.api_key,
            "model": model or self.chat_model,
            "messages": messages,
            "result_format": result_format,
        }

        # 添加可选参数
        if temperature is not None:
            params["temperature"] = temperature
        if top_p is not None:
            params["top_p"] = top_p
        if top_k is not None:
            params["top_k"] = top_k
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if repetition_penalty is not None:
            params["repetition_penalty"] = repetition_penalty
        if enable_search:
            params["enable_search"] = True
        if stream:
            params["stream"] = True
            # 流式必须开启增量输出,否则每个 chunk 是累积全文,拼接会重复
            params["incremental_output"] = True

        # 添加其他额外参数
        params.update(kwargs)

        # 调用 API
        if stream:
            return self._chat_stream(params, result_format)
        else:
            return self._chat_sync(params, result_format)

    def _chat_sync(self, params: Dict, result_format: str) -> str:
        """同步调用 Chat API"""
        from dashscope import Generation

        response = Generation.call(**params)

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope chat failed: {response.code} - {response.message}"
            )

        if result_format == "message":
            return response.output.choices[0].message.content
        else:
            return response.output.text

    @staticmethod
    def _chat_stream(params: Dict, result_format: str) -> str:
        """流式调用 Chat API,返回拼接后的完整文本"""
        from dashscope import Generation

        response = Generation.call(**params)
        full_content = ""
        for chunk in response:
            if chunk.status_code != 200:
                raise RuntimeError(
                    f"DashScope chat failed: {chunk.code} - {chunk.message}"
                )
            if result_format == "message":
                content = chunk.output.choices[0].message.content
            else:
                content = chunk.output.text
            if content:
                full_content += content
        return full_content


# ==================== Ollama ====================

class OllamaModel(BaseModel):
    """Ollama 本地部署模型实现

    支持通过 Ollama 运行本地模型：
    - Chat: llama3, qwen2, mistral 等 (/api/chat)
    - Embed: nomic-embed-text, mxbai-embed-large 等 (/api/embed)
    - Rerank: 通过 embedding + cosine similarity 模拟

    文档: https://docs.ollama.com/api

    Example:
        >>> model = OllamaModel(chat_model="llama3")
        >>> response = model.chat([{"role": "user", "content": "Hi"}])
        >>> embeddings = model.embed(["Hello", "World"])
    """

    @property
    def provider(self) -> str:
        return "ollama"

    def _get_default_base_url(self) -> str:
        return "http://localhost:11434"

    def _get_default_model(self) -> str:
        return "llama3"

    def _get_default_embed_model(self) -> str:
        return "nomic-embed-text"

    def embed(
        self,
        texts: Union[str, List[str]],
        model: str = None,
        **kwargs
    ) -> List[List[float]]:
        """使用 Ollama Embed API (批量)

        文档: https://docs.ollama.com/api/embed

        Args:
            texts: 文本或文本列表
            model: 模型名称,默认为 nomic-embed-text
            **kwargs: 额外参数 (如 truncate, dimensions, keep_alive)

        Returns:
            嵌入向量列表
        """
        import requests

        if isinstance(texts, str):
            texts = [texts]

        response = requests.post(
            f"{self.base_url}/api/embed",
            json={
                "model": model or self.embed_model,
                "input": texts,
                **kwargs
            },
            timeout=self.timeout
        )
        response.raise_for_status()

        return response.json()["embeddings"]

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_n: int = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Ollama 不支持 rerank。

        Raises:
            NotImplementedError: 始终抛出,提示使用支持 rerank 的模型。
        """
        raise NotImplementedError(
            "Ollama does not provide a rerank API. "
            "Use a provider with native rerank support "
            "(e.g. DashScope with gte-rerank-v2, Cohere, Jina)."
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        temperature: float = None,
        top_p: float = None,
        top_k: int = None,
        max_tokens: int = None,
        repetition_penalty: float = None,
        output_format: str = None,
        keep_alive: str = None,
        **kwargs
    ) -> str:
        """使用 Ollama Chat API

        文档: https://docs.ollama.com/api/chat

        Args:
            messages: 消息列表,格式为 [{"role": "user", "content": "..."}]
            model: 模型名称,默认为 llama3
            temperature: 采样温度
            top_p: 核采样概率阈值
            top_k: 候选 token 数量
            max_tokens: 最大生成 token 数 (对应 Ollama 的 num_predict)
            repetition_penalty: 重复度惩罚 (对应 Ollama 的 repeat_penalty)
            output_format: 输出格式,如 "json"
            keep_alive: 模型保持加载时间,如 "5m"
            **kwargs: 额外 options 参数 (如 seed, num_ctx 等)

        Returns:
            生成的文本
        """
        import requests

        # 构建请求体
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
        }

        # 顶层参数 (非 options)
        if output_format is not None:
            payload["format"] = output_format
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        # 运行时 options (仅在显式设置时传入,不覆盖模型默认值)
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if top_p is not None:
            options["top_p"] = top_p
        if top_k is not None:
            options["top_k"] = top_k
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        if repetition_penalty is not None:
            options["repeat_penalty"] = repetition_penalty
        options.update(kwargs)

        if options:
            payload["options"] = options

        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()

        return response.json()["message"]["content"]


# ==================== 提供商注册表 & 工厂函数 ====================

_PROVIDERS: Dict[str, type] = {
    "openai": OpenAIModel,
    "dashscope": DashScopeModel,
    "ollama": OllamaModel,
}


def register_provider(name: str, cls: type):
    """注册自定义模型提供商

    Args:
        name: 提供商名称
        cls: 模型类（需继承 BaseModel）

    Example:
        >>> class MyModel(BaseModel): ...
        >>> register_provider("my_provider", MyModel)
        >>> model = create_model("my_provider", api_key="xxx")
    """
    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        raise TypeError(f"cls must be a subclass of BaseModel, got {cls}")
    _PROVIDERS[name] = cls


def list_providers() -> List[str]:
    """列出所有已注册的模型提供商"""
    return list(_PROVIDERS.keys())


def create_model(
    provider: str,
    **kwargs
) -> BaseModel:
    """创建模型实例的工厂函数

    配置优先级: kwargs 显式传参 > 环境变量 > 子类硬编码默认值

    Args:
        provider: 提供商名称
            - openai: OpenAI GPT 系列
            - dashscope: 阿里云千问系列
            - ollama: Ollama 本地部署
        **kwargs: 传给模型构造函数的参数
            (api_key, base_url, chat_model, embed_model, rerank_model, ...)

    Returns:
        BaseModel 实例

    Example:
        >>> model = create_model("openai", api_key="sk-xxx")
        >>> model = create_model("dashscope", api_key="sk-xxx")
        >>> model = create_model("ollama", chat_model="llama3")
    """
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Available: {list(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[provider](**kwargs)
