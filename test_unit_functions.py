# -*- coding:utf-8 -*-
"""
单元测试：验证核心函数
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from DrissionPage._libs.DownloadKit._funcs import (
    verify_range_match, 
    parse_content_range,
    calculate_file_hash,
    verify_file_integrity
)


def test_parse_content_range():
    """测试 Content-Range 解析"""
    print("="*60)
    print("测试: parse_content_range")
    print("="*60)
    
    test_cases = [
        ("bytes 0-499/1234", (0, 499, 1234), "正常格式"),
        ("bytes 100-199/200", (100, 199, 200), "部分范围"),
        ("bytes */1234", (None, None, 1234), "未知范围格式"),
        ("", (None, None, None), "空字符串"),
    ]
    
    all_passed = True
    for content_range, expected, desc in test_cases:
        result = parse_content_range(content_range)
        passed = result == expected
        if not passed:
            all_passed = False
        
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {desc}")
        print(f"  输入: {content_range!r}")
        print(f"  期望: {expected}")
        print(f"  实际: {result}")
    
    print(f"\n结果: {'通过' if all_passed else '失败'}")
    return all_passed


def test_verify_range_match():
    """测试 Range 匹配验证"""
    print("\n" + "="*60)
    print("测试: verify_range_match")
    print("="*60)
    
    test_cases = [
        (0, 499, "bytes 0-499/1234", True, "正常匹配"),
        (0, 499, "bytes 10-499/1234", False, "起始位置不匹配"),
        (0, 499, "bytes 0-500/1234", False, "结束位置不匹配"),
        (100, '', "bytes 100-199/200", True, "请求到末尾，响应有具体范围"),
        (100, '', "bytes 0-199/200", False, "请求从100开始，响应从0开始"),
        (50, 99, "bytes 60-99/1000", False, "Range 偏移10字节"),
    ]
    
    all_passed = True
    for req_start, req_end, content_range, expected_match, desc in test_cases:
        match_ok, reason = verify_range_match(req_start, req_end, content_range)
        passed = match_ok == expected_match
        if not passed:
            all_passed = False
        
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {desc}")
        print(f"  请求: bytes={req_start}-{req_end}")
        print(f"  响应: {content_range}")
        print(f"  期望匹配: {expected_match}")
        print(f"  实际匹配: {match_ok}")
        print(f"  原因: {reason}")
    
    print(f"\n结果: {'通过' if all_passed else '失败'}")
    return all_passed


def test_state_idempotency():
    """测试状态幂等性"""
    print("\n" + "="*60)
    print("测试: 状态幂等性")
    print("="*60)
    
    from DrissionPage._libs.DownloadKit.mission import BaseTask
    
    task = BaseTask(ID="test")
    
    print(f"初始状态: state={task.state}, result={task.result}")
    
    task.set_states(result='success', info='第一次成功', state='done')
    print(f"第一次设置后: state={task.state}, result={task.result}")
    
    task.set_states(result='failed', info='第二次失败', state='done')
    print(f"第二次设置后: state={task.state}, result={task.result}")
    
    passed = task.state == 'done' and task.result == 'success'
    print(f"\n结果: {'通过' if passed else '失败'}")
    
    if passed:
        print("  验证: 终态不可被覆盖")
    else:
        print(f"  失败: 期望 result='success', 实际 result={task.result!r}")
    
    return passed


def run_all_tests():
    print("#"*60)
    print("# 核心函数单元测试")
    print("#"*60)
    
    results = []
    
    passed = test_parse_content_range()
    results.append(("parse_content_range", passed))
    
    passed = test_verify_range_match()
    results.append(("verify_range_match", passed))
    
    passed = test_state_idempotency()
    results.append(("state_idempotency", passed))
    
    print("\n" + "#"*60)
    print("# 测试摘要")
    print("#"*60)
    
    all_passed = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}")
        if not passed:
            all_passed = False
    
    total = len(results)
    passed_count = len([r for r in results if r[1]])
    
    print("\n" + "="*60)
    print(f"总计: {passed_count}/{total} 测试通过")
    print("="*60)
    
    exit_code = 0 if all_passed else 1
    print(f"\n$LASTEXITCODE = {exit_code}")
    sys.exit(exit_code)


if __name__ == '__main__':
    run_all_tests()
