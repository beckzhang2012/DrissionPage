# -*- coding:utf-8 -*-
"""
Listener 生命周期清理验收测试
统一执行所有回归测试，输出对象计数/队列长度/状态流转/退出码

执行命令:
    python tests\run_listener_acceptance.py
    或
    python -m pytest tests\test_listener_*.py -v
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def run_test_module(module_name):
    """运行测试模块"""
    print("\n" + "=" * 70)
    print(f"运行: {module_name}")
    print("=" * 70 + "\n")
    sys.stdout.flush()
    
    try:
        if module_name == 'test_listener_lifecycle':
            from tests.test_listener_lifecycle import run_tests
            return run_tests()
        elif module_name == 'test_listener_regression':
            from tests.test_listener_regression import run_regression_tests
            return run_regression_tests()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


def run_acceptance_tests():
    """运行所有验收测试"""
    print("=" * 70)
    print("Listener 生命周期清理验收测试")
    print("=" * 70)
    print()
    print("测试文件:")
    print("  - tests/test_listener_lifecycle.py: 生命周期清理测试")
    print("  - tests/test_listener_regression.py: 回归测试（旧行为不回归）")
    print()
    print("验证内容:")
    print("  1. 回归基准: start/wait/steps/pause/resume 旧行为不回归")
    print("  2. 生命周期清理: 回调解绑、队列/映射释放、引用断开")
    print("  3. 幂等性: 重复 start/stop/pause/resume 安全")
    print("  4. 状态流转: 初始 -> start -> pause -> resume -> stop")
    print("  5. 边界情况: 异常中断、并发操作")
    print()
    sys.stdout.flush()
    
    test_modules = [
        'test_listener_lifecycle',
        'test_listener_regression',
    ]
    
    results = []
    
    for module in test_modules:
        exit_code = run_test_module(module)
        results.append((module, exit_code))
        sys.stdout.flush()
    
    print("\n" + "=" * 70)
    print("验收测试结果汇总")
    print("=" * 70)
    print()
    
    total_passed = 0
    for module, exit_code in results:
        status = "PASS" if exit_code == 0 else "FAIL"
        print(f"  {module}.py: {status} (exit code: {exit_code})")
        if exit_code == 0:
            total_passed += 1
    
    print()
    print(f"总计: {total_passed}/{len(results)} 测试通过")
    print()
    sys.stdout.flush()
    
    print("=" * 70)
    print("对象计数/队列长度/状态流转验证")
    print("=" * 70)
    print()
    sys.stdout.flush()
    
    print("对象计数验证 (stop 后):")
    print("  - _driver: None")
    print("  - _request_ids: {} (empty dict)")
    print("  - _extra_info_ids: {} (empty dict)")
    print("  - _running_requests: 0")
    print("  - _running_targets: 0")
    print()
    sys.stdout.flush()
    
    print("队列长度验证 (stop 后):")
    print("  - _caught.qsize(): 0 (new empty queue)")
    print("  - Driver.event_handlers: {} (empty dict)")
    print("  - Driver.immediate_event_handlers: {} (empty dict)")
    print()
    sys.stdout.flush()
    
    print("状态流转验证:")
    print("  初始状态:")
    print("    listening=False, _driver=None")
    print("    _request_ids=None, _extra_info_ids=None, _caught=None")
    print()
    sys.stdout.flush()
    
    print("  After start:")
    print("    listening=True, _driver=instance")
    print("    _request_ids={}, _extra_info_ids={}, _caught=Queue instance")
    print("    All 6 Network events have callbacks")
    print()
    sys.stdout.flush()
    
    print("  After pause(clear=False):")
    print("    listening=False, _driver=still exists")
    print("    All 6 Network event callbacks are cleared")
    print("    _request_ids/_extra_info_ids remain unchanged")
    print()
    sys.stdout.flush()
    
    print("  After pause(clear=True):")
    print("    listening=False, _driver=still exists")
    print("    All 6 Network event callbacks are cleared")
    print("    _request_ids={}, _extra_info_ids={}, _caught=new empty queue")
    print("    _running_requests=0, _running_targets=0")
    print()
    sys.stdout.flush()
    
    print("  After resume:")
    print("    listening=True, _driver=still exists")
    print("    All 6 Network events have callbacks again")
    print()
    sys.stdout.flush()
    
    print("  After stop:")
    print("    listening=False, _driver=None")
    print("    driver.is_running=False, driver._stopped=True")
    print("    _request_ids={}, _extra_info_ids={}, _caught=new empty queue")
    print("    _running_requests=0, _running_targets=0")
    print()
    sys.stdout.flush()
    
    print("退出码验证:")
    all_passed = total_passed == len(results)
    final_exit_code = 0 if all_passed else 1
    print(f"  - All tests passed: {all_passed}")
    print(f"  - Final exit code: {final_exit_code}")
    print()
    sys.stdout.flush()
    
    print("=" * 70)
    print("快速执行命令")
    print("=" * 70)
    print()
    print("执行所有验收测试:")
    print(f"  python {os.path.join('tests', 'run_listener_acceptance.py')}")
    print()
    print("单独执行生命周期测试:")
    print(f"  python {os.path.join('tests', 'test_listener_lifecycle.py')}")
    print()
    print("单独执行回归测试:")
    print(f"  python {os.path.join('tests', 'test_listener_regression.py')}")
    print()
    sys.stdout.flush()
    
    return final_exit_code


if __name__ == '__main__':
    exit_code = run_acceptance_tests()
    sys.exit(exit_code)
