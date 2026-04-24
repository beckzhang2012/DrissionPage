# -*- coding: utf-8 -*-
"""
测试 Driver 在超时/重试/连接抖动下的结果一致性

测试覆盖：
1. 超时迟到：命令超时后，迟到响应必须丢弃
2. 重试晚到：重试后，旧命令的响应必须丢弃
3. 重连旧响应：重连后，旧会话的响应必须丢弃
4. 并发不串号：并发命令的响应不能串号
5. 多轮一致性：多轮操作后结果必须一致

输出：
- 终态一致率
- 重复终态拦截次数
- 迟到响应丢弃数
- 串号检测结果
- $LASTEXITCODE
"""
import sys
import threading
import time
from queue import Queue, Empty
from threading import Thread, Lock
from json import dumps, loads

sys.path.insert(0, '.')

from DrissionPage._base.driver import Driver


class MockWebSocket:
    """模拟 WebSocket，用于测试"""

    def __init__(self):
        self._received = []
        self._to_send = Queue()
        self._lock = Lock()
        self._closed = False

    def send(self, message):
        with self._lock:
            self._received.append(message)

    def recv(self):
        while not self._closed:
            try:
                return self._to_send.get(timeout=0.1)
            except:
                continue
        raise Exception("Connection closed")

    def close(self):
        self._closed = True

    def inject_response(self, response_json, delay=0):
        """注入响应，可指定延迟"""
        if delay > 0:
            def delayed_send():
                time.sleep(delay)
                if not self._closed:
                    self._to_send.put(response_json)

            t = Thread(target=delayed_send, daemon=True)
            t.start()
        else:
            self._to_send.put(response_json)


def create_test_driver(mock_ws):
    """创建测试用的 Driver 实例"""
    driver = object.__new__(Driver)
    driver.id = 'test-id'
    driver.address = 'ws://test:9222'
    driver.owner = None
    driver.alert_flag = False
    driver._cur_id = 0
    driver._ws = mock_ws
    driver._recv_th = Thread(target=driver._recv_loop)
    driver._handle_event_th = Thread(target=driver._handle_event_loop)
    driver._recv_th.daemon = True
    driver._handle_event_th.daemon = True
    driver._handle_immediate_event_th = None
    driver.is_running = False
    driver.session_id = None
    driver.event_handlers = {}
    driver.immediate_event_handlers = {}
    driver.method_results = {}
    driver.event_queue = Queue()
    driver.immediate_event_queue = Queue()
    driver._generation = 0
    driver._id_generation = {}
    driver._received_ids = set()
    driver._completed_ids = set()
    driver._lock = Lock()
    driver._stats = {
        'duplicate_final_states': 0,
        'late_responses_dropped': 0,
        'mismatch_generation_dropped': 0,
        'total_commands': 0,
        'consistent_completions': 0
    }
    return driver


def test_timeout_late_response():
    """测试1：超时后迟到响应必须丢弃"""
    print("\n" + "=" * 60)
    print("测试1：超时后迟到响应必须丢弃")
    print("=" * 60)

    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)

    try:
        driver.is_running = True
        driver._recv_th.start()
        driver._handle_event_th.start()

        result_received = []

        def send_with_timeout():
            result = driver._send({'method': 'Test.testMethod'}, timeout=0.3)
            result_received.append(result)

        sender = Thread(target=send_with_timeout)
        sender.start()

        time.sleep(0.6)

        mock_ws.inject_response('{"id": 1, "result": {"data": "late response"}}')

        sender.join(timeout=1)

        time.sleep(0.3)

        stats = driver._get_stats()
        print(f"  总命令数: {stats['total_commands_issued']}")
        print(f"  一致完成数: {stats['consistent_completions']}")
        print(f"  终态一致率: {stats['final_state_consistency_rate']:.2f}%")
        print(f"  迟到响应丢弃数: {stats['late_responses_dropped']}")

        assert len(result_received) == 1, "应该收到一个结果"
        result = result_received[0]
        assert result.get('type') == 'timeout', f"应该返回超时错误，实际: {result}"

        assert stats['final_state_consistency_rate'] == 100.0, "终态一致率应为100%"
        assert stats['late_responses_dropped'] >= 1, f"应该丢弃迟到响应，实际丢弃数: {stats['late_responses_dropped']}"

        print("  [PASS] 测试通过：超时后返回超时错误，迟到响应被丢弃")
        return True, stats

    except Exception as e:
        print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, {}
    finally:
        driver._stop()
        while driver._handle_event_th.is_alive() or driver._recv_th.is_alive():
            time.sleep(0.01)


def test_duplicate_final_state():
    """测试2：重复终态必须被拦截"""
    print("\n" + "=" * 60)
    print("测试2：重复终态必须被拦截")
    print("=" * 60)

    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)

    try:
        driver.is_running = True
        driver._recv_th.start()
        driver._handle_event_th.start()

        result_received = []

        def send_and_wait():
            result = driver._send({'method': 'Test.testMethod'}, timeout=1.0)
            result_received.append(result)

        sender = Thread(target=send_and_wait)
        sender.start()

        time.sleep(0.1)

        mock_ws.inject_response('{"id": 1, "result": {"data": "first response"}}')
        mock_ws.inject_response('{"id": 1, "result": {"data": "duplicate response"}}')

        sender.join(timeout=2)

        stats = driver._get_stats()
        print(f"  总命令数: {stats['total_commands_issued']}")
        print(f"  一致完成数: {stats['consistent_completions']}")
        print(f"  终态一致率: {stats['final_state_consistency_rate']:.2f}%")
        print(f"  重复终态拦截数: {stats['duplicate_final_states_intercepted']}")

        assert len(result_received) == 1, "应该只收到一个结果"
        result = result_received[0]
        assert 'result' in result, f"应该收到成功响应，实际: {result}"

        assert stats['duplicate_final_states_intercepted'] >= 1, "应该拦截重复终态"
        assert stats['final_state_consistency_rate'] == 100.0, "终态一致率应为100%"

        print("  [PASS] 测试通过：重复终态被拦截，只返回第一个结果")
        return True, stats

    except Exception as e:
        print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, {}
    finally:
        driver._stop()
        while driver._handle_event_th.is_alive() or driver._recv_th.is_alive():
            time.sleep(0.01)


def test_reconnect_old_generation():
    """测试3：重连后旧会话响应必须丢弃"""
    print("\n" + "=" * 60)
    print("测试3：重连后旧会话响应必须丢弃")
    print("=" * 60)

    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)

    try:
        driver.is_running = True
        driver._recv_th.start()
        driver._handle_event_th.start()

        gen_before = driver._get_stats()['current_generation']
        print(f"  重连前代号: {gen_before}")

        driver._cur_id = 5

        driver._stop()
        while driver._handle_event_th.is_alive() or driver._recv_th.is_alive():
            time.sleep(0.01)

        gen_after_stop = driver._generation
        print(f"  stop后代号: {gen_after_stop}")

        mock_ws2 = MockWebSocket()
        driver._ws = mock_ws2
        driver.is_running = True
        driver._recv_th = Thread(target=driver._recv_loop)
        driver._handle_event_th = Thread(target=driver._handle_event_loop)
        driver._recv_th.daemon = True
        driver._handle_event_th.daemon = True
        driver._recv_th.start()
        driver._handle_event_th.start()

        gen_after = driver._get_stats()['current_generation']
        print(f"  重连后代号: {gen_after}")

        assert gen_after > gen_before, "重连后generation应该增加"

        result_received = []

        def send_new():
            result = driver._send({'method': 'Test.newMethod'}, timeout=1.0)
            result_received.append(result)

        sender = Thread(target=send_new)
        sender.start()

        time.sleep(0.1)

        driver._id_generation[5] = gen_before
        mock_ws2.inject_response('{"id": 5, "result": {"data": "OLD generation response"}}')

        mock_ws2.inject_response('{"id": 1, "result": {"data": "NEW generation response"}}')

        sender.join(timeout=2)

        stats = driver._get_stats()
        print(f"  总命令数: {stats['total_commands_issued']}")
        print(f"  一致完成数: {stats['consistent_completions']}")
        print(f"  终态一致率: {stats['final_state_consistency_rate']:.2f}%")
        print(f"  旧世代响应丢弃数: {stats['old_generation_responses_dropped']}")

        assert len(result_received) == 1, "应该收到一个结果"
        result = result_received[0]
        assert 'result' in result, f"应该收到成功响应，实际: {result}"
        assert result['result'].get('data') == 'NEW generation response', f"应该返回新世代响应，实际: {result}"

        assert stats['old_generation_responses_dropped'] >= 1, "应该丢弃旧世代响应"
        assert stats['final_state_consistency_rate'] == 100.0, "终态一致率应为100%"

        print("  [PASS] 测试通过：旧世代响应被丢弃，新世代响应正确返回")
        return True, stats

    except Exception as e:
        print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, {}
    finally:
        driver._stop()
        while driver._handle_event_th.is_alive() or driver._recv_th.is_alive():
            time.sleep(0.01)


def test_concurrent_no_crosstalk():
    """测试4：并发命令不串号"""
    print("\n" + "=" * 60)
    print("测试4：并发命令不串号")
    print("=" * 60)

    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)

    try:
        driver.is_running = True
        driver._recv_th.start()
        driver._handle_event_th.start()

        results = {}
        results_lock = Lock()
        errors = []

        def send_command(cmd_id, expected_data):
            try:
                result = driver._send({'method': f'Test.cmd{cmd_id}'}, timeout=2.0)
                with results_lock:
                    results[cmd_id] = result

                actual_data = result.get('result', {}).get('data') if 'result' in result else None
                if actual_data != expected_data:
                    errors.append(f"命令{cmd_id}: 期望{expected_data}, 实际{actual_data}")
            except Exception as e:
                errors.append(f"命令{cmd_id}异常: {e}")

        threads = []
        for i in range(1, 6):
            t = Thread(target=send_command, args=(i, f"response-{i}"))
            threads.append(t)

        for t in threads:
            t.start()

        time.sleep(0.2)

        response_order = [3, 1, 5, 2, 4]
        for cmd_id in response_order:
            mock_ws.inject_response(f'{{"id": {cmd_id}, "result": {{"data": "response-{cmd_id}"}}}}')

        for t in threads:
            t.join(timeout=3)

        stats = driver._get_stats()
        print(f"  总命令数: {stats['total_commands_issued']}")
        print(f"  一致完成数: {stats['consistent_completions']}")
        print(f"  终态一致率: {stats['final_state_consistency_rate']:.2f}%")

        crosstalk_found = False
        for cmd_id in range(1, 6):
            result = results.get(cmd_id)
            if result:
                actual = result.get('result', {}).get('data') if 'result' in result else None
                expected = f"response-{cmd_id}"
                status = "OK" if actual == expected else "FAIL"
                if actual != expected:
                    crosstalk_found = True
                print(f"    命令{cmd_id}: {actual} (期望: {expected}) [{status}]")

        assert len(errors) == 0, f"发现串号错误: {errors}"
        assert len(results) == 5, f"应该收到5个结果，实际: {len(results)}"
        assert stats['final_state_consistency_rate'] == 100.0, "终态一致率应为100%"
        assert not crosstalk_found, "发现串号问题"

        print("  [PASS] 测试通过：并发命令无串号")
        return True, stats

    except Exception as e:
        print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, {}
    finally:
        driver._stop()
        while driver._handle_event_th.is_alive() or driver._recv_th.is_alive():
            time.sleep(0.01)


def test_multiple_round_consistency():
    """测试5：多轮一致性"""
    print("\n" + "=" * 60)
    print("测试5：多轮一致性")
    print("=" * 60)

    mock_ws = MockWebSocket()
    driver = create_test_driver(mock_ws)

    try:
        driver.is_running = True
        driver._recv_th.start()
        driver._handle_event_th.start()

        round_count = 10
        success_count = 0
        all_results = []

        for round_num in range(1, round_count + 1):
            result_received = []

            def send_round(rn):
                result = driver._send({'method': f'Test.round{rn}'}, timeout=1.0)
                result_received.append(result)

            sender = Thread(target=send_round, args=(round_num,))
            sender.start()

            time.sleep(0.05)

            mock_ws.inject_response(f'{{"id": {round_num}, "result": {{"data": "round-{round_num}"}}}}')
            mock_ws.inject_response(f'{{"id": {round_num}, "result": {{"data": "duplicate-{round_num}"}}}}')

            sender.join(timeout=2)

            if len(result_received) == 1:
                result = result_received[0]
                all_results.append(result)
                if 'result' in result and result['result'].get('data') == f"round-{round_num}":
                    success_count += 1
                    print(f"  轮次{round_num}: [OK] 成功")
                else:
                    print(f"  轮次{round_num}: [FAIL] 结果错误: {result}")
            else:
                print(f"  轮次{round_num}: [FAIL] 未收到结果或收到多个结果")

        stats = driver._get_stats()
        print(f"\n  统计:")
        print(f"    总轮次: {round_count}")
        print(f"    成功轮次: {success_count}")
        print(f"    总命令数: {stats['total_commands_issued']}")
        print(f"    一致完成数: {stats['consistent_completions']}")
        print(f"    终态一致率: {stats['final_state_consistency_rate']:.2f}%")
        print(f"    重复终态拦截数: {stats['duplicate_final_states_intercepted']}")

        assert success_count == round_count, f"多轮测试失败: {success_count}/{round_count} 成功"
        assert stats['final_state_consistency_rate'] == 100.0, "终态一致率应为100%"

        print("  [PASS] 测试通过：多轮操作一致")
        return True, stats

    except Exception as e:
        print(f"  [FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, {}
    finally:
        driver._stop()
        while driver._handle_event_th.is_alive() or driver._recv_th.is_alive():
            time.sleep(0.01)


def run_all_tests():
    """运行所有测试"""
    print("\n" + "#" * 60)
    print("# Driver 结果一致性测试")
    print("#" * 60)

    tests = [
        ("超时迟到响应丢弃", test_timeout_late_response),
        ("重复终态拦截", test_duplicate_final_state),
        ("重连旧会话响应丢弃", test_reconnect_old_generation),
        ("并发不串号", test_concurrent_no_crosstalk),
        ("多轮一致性", test_multiple_round_consistency),
    ]

    results = []
    all_stats = []

    for name, test_func in tests:
        success, stats = test_func()
        results.append((name, success))
        if stats:
            all_stats.append(stats)

    print("\n" + "#" * 60)
    print("# 测试结果汇总")
    print("#" * 60)

    passed = sum(1 for _, s in results if s)
    total = len(results)

    print(f"\n  测试结果: {passed}/{total} 通过")
    for name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"    {name}: [{status}]")

    if all_stats:
        total_commands = sum(s.get('total_commands_issued', 0) for s in all_stats)
        consistent_completions = sum(s.get('consistent_completions', 0) for s in all_stats)
        duplicate_intercepted = sum(s.get('duplicate_final_states_intercepted', 0) for s in all_stats)
        late_dropped = sum(s.get('late_responses_dropped', 0) for s in all_stats)
        old_gen_dropped = sum(s.get('old_generation_responses_dropped', 0) for s in all_stats)

        consistency_rate = 100.0 if total_commands == 0 else (consistent_completions / total_commands * 100)

        print(f"\n  全局统计:")
        print(f"    终态一致率: {consistency_rate:.2f}%")
        print(f"    重复终态拦截次数: {duplicate_intercepted}")
        print(f"    迟到响应丢弃数: {late_dropped}")
        print(f"    旧世代响应丢弃数: {old_gen_dropped}")
        print(f"    总命令数: {total_commands}")
        print(f"    一致完成数: {consistent_completions}")
        print(f"\n    串号检测: {'未发现串号' if passed == total else '存在串号问题'}")

    exit_code = 0 if passed == total else 1
    print(f"\n  退出码 ($LASTEXITCODE): {exit_code}")

    return passed == total


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
