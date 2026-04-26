# -*- coding:utf-8 -*-
"""
测试 ChromiumOptions 配置一致性
覆盖:
1. 多个 ChromiumOptions 实例并发修改后配置不串
2. 保存后重新加载，路径、参数、扩展顺序一致
3. 覆盖保存时异常中断不破坏原配置
4. 删除/替换参数后不残留旧值
5. 多轮保存加载无状态漂移
"""
import os
import sys
import tempfile
import threading
import shutil
import json
from pathlib import Path
from copy import deepcopy

repo_root = Path(__file__).parent
sys.path.insert(0, str(repo_root))
test_tmp_root = repo_root / '.test_tmp'
test_tmp_root.mkdir(exist_ok=True)

from DrissionPage._configs.chromium_options import ChromiumOptions
from DrissionPage._configs.options_manage import OptionsManager


class Metrics:
    def __init__(self):
        self.total_checks = 0
        self.passed_checks = 0
        self.pollution_count = 0
        self.half_write_intercepted = 0
        self.residual_params = 0
        self.reload_consistent = 0

    @property
    def consistency_rate(self):
        if self.total_checks == 0:
            return 100.0
        return (self.passed_checks / self.total_checks) * 100

    def snapshot(self):
        """Return a stable hard-metrics snapshot for PR review evidence."""
        return {
            'consistency_rate': round(self.consistency_rate, 2),
            'passed_checks': self.passed_checks,
            'total_checks': self.total_checks,
            'pollution_count': self.pollution_count,
            'half_write_intercepted': self.half_write_intercepted,
            'residual_params': self.residual_params,
            'reload_consistent': self.reload_consistent,
        }


metrics = Metrics()


def temp_config_dir():
    """Keep test temp files inside the repo to avoid host TEMP permission drift."""
    class _TempConfigDir:
        def __enter__(self):
            for old_file in test_tmp_root.glob('*.ini*'):
                old_file.unlink(missing_ok=True)
            return str(test_tmp_root)

        def __exit__(self, exc_type, exc, tb):
            for old_file in test_tmp_root.glob('*.ini*'):
                old_file.unlink(missing_ok=True)
            return False

    return _TempConfigDir()


def test_multi_instance_isolation():
    """测试多个 ChromiumOptions 实例并发修改后配置不串"""
    print("\n=== 测试: 多实例隔离 ===")
    metrics.total_checks += 1

    opt1 = ChromiumOptions(read_file=False)
    opt2 = ChromiumOptions(read_file=False)
    opt3 = ChromiumOptions(read_file=False)

    opt1.set_argument('--test-arg', 'opt1-value')
    opt1.set_user_data_path('/path/to/opt1')
    opt1.add_extension('/ext/opt1')
    opt1.set_pref('pref1', 'value1')

    opt2.set_argument('--test-arg', 'opt2-value')
    opt2.set_user_data_path('/path/to/opt2')
    opt2.add_extension('/ext/opt2')
    opt2.set_pref('pref2', 'value2')

    opt3.set_argument('--test-arg', 'opt3-value')
    opt3.set_user_data_path('/path/to/opt3')
    opt3.add_extension('/ext/opt3')
    opt3.set_pref('pref3', 'value3')

    errors = []

    if opt1._arguments is opt2._arguments:
        errors.append("opt1 和 opt2 共享 arguments 列表")
        metrics.pollution_count += 1
    if opt1._extensions is opt2._extensions:
        errors.append("opt1 和 opt2 共享 extensions 列表")
        metrics.pollution_count += 1
    if opt1._prefs is opt2._prefs:
        errors.append("opt1 和 opt2 共享 prefs 字典")
        metrics.pollution_count += 1
    if opt1._flags is opt2._flags:
        errors.append("opt1 和 opt2 共享 flags 字典")
        metrics.pollution_count += 1

    if '--test-arg=opt1-value' not in opt1._arguments:
        errors.append("opt1 参数丢失")
    if '--test-arg=opt2-value' not in opt2._arguments:
        errors.append("opt2 参数丢失")
    if '--test-arg=opt3-value' not in opt3._arguments:
        errors.append("opt3 参数丢失")

    if opt1.user_data_path != '/path/to/opt1':
        errors.append("opt1 user_data_path 错误")
    if opt2.user_data_path != '/path/to/opt2':
        errors.append("opt2 user_data_path 错误")

    if '/ext/opt1' not in opt1._extensions:
        errors.append("opt1 extensions 错误")
    if '/ext/opt2' not in opt2._extensions:
        errors.append("opt2 extensions 错误")

    if errors:
        print(f"FAILED: {errors}")
        return False

    metrics.passed_checks += 1
    print("PASSED: 多实例状态隔离")
    return True


def test_concurrent_modifications():
    """测试并发修改不互相污染"""
    print("\n=== 测试: 并发修改 ===")
    metrics.total_checks += 1

    num_threads = 10
    iterations = 50
    errors = []
    error_lock = threading.Lock()

    def modify_options(thread_id):
        try:
            for i in range(iterations):
                opt = ChromiumOptions(read_file=False)
                arg_name = f'--thread-{thread_id}-iter-{i}'
                opt.set_argument(arg_name, f'value-{thread_id}-{i}')
                opt.set_user_data_path(f'/path/thread/{thread_id}/{i}')
                opt.add_extension(f'/ext/thread/{thread_id}/{i}')
                opt.set_pref(f'pref.{thread_id}.{i}', f'v{thread_id}{i}')

                if arg_name not in str(opt._arguments):
                    with error_lock:
                        errors.append(f"线程 {thread_id}: 参数丢失")
                        metrics.pollution_count += 1

                if f'/path/thread/{thread_id}/{i}' != opt.user_data_path:
                    with error_lock:
                        errors.append(f"线程 {thread_id}: user_data_path 污染")
                        metrics.pollution_count += 1
        except Exception as e:
            with error_lock:
                errors.append(f"线程 {thread_id} 异常: {e}")

    threads = []
    for t in range(num_threads):
        thread = threading.Thread(target=modify_options, args=(t,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    if errors:
        print(f"FAILED: 发现 {len(errors)} 个并发问题")
        for e in errors[:10]:
            print(f"  - {e}")
        return False

    metrics.passed_checks += 1
    print("PASSED: 并发修改无污染")
    return True


def test_save_reload_consistency():
    """测试保存后重新加载，路径、参数、扩展顺序一致"""
    print("\n=== 测试: 保存重载一致性 ===")
    metrics.total_checks += 1

    with temp_config_dir() as tmpdir:
        ini_path = Path(tmpdir) / 'test_config.ini'

        opt = ChromiumOptions(read_file=False)
        test_args = ['--arg1=val1', '--arg2=val2', '--arg3=val3']
        for arg in test_args:
            if '=' in arg:
                k, v = arg.split('=', 1)
                opt.set_argument(k, v)
            else:
                opt.set_argument(arg)

        test_exts = ['/ext/ext1.crx', '/ext/ext2.crx', '/ext/ext3.crx']
        for ext in test_exts:
            opt.add_extension(ext)

        opt.set_user_data_path('/test/user/data')
        opt.set_cache_path('/test/cache')
        opt.set_pref('test.pref.nested', {'a': 1, 'b': 2})
        opt.set_flag('test-flag', 'flag-value')

        saved_path = opt.save(str(ini_path))

        opt2 = ChromiumOptions(ini_path=saved_path)

        errors = []

        for arg in test_args:
            if arg not in str(opt2._arguments):
                errors.append(f"参数丢失: {arg}")

        if len(opt2._extensions) != len(test_exts):
            errors.append(f"extensions 数量不匹配: {len(opt2._extensions)} vs {len(test_exts)}")
        else:
            for i, ext in enumerate(test_exts):
                if opt2._extensions[i] != ext:
                    errors.append(f"extensions 顺序/值不匹配: 位置{i}")

        if opt2.user_data_path != '/test/user/data':
            errors.append(f"user_data_path 不匹配: {opt2.user_data_path}")

        cache_arg_found = any('--disk-cache-dir=/test/cache' in a for a in opt2._arguments)
        if not cache_arg_found:
            errors.append(f"cache_path 未正确保存")

        if errors:
            print(f"FAILED: {errors}")
            metrics.residual_params += len(errors)
            return False

        metrics.passed_checks += 1
        metrics.reload_consistent += 1
        print("PASSED: 保存重载一致性")
        return True


def test_multiple_round_trips():
    """测试多轮保存加载无状态漂移"""
    print("\n=== 测试: 多轮往返无漂移 ===")
    metrics.total_checks += 1

    with temp_config_dir() as tmpdir:
        ini_path = Path(tmpdir) / 'roundtrip.ini'

        opt = ChromiumOptions(read_file=False)
        opt.set_argument('--stable-arg', 'stable-value')
        opt.set_user_data_path('/stable/path')
        opt.add_extension('/stable/ext1')
        opt.set_pref('stable.pref', 'stable')

        original_exts = list(opt._extensions)
        original_user_path = opt.user_data_path

        current_path = ini_path
        for round_num in range(10):
            saved_path = opt.save(str(current_path))
            opt = ChromiumOptions(ini_path=saved_path)
            current_path = Path(saved_path)
            metrics.reload_consistent += 1

        errors = []

        if '--stable-arg=stable-value' not in str(opt._arguments):
            errors.append(f"参数漂移: {opt._arguments}")

        if opt.user_data_path != original_user_path:
            errors.append(f"user_data_path 漂移: {opt.user_data_path} vs {original_user_path}")

        if opt._extensions != original_exts:
            errors.append(f"extensions 漂移: {opt._extensions} vs {original_exts}")

        if errors:
            print(f"FAILED: {errors}")
            metrics.residual_params += len(errors)
            return False

        metrics.passed_checks += 1
        print("PASSED: 多轮往返无状态漂移")
        return True


def test_remove_argument_no_residue():
    """测试删除/替换参数后不残留旧值"""
    print("\n=== 测试: 删除参数无残留 ===")
    metrics.total_checks += 1

    opt = ChromiumOptions(read_file=False)

    opt.set_argument('--test-param', 'old-value')
    opt.set_argument('--test-param', 'new-value')

    old_count = sum(1 for a in opt._arguments if a.startswith('--test-param'))
    if old_count > 1:
        print(f"FAILED: 参数替换后残留 {old_count} 个实例")
        metrics.residual_params += old_count - 1
        return False

    opt.set_argument('--to-remove', 'value')
    opt.remove_argument('--to-remove')

    if any(a.startswith('--to-remove') for a in opt._arguments):
        print(f"FAILED: 删除后参数仍残留: {opt._arguments}")
        metrics.residual_params += 1
        return False

    opt.set_argument('--headless', 'old')
    opt.set_argument('--headless', 'new')

    headless_count = sum(1 for a in opt._arguments if a.startswith('--headless'))
    if headless_count > 1:
        print(f"FAILED: headless 替换后残留 {headless_count} 个实例")
        metrics.residual_params += headless_count - 1
        return False

    metrics.passed_checks += 1
    print("PASSED: 删除/替换参数无残留")
    return True


def test_atomic_save_on_error():
    """测试覆盖保存时异常中断不破坏原配置"""
    print("\n=== 测试: 原子保存（异常不破坏原配置） ===")
    metrics.total_checks += 1

    with temp_config_dir() as tmpdir:
        ini_path = Path(tmpdir) / 'atomic_test.ini'

        opt = ChromiumOptions(read_file=False)
        opt.set_argument('--original-arg', 'original-value')
        opt.set_user_data_path('/original/path')
        original_saved = opt.save(str(ini_path))

        with open(original_saved, 'r', encoding='utf-8') as f:
            original_content = f.read()

        if '--original-arg' not in original_content:
            print("FAILED: 初始保存未包含预期内容")
            return False

        import builtins
        original_open = builtins.open
        fail_after_write = [False]

        def failing_open(*args, **kwargs):
            f = original_open(*args, **kwargs)
            if fail_after_write[0] and 'tmp' in str(args[0]):
                real_write = f.write

                def error_write(data):
                    real_write(data[:10])
                    raise IOError("模拟磁盘写入错误")

                f.write = error_write
            return f

        opt2 = ChromiumOptions(read_file=False)
        opt2.set_argument('--corrupted-arg', 'corrupted-value')
        opt2.set_user_data_path('/corrupted/path')

        builtins.open = failing_open
        fail_after_write[0] = True

        try:
            opt2.save(str(ini_path))
            print("WARNING: 保存没有按预期失败")
        except IOError:
            pass
        finally:
            builtins.open = original_open

        with open(original_saved, 'r', encoding='utf-8') as f:
            final_content = f.read()

        if '--corrupted-arg' in final_content:
            print("FAILED: 原配置被半写入数据污染")
            return False

        if '--original-arg' not in final_content:
            print("FAILED: 原配置内容丢失")
            return False

        metrics.half_write_intercepted += 1
        metrics.passed_checks += 1
        print("PASSED: 异常中断不破坏原配置")
        return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("ChromiumOptions 配置一致性测试")
    print("=" * 60)

    all_passed = True

    all_passed &= test_multi_instance_isolation()
    all_passed &= test_concurrent_modifications()
    all_passed &= test_save_reload_consistency()
    all_passed &= test_multiple_round_trips()
    all_passed &= test_remove_argument_no_residue()
    all_passed &= test_atomic_save_on_error()

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"配置一致率: {metrics.consistency_rate:.2f}%")
    print(f"通过检查数: {metrics.passed_checks}/{metrics.total_checks}")
    print(f"污染次数: {metrics.pollution_count}")
    print(f"半写入拦截次数: {metrics.half_write_intercepted}")
    print(f"残留参数数: {metrics.residual_params}")
    print(f"重载一致次数: {metrics.reload_consistent}")
    print(f"硬指标JSON: {json.dumps(metrics.snapshot(), ensure_ascii=False, sort_keys=True)}")

    if all_passed:
        print("\n[OK] 所有测试通过!")
        return 0
    else:
        print("\n[FAIL] 部分测试失败!")
        return 1


if __name__ == '__main__':
    exit_code = run_all_tests()
    print(f"\n$LASTEXITCODE = {exit_code}")
    sys.exit(exit_code)
