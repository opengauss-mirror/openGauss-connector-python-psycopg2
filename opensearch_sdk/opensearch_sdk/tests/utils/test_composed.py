#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 Composed 对象的格式化"""

from psycopg2 import sql

# 创建一个简单的 Composed 对象
composed = sql.SQL("SELECT * FROM ").format(
    sql.Identifier('test_table')
)

print("Type:", type(composed))
print("Class name:", composed.__class__.__name__)
print("Has as_string:", hasattr(composed, 'as_string'))
print("Has flatten:", hasattr(composed, 'flatten'))
print("Has string:", hasattr(composed, 'string'))

if hasattr(composed, 'as_string'):
    try:
        result = composed.as_string(None)
        print("as_string result:", result)
    except Exception as e:
        print("as_string error:", e)

if hasattr(composed, 'flatten'):
    print("\nFlattened items:")
    for i, item in enumerate(composed.flatten()):
        print(f"  {i}: Type={type(item).__name__}, Item={item}")
        if hasattr(item, 'string'):
            print(f"      string attr: {item.string}")
