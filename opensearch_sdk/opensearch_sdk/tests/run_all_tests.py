#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Opensearch兼容接口完整回归测试脚本
运行所有测试模块并生成综合报告

使用方法:
    python run_all_tests.py                    # 运行所有测试
    python run_all_tests.py --module document_ops  # 只运行指定模块
    python run_all_tests.py --help             # 查看帮助
"""

import os
import sys
import argparse
import re
import subprocess
from pathlib import Path

# 导入配置常量
from config import PYTHON_CMD, TEST_MODULES, ROOT_TEST_FILES, TEST_TIMEOUT


def _project_root():
    return str(Path(__file__).resolve().parent.parent.parent)


def _test_env(project_root):
    env = os.environ.copy()
    pythonpath_parts = [project_root]
    if 'PYTHONPATH' in env:
        pythonpath_parts.append(env['PYTHONPATH'])
    env['PYTHONPATH'] = os.pathsep.join(pythonpath_parts)
    return env


def _run_unittest(command, project_root, env):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=TEST_TIMEOUT,
        encoding='utf-8',
        errors='replace',
        env=env,
        cwd=project_root
    )


def _failure_name_from_line(line):
    if 'unittest.loader._FailedTest' in line or 'setUpClass' in line:
        return None

    parts = line.split('(')
    if len(parts) <= 1:
        return None

    test_method = parts[0].strip().replace('FAIL:', '').replace('ERROR:', '').strip()
    test_class = parts[1].split(')')[0] if ')' in parts[1] else ''
    return f"{test_class}.{test_method}"


def _parse_failures_and_errors(output_lines):
    failures = []
    errors = []
    for line in output_lines:
        stripped = line.strip()
        if not (stripped.startswith('FAIL:') or stripped.startswith('ERROR:')):
            continue

        full_test_name = _failure_name_from_line(line)
        if not full_test_name:
            continue

        if stripped.startswith('FAIL:'):
            failures.append(full_test_name)
        else:
            errors.append(full_test_name)
    return failures, errors


def _count_total_tests(full_output, output_lines):
    ran_matches = re.findall(r'Ran\s+(\d+)\s+tests?\s+in', full_output)
    if ran_matches:
        return sum(int(match) for match in ran_matches)

    ok_count = sum(1 for line in output_lines if ' ... ok' in line)
    error_count = sum(1 for line in output_lines if ' ... ERROR' in line or line.strip().startswith('ERROR:'))
    fail_count = sum(1 for line in output_lines if ' ... FAIL' in line or line.strip().startswith('FAIL:'))
    skip_count = sum(1 for line in output_lines if ' ... skipped' in line or 'SKIP' in line.upper())
    return ok_count + error_count + fail_count + skip_count


def _process_output(result, use_returncode=False):
    full_output = result.stdout + '\n' + result.stderr
    output_lines = full_output.split('\n')
    failures, errors = _parse_failures_and_errors(output_lines)
    total_tests = _count_total_tests(full_output, output_lines)
    passed = result.returncode == 0 if use_returncode else (
        len(failures) == 0 and len(errors) == 0 and total_tests > 0
    )
    return {
        'passed': passed,
        'failures': failures,
        'errors': errors,
        'returncode': result.returncode,
        'total_tests': total_tests,
        'output_sample': full_output[-1000:] if len(full_output) > 1000 else full_output
    }


def run_tests_for_directory(dir_name):
    """运行指定目录的测试并返回结果"""
    print(f"\n{'='*70}")
    print(f"正在测试：{dir_name}")
    print('='*70)

    test_dir = Path(__file__).parent / dir_name
    if not test_dir.exists():
        print(f"目录不存在：{test_dir}")
        return []

    project_root = _project_root()
    env = _test_env(project_root)

    # 使用 discover 方式运行测试，从项目根目录访问测试文件
    # 关键：使用相对于项目根目录的路径，并指定 top-level directory
    relative_test_path = f"opensearch_sdk/tests/{dir_name}"
    print(f"正在运行测试：{relative_test_path}")
    result = _run_unittest(
        [PYTHON_CMD, '-m', 'unittest', 'discover', '-s', relative_test_path, '-t', project_root, '-p', 'test_*.py', '-v'],
        project_root,
        env
    )
    return _process_output(result)

def _write_test_list(f, tests):
    """写入测试列表到报告文件"""
    for test in tests:
        f.write(f"- `{test}`\n")
    f.write("\n")


def _write_failure_details(f, all_results):
    """
    写入失败用例详情到报告文件

    :arg f: 已打开的文件对象
    :arg all_results: 所有测试结果字典
    """
    f.write("## 失败用例分析\n\n")

    for dir_name, result in all_results.items():
        if not result['passed']:
            f.write(f"### {dir_name}\n\n")

            if result['failures']:
                f.write("**失败的测试**:\n\n")
                _write_test_list(f, result['failures'])

            if result['errors']:
                f.write("**出错的测试**:\n\n")
                _write_test_list(f, result['errors'])


def generate_report(all_results, total_passed, total_failed, total_errors):
    """
    生成测试报告文件
    
    Args:
        all_results: 所有测试结果字典
        total_passed: 通过的测试数
        total_failed: 失败的测试数
        total_errors: 错误的测试数
    """
    from datetime import datetime
    
    # 创建 reports 目录
    reports_dir = Path(__file__).parent.parent.parent / 'reports'
    reports_dir.mkdir(exist_ok=True)
    
    # 生成文件名（带时间戳）
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = reports_dir / f'regression_report_{timestamp}.md'
    
    total_tests = total_passed + total_failed + total_errors
    pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# Opensearch兼容接口回归测试报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # 测试摘要
        f.write("## 测试摘要\n\n")
        f.write("| 指标 | 数量 | 百分比 |\n")
        f.write("|------|------|--------|\n")
        f.write(f"| 总测试数 | {total_tests} | 100% |\n")
        f.write(f"| 通过 | {total_passed} | {pass_rate:.1f}% |\n")
        f.write(f"| 失败 | {total_failed} | {(total_failed/total_tests*100) if total_tests > 0 else 0:.1f}% |\n")
        f.write(f"| 错误 | {total_errors} | {(total_errors/total_tests*100) if total_tests > 0 else 0:.1f}% |\n\n")
        
        # 模块详情
        f.write("## 模块详情\n\n")
        f.write("| 模块 | 测试数 | 状态 |\n")
        f.write("|------|--------|------|\n")
        
        for dir_name, result in all_results.items():
            status = "[OK] 通过" if result['passed'] else "[FAIL] 失败"
            f.write(f"| {dir_name} | {result['total_tests']} | {status} |\n")
        
        f.write("\n")
        
        # 失败用例详情
        if total_failed > 0 or total_errors > 0:
            _write_failure_details(f, all_results)
        else:
            f.write("## 失败用例分析\n\n")
            f.write("[OK] 所有测试均通过，无失败用例。\n\n")
        
        # 总结
        f.write("## 总结\n\n")
        if total_failed == 0 and total_errors == 0:
            f.write("[SUCCESS] **恭喜！所有测试通过！**\n\n")
            f.write("代码质量良好，可以安全提交或发布。\n")
        else:
            f.write("[WARN] **存在失败的测试，需要修复后再提交。**\n\n")
            f.write("建议：\n")
            f.write("1. 查看上方的失败用例分析\n")
            f.write("2. 定位并修复问题\n")
            f.write("3. 重新运行测试验证修复\n")
    
    print(f"\n[REPORT] 详细报告已保存至: {report_file}")


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Opensearch兼容接口回归测试脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_all_tests.py                     # 运行所有测试
  python run_all_tests.py --module document_ops  # 只运行文档操作测试
  python run_all_tests.py --module document_ops,bool_query  # 运行多个模块
  python run_all_tests.py --list              # 列出所有可用模块
        """
    )
    
    parser.add_argument(
        '--module', '-m',
        type=str,
        default=None,
        help='指定要运行的测试模块（逗号分隔），如: document_ops,bool_query'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='列出所有可用的测试模块'
    )
    return parser.parse_args()


def _print_module_list():
    print("可用的测试模块：")
    for i, module in enumerate(TEST_MODULES, 1):
        print(f"  {i}. {module}")


def _selected_test_dirs(module_arg):
    if not module_arg:
        return TEST_MODULES

    selected_modules = [module.strip() for module in module_arg.split(',')]
    valid_modules = []
    for module in selected_modules:
        if module in TEST_MODULES:
            valid_modules.append(module)
        else:
            print(f"警告: 未知模块 '{module}'，已跳过")
    return valid_modules


def _run_test_directories(test_dirs):
    print("开始批量测试验证...")
    print(f"测试模块: {', '.join(test_dirs)}")
    print(f"总计 {len(test_dirs)} 个模块\n")

    all_results = {}
    for dir_name in test_dirs:
        all_results[dir_name] = run_tests_for_directory(dir_name)
    return all_results


def _run_root_test_file(test_file, project_root, env):
    test_path = Path(__file__).parent / test_file
    if not test_path.exists():
        return None

    module_name = f"opensearch_sdk.tests.{test_file[:-3]}"
    result = _run_unittest(
        [PYTHON_CMD, '-m', 'unittest', module_name, '-v'],
        project_root,
        env
    )
    parsed_result = _process_output(result, use_returncode=True)
    if parsed_result['total_tests'] <= 0:
        return None

    parsed_result['output_sample'] = ''
    print(f"[OK] {test_file}: 通过 ({parsed_result['total_tests']} 个测试)")
    return parsed_result


def _run_root_tests(all_results):
    if not ROOT_TEST_FILES:
        return

    print(f"\n{'='*70}")
    print(f"正在测试：根目录测试文件")
    print('='*70)

    project_root = _project_root()
    env = _test_env(project_root)
    for test_file in ROOT_TEST_FILES:
        result = _run_root_test_file(test_file, project_root, env)
        if result:
            all_results[f"root/{test_file}"] = result


def _print_failed_tests(result):
    if result['failures']:
        for test in result['failures']:
            print(f"   - FAIL: {test}")
    if result['errors']:
        for test in result['errors']:
            print(f"   - ERROR: {test}")


def _print_summary(all_results):
    print("\n" + "="*70)
    print("测试验证报告")
    print("="*70)

    total_passed_dirs = 0
    total_passed_tests = 0
    total_failed = 0
    total_errors = 0

    for dir_name, result in all_results.items():
        if result['passed']:
            print(f"[OK] {dir_name}: 通过 ({result['total_tests']} 个测试)")
            total_passed_dirs += 1
            total_passed_tests += result['total_tests']
        else:
            num_failures = len(result['failures'])
            num_errors = len(result['errors'])
            print(f"[FAIL] {dir_name}: 失败 ({num_failures} FAIL, {num_errors} ERROR, 共{result['total_tests']}个测试)")
            total_failed += num_failures
            total_errors += num_errors
            _print_failed_tests(result)

            # 显示通过的测试数
            passed_in_dir = result['total_tests'] - len(result['failures']) - len(result['errors'])
            total_passed_tests += passed_in_dir
            if passed_in_dir > 0:
                print(f"   [OK] 通过：{passed_in_dir} 个测试")

    print("\n" + "="*70)
    print(f"总计：通过 {total_passed_tests}, 失败 {total_failed}, 错误 {total_errors}")
    print("="*70)

    return total_passed_tests, total_failed, total_errors


def main():
    """主函数"""
    args = _parse_args()
    if args.list:
        _print_module_list()
        return 0

    test_dirs = _selected_test_dirs(args.module)
    if not test_dirs:
        print("错误: 没有有效的测试模块")
        return 1

    all_results = _run_test_directories(test_dirs)
    _run_root_tests(all_results)
    total_passed_tests, total_failed, total_errors = _print_summary(all_results)
    generate_report(all_results, total_passed_tests, total_failed, total_errors)
    return 0 if (total_failed == 0 and total_errors == 0) else 1

if __name__ == '__main__':
    sys.exit(main())
