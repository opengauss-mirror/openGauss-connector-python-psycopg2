DEFAULT_DB_HOST = "localhost"     # 默认数据库主机
                                  # 来源：PostgreSQL/Opensearch 标准配置
                                  # 用途：当未指定 hosts 参数时使用此默认值

DEFAULT_DB_PORT = 5432            # 默认数据库端口（PostgreSQL/Opensearch 标准端口）
                                  # 来源：PostgreSQL 默认端口号
                                  # 用途：当未指定端口时使用此默认值

# ==================== 向量维度限制 ====================
MAX_VECTOR_DIMENSION = 10000      # 最大向量维度
                                  # 来源：Opensearch 向量类型上限
                                  # 用途：创建向量索引时的维度校验

MIN_VECTOR_DIMENSION = 1          # 最小向量维度
                                  # 来源：向量维度基本要求
                                  # 用途：防止无效的低维向量配置

# ==================== 查询限制 ====================
MAX_QUERY_LIMIT = 10000         # 查询结果最大返回数量
                                # 来源：防止内存溢出的安全限制
                                # 用途：限制单次查询的最大结果集大小

DEFAULT_QUERY_LIMIT = 10        # 默认查询返回数量
                                # 来源：OpenSearch 兼容默认值
                                # 用途：未指定 size 参数时的默认返回值

MIN_QUERY_LIMIT = 0             # 查询最小限制
                                # 用途：参数校验下限

# ==================== KNN 搜索限制 ====================
MAX_KNN_TOP_K = 10000           # KNN 搜索最大返回数量
                                # 来源：性能优化考虑的限制
                                # 用途：防止过大的 k 值导致性能问题

MIN_KNN_TOP_K = 1               # KNN 搜索最小返回数量
                                # 用途：参数校验下限

# ==================== 批量操作限制 ====================
DEFAULT_BATCH_SIZE = 100        # 默认批量操作大小
                                # 来源：性能与内存的平衡点
                                # 用途：bulk 操作的默认批次大小

MAX_BATCH_SIZE = 10000          # 最大批量操作大小
                                # 来源：防止内存溢出
                                # 用途：限制单次批量操作的最大记录数

# ==================== HNSW 索引参数 ====================
DEFAULT_HNSW_M = 16                    # HNSW 索引默认 M 参数
                                       # 来源：HNSW 算法推荐值
                                       # 用途：每个节点的最大连接数，影响索引质量和构建速度

DEFAULT_HNSW_EF_CONSTRUCTION = 100   # HNSW 索引默认 ef_construction 参数
                                       # 来源：与 OpenSearch 2.12+ 保持一致
                                       # 用途：构建时的搜索范围，值越大质量越高但速度越慢
                                       # 注意：OpenSearch 2.11及之前版本使用512，2.12+改为100

# ==================== 分布式表配置 ====================
DEFAULT_DISTRIBUTED = False            # 默认是否创建分布式表
                                       # True: 所有新表默认为分布式表
                                       # False: 需要显式指定 distributed=True

DEFAULT_DISTRIBUTION_COLUMN = "id"     # 默认分布列名称
                                       # 用途：当 distributed=True 且未指定分布列时使用

DEFAULT_SHARD_COUNT = 6                # 默认分片数量
                                       # 来源：平衡性能和复杂度的经验值
                                       # 用途：分布式表的默认分片数

DEFAULT_HNSW_EF_SEARCH = 100           # HNSW 索引默认 ef_search 参数
                                       # 来源：HNSW 算法推荐值
                                       # 用途：搜索时的探索范围，值越大精度越高但速度越慢

# ==================== IVF 索引参数 ====================
DEFAULT_IVF_NLIST = 4                  # IVF 索引默认 nlist 参数（聚类中心数）
                                       # 来源：性能优化经验值
                                       # 用途：控制聚类的粒度，影响索引构建和查询性能

DEFAULT_IVF_NPROBES = 1                # IVF 索引默认 nprobes 参数（查询时探测的桶数）
                                       # 来源：性能优化经验值
                                       # 用途：值越大精度越高但速度越慢

# ==================== RabitQ 索引参数 ====================
DEFAULT_RABITQ_SAMPLE_ROWS = 1000      # RabitQ 延迟索引数据行阈值
                                       # 来源：性能优化经验值
                                       # 用途：达到此行数时自动创建 RabitQ 索引

# ==================== Nested 对象配置 ====================
NESTED_FIELD_SEPARATOR = "__"       # Nested 字段展开时的连接符
                                       # 来源：OpenSearch nested 对象扁平化命名规范
                                       # 用途：将 author.name 转换为 author__name

# ==================== Mapping 存储配置 ====================
MAPPING_STORAGE_TABLE = "opensearch_mapping"  # Mapping 存储表名
                                               # 来源：独立表存储方案，避免依赖 pg_description
                                               # 用途：存储所有索引的 mapping 信息，支持动态列类型推断

# ==================== 时间相关 ====================
MILLISECONDS_PER_SECOND = 1000         # 每秒毫秒数
                                       # 用途：时间单位转换常量

# ==================== 重试和超时 ====================
DEFAULT_MAX_RETRIES = 3                # 默认最大重试次数
                                       # 来源：容错与性能的平衡
                                       # 用途：网络错误等临时故障的重试次数

DEFAULT_TIMEOUT_SECONDS = 30           # 默认超时时间（秒）
                                       # 来源：一般网络请求的合理超时时间
                                       # 用途：防止查询长时间阻塞
