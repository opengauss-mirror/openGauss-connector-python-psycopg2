"""
Connection pool checker for tests
"""

def check_pool_status(client, test_name=""):
    """
    检查连接池状态
    
    :param client: Opensearch 客户端
    :param test_name: 测试名称（用于日志）
    :return: True 如果没有泄漏，False 如果有泄漏
    """
    if not hasattr(client.connection, '_pool'):
        # 单连接模式，跳过检查
        return True
    
    status = client.connection._pool.get_pool_status()
    used = status['used_connections']
    
    if used > 0:
        print(f"[WARN] {test_name}: Connection leak detected! Used: {used}, Status: {status}")
        return False
    else:
        print(f"[OK] {test_name}: No connection leak (used={used})")
        return True


def check_transaction_state(client, test_name=""):
    """
    检查事务状态
    
    :param client: Opensearch 客户端
    :param test_name: 测试名称（用于日志）
    :return: True 如果事务状态正常，False 如果有问题
    """
    try:
        # 尝试执行一个简单的查询来检查事务状态
        cursor = client.connection.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        print(f"[OK] {test_name}: Transaction state is normal")
        return True
    except Exception as e:
        error_msg = str(e)
        if "aborted" in error_msg.lower() or "failed" in error_msg.lower():
            print(f"[FAIL] {test_name}: Transaction is in aborted state: {e}")
            return False
        else:
            print(f"[WARN] {test_name}: Transaction check failed: {e}")
            return False
