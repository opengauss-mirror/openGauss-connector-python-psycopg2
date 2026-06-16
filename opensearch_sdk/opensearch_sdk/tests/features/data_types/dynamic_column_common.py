"""Shared helpers for dynamic column integration tests."""


def base_mapping():
    return {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "content": {"type": "text"}
            }
        }
    }


def delete_index_safely(client, index_name):
    try:
        client.indices.delete(index=index_name)
    except Exception:
        pass


def recreate_base_index(client, index_name):
    delete_index_safely(client, index_name)
    client.indices.create(index=index_name, body=base_mapping())


def fetch_columns(client, index_name, column_name=None):
    column_filter = "AND column_name = %s" if column_name else ""
    params = (index_name, column_name) if column_name else (index_name,)
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public' {column_filter}
                ORDER BY column_name;
            """, params)
            return cursor.fetchall()
        finally:
            cursor.close()


def fetch_indexes(client, index_name, index_like=None):
    index_filter = "AND indexname LIKE %s" if index_like else ""
    params = (index_name, index_like) if index_like else (index_name,)
    with client.connection.get_connection_for_operation() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = %s {index_filter}
                ORDER BY indexname;
            """, params)
            return cursor.fetchall()
        finally:
            cursor.close()


def refresh_index_safely(client, index_name):
    try:
        client.indices.refresh(index=index_name)
        print("[INFO] 索引已刷新")
    except Exception as e:
        print(f"[WARN] 刷新索引失败: {e}")
