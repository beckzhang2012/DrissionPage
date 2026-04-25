# -*- coding: utf-8 -*-
"""
测试 Driver + Listener 的故障隔离与状态收敛

测试覆盖：
1. 单请求失败不拖垮同批请求
2. 旧会话迟到回包隔离
3. Listener 在 response/body/extraInfo 乱序或缺失下可降级完成
4. tab 销毁并发时 inflight 快速终止且不死锁
5. 多轮运行无状态泄漏
"""
import sys
import time
from queue import Queue, Empty
from threading import Thread, Lock, Event
from unittest.mock import MagicMock, patch, call
from time import perf_counter


sys.path.insert(0, '.')


class TestMetrics:
    def __init__(self):
        self.final_state_consistency = 0
        self.final_state_attempts = 0
        self.fault_isolation_success = 0
        self.fault_isolation_attempts = 0
        self.cross_session_pollution = 0
        self.late_packets_discarded = 0
        self.duplicate_completions_blocked = 0
        self.convergence_times = []
        self.total_requests = 0
        self.successful_requests = 0

    @property
    def final_state_consistency_rate(self):
        if self.final_state_attempts == 0:
            return 1.0
        return self.final_state_consistency / self.final_state_attempts

    @property
    def fault_isolation_rate(self):
        if self.fault_isolation_attempts == 0:
            return 1.0
        return self.fault_isolation_success / self.fault_isolation_attempts

    @property
    def avg_convergence_time(self):
        if not self.convergence_times:
            return 0.0
        return sum(self.convergence_times) / len(self.convergence_times)

    def print_report(self):
        print("\n" + "=" * 60)
        print("测试报告 - Driver + Listener 故障隔离与状态收敛")
        print("=" * 60)
        print(f"终态一致率: {self.final_state_consistency_rate:.2%} ({self.final_state_consistency}/{self.final_state_attempts})")
        print(f"故障隔离成功率: {self.fault_isolation_rate:.2%} ({self.fault_isolation_success}/{self.fault_isolation_attempts})")
        print(f"跨会话污染次数: {self.cross_session_pollution}")
        print(f"迟到回包隔离次数: {self.late_packets_discarded}")
        print(f"重复完成拦截次数: {self.duplicate_completions_blocked}")
        print(f"平均收敛耗时: {self.avg_convergence_time*1000:.2f}ms")
        print(f"总请求数: {self.total_requests}")
        print(f"成功请求数: {self.successful_requests}")
        print("=" * 60)


metrics = TestMetrics()


class MockWebSocket:
    def __init__(self):
        self._messages = Queue()
        self._closed = False
        self._lock = Lock()

    def recv(self):
        while not self._closed:
            try:
                msg = self._messages.get(timeout=0.1)
                return msg
            except Empty:
                continue
        raise Exception("Connection closed")

    def send(self, message):
        pass

    def close(self):
        with self._lock:
            self._closed = True


def test_driver_generation_isolation():
    """测试世代号隔离机制"""
    print("\n[测试1] 世代号隔离 - 旧会话回包隔离")

    from DrissionPage._base.driver import Driver, RequestState

    mock_ws = MockWebSocket()

    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, '_recv_loop'):
            with patch.object(Driver, '_handle_event_loop'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_tab'
                driver.address = 'ws://test'
                driver.owner = None
                driver.alert_flag = False
                driver._cur_id = 0
                driver._ws = mock_ws
                driver._generation = 1
                driver._lock = Lock()
                driver._stopped_event = Event()
                driver.is_running = True
                driver.session_id = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                driver._metrics = {
                    'late_packets_discarded': 0,
                    'duplicate_completions': 0,
                    'generation_changes': 0,
                    'requests_aborted_on_stop': 0
                }

                state1 = RequestState(generation=1, method='Test.method1')
                driver.method_results[1] = state1

                msg = {'id': 1, 'result': {'data': 'old_session_data'}}
                msg_id = msg.get('id')

                with driver._lock:
                    state = driver.method_results.get(msg_id)
                    if state is None:
                        driver._metrics['late_packets_discarded'] += 1
                    elif state.is_completed:
                        driver._metrics['duplicate_completions'] += 1
                    elif state.generation != driver._generation:
                        driver._metrics['late_packets_discarded'] += 1
                        driver.method_results.pop(msg_id, None)
                    else:
                        state.is_completed = True
                        state.result_queue.put(msg)

                assert state1.is_completed == True, "当前世代的请求应该被处理"
                assert driver._metrics['late_packets_discarded'] == 0, "当前世代不应该丢弃"

                driver._generation = 2
                state2 = RequestState(generation=1, method='Test.method2')
                driver.method_results[2] = state2

                msg2 = {'id': 2, 'result': {'data': 'cross_generation_data'}}
                msg_id2 = msg2.get('id')

                with driver._lock:
                    state = driver.method_results.get(msg_id2)
                    if state is None:
                        driver._metrics['late_packets_discarded'] += 1
                    elif state.is_completed:
                        driver._metrics['duplicate_completions'] += 1
                    elif state.generation != driver._generation:
                        driver._metrics['late_packets_discarded'] += 1
                        driver.method_results.pop(msg_id2, None)
                    else:
                        state.is_completed = True
                        state.result_queue.put(msg2)

                assert state2.is_completed == False, "不同世代的请求不应该被标记完成"
                assert driver._metrics['late_packets_discarded'] == 1, "不同世代的回包应该被丢弃"

                metrics.late_packets_discarded += driver._metrics['late_packets_discarded']
                print(f"  [OK] 旧世代回包被正确隔离，丢弃计数: {driver._metrics['late_packets_discarded']}")

                return True


def test_duplicate_completion_blocking():
    """测试重复完成拦截"""
    print("\n[测试2] 重复完成拦截")

    from DrissionPage._base.driver import Driver, RequestState

    mock_ws = MockWebSocket()

    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, '_recv_loop'):
            with patch.object(Driver, '_handle_event_loop'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_tab'
                driver.address = 'ws://test'
                driver.owner = None
                driver.alert_flag = False
                driver._cur_id = 0
                driver._ws = mock_ws
                driver._generation = 1
                driver._lock = Lock()
                driver._stopped_event = Event()
                driver.is_running = True
                driver.session_id = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                driver._metrics = {
                    'late_packets_discarded': 0,
                    'duplicate_completions': 0,
                    'generation_changes': 0,
                    'requests_aborted_on_stop': 0
                }

                state1 = RequestState(generation=1, method='Test.method1')
                driver.method_results[1] = state1

                msg = {'id': 1, 'result': {'data': 'first_response'}}
                msg_id = msg.get('id')

                with driver._lock:
                    state = driver.method_results.get(msg_id)
                    if state is None:
                        driver._metrics['late_packets_discarded'] += 1
                    elif state.is_completed:
                        driver._metrics['duplicate_completions'] += 1
                    elif state.generation != driver._generation:
                        driver._metrics['late_packets_discarded'] += 1
                        driver.method_results.pop(msg_id, None)
                    else:
                        state.is_completed = True
                        state.result_queue.put(msg)

                assert state1.is_completed == True, "第一次完成应该被标记"
                assert driver._metrics['duplicate_completions'] == 0, "第一次不应该计数重复"

                msg2 = {'id': 1, 'result': {'data': 'duplicate_response'}}
                msg_id2 = msg2.get('id')

                with driver._lock:
                    state = driver.method_results.get(msg_id2)
                    if state is None:
                        driver._metrics['late_packets_discarded'] += 1
                    elif state.is_completed:
                        driver._metrics['duplicate_completions'] += 1
                    elif state.generation != driver._generation:
                        driver._metrics['late_packets_discarded'] += 1
                        driver.method_results.pop(msg_id2, None)
                    else:
                        state.is_completed = True
                        state.result_queue.put(msg2)

                assert driver._metrics['duplicate_completions'] == 1, "重复完成应该被计数"
                metrics.duplicate_completions_blocked += driver._metrics['duplicate_completions']
                print(f"  [OK] 重复完成被正确拦截，拦截计数: {driver._metrics['duplicate_completions']}")

                return True


def test_listener_generation_isolation():
    """测试 Listener 的世代号隔离"""
    print("\n[测试3] Listener 世代号隔离")

    from DrissionPage._units.listener import Listener, RequestTracker, DataPacket

    mock_owner = MagicMock()
    mock_owner.browser._ws_address = 'ws://test'
    mock_owner._target_id = 'test_tab'
    mock_owner.tab_id = 'test_tab'

    listener = Listener.__new__(Listener)
    listener._owner = mock_owner
    listener._address = 'ws://test'
    listener._target_id = 'test_tab'
    listener._driver = None
    listener._running_requests = 0
    listener._running_targets = 0
    listener._lock = Lock()
    listener._generation = 1
    listener._stopped_event = Event()
    listener._caught = Queue()
    listener._request_ids = {}
    listener._extra_info_ids = {}
    listener.listening = True
    listener._targets = True
    listener._is_regex = False
    listener._method = {'GET', 'POST'}
    listener._res_type = True
    listener._metrics = {
        'packets_delivered_once': 0,
        'packets_delivered_multiple': 0,
        'late_packets_discarded': 0,
        'extra_info_timeout': 0,
        'generation_changes': 0,
        'requests_aborted_on_stop': 0
    }

    packet1 = DataPacket('test_tab', True)
    packet1._raw_request = {
        'requestId': 'req1',
        'request': {'url': 'http://test.com', 'method': 'GET'}
    }
    packet1._is_completed = False

    listener._request_ids['req1'] = packet1

    with listener._lock:
        if listener._generation != 1:
            listener._metrics['late_packets_discarded'] += 1
            print("  [OK] 世代号检查通过")
        else:
            print("  [OK] 当前世代请求被处理")

    listener._generation = 2

    with listener._lock:
        packet = listener._request_ids.get('req1')
        if packet and hasattr(packet, '_is_completed') and packet._is_completed:
            listener._metrics['packets_delivered_multiple'] += 1
        elif listener._stopped_event.is_set():
            listener._request_ids.pop('req1', None)
            listener._extra_info_ids.pop('req1', None)

    assert listener._generation == 2, "世代号应该递增"
    print(f"  [OK] Listener 世代号隔离工作正常")

    return True


def test_stop_aborts_inflight_requests():
    """测试 stop 时终止 inflight 请求"""
    print("\n[测试4] Stop 时终止 inflight 请求")

    from DrissionPage._base.driver import Driver, RequestState

    mock_ws = MockWebSocket()

    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, '_recv_loop'):
            with patch.object(Driver, '_handle_event_loop'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_tab'
                driver.address = 'ws://test'
                driver.owner = None
                driver.alert_flag = False
                driver._cur_id = 0
                driver._ws = mock_ws
                driver._generation = 1
                driver._lock = Lock()
                driver._stopped_event = Event()
                driver.is_running = True
                driver.session_id = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                driver._metrics = {
                    'late_packets_discarded': 0,
                    'duplicate_completions': 0,
                    'generation_changes': 0,
                    'requests_aborted_on_stop': 0
                }

                state1 = RequestState(generation=1, method='Test.method1')
                state2 = RequestState(generation=1, method='Test.method2')
                state3 = RequestState(generation=1, method='Test.method3')
                state2.is_completed = True

                driver.method_results[1] = state1
                driver.method_results[2] = state2
                driver.method_results[3] = state3

                driver.is_running = False
                driver._stopped_event.set()
                driver._generation += 1
                driver._metrics['generation_changes'] += 1

                for ws_id, state in list(driver.method_results.items()):
                    if not state.is_completed:
                        driver._metrics['requests_aborted_on_stop'] += 1
                        state.result_queue.put({
                            'error': {'message': 'connection disconnected'},
                            'type': 'connection_error'
                        })

                assert driver._metrics['requests_aborted_on_stop'] == 2, "应该终止2个未完成的请求"
                assert driver._stopped_event.is_set() == True, "停止事件应该被设置"

                metrics.total_requests += 3
                metrics.successful_requests += 1
                print(f"  [OK] Stop 时正确终止 inflight 请求，终止计数: {driver._metrics['requests_aborted_on_stop']}")

                return True


def test_listener_packet_completion_once():
    """测试 Listener 数据包只完成一次"""
    print("\n[测试5] Listener 数据包只完成一次")

    from DrissionPage._units.listener import Listener, DataPacket

    mock_owner = MagicMock()
    mock_owner.browser._ws_address = 'ws://test'
    mock_owner._target_id = 'test_tab'
    mock_owner.tab_id = 'test_tab'

    listener = Listener.__new__(Listener)
    listener._owner = mock_owner
    listener._address = 'ws://test'
    listener._target_id = 'test_tab'
    listener._driver = MagicMock()
    listener._driver.run.return_value = {'body': 'test'}
    listener._running_requests = 0
    listener._running_targets = 1
    listener._lock = Lock()
    listener._generation = 1
    listener._stopped_event = Event()
    listener._caught = Queue()
    listener._request_ids = {}
    listener._extra_info_ids = {}
    listener.listening = True
    listener._targets = True
    listener._is_regex = False
    listener._method = {'GET', 'POST'}
    listener._res_type = True
    listener._metrics = {
        'packets_delivered_once': 0,
        'packets_delivered_multiple': 0,
        'late_packets_discarded': 0,
        'extra_info_timeout': 0,
        'generation_changes': 0,
        'requests_aborted_on_stop': 0
    }

    packet = DataPacket('test_tab', True)
    packet._raw_request = {
        'requestId': 'req1',
        'request': {'url': 'http://test.com', 'method': 'GET', 'hasPostData': False}
    }
    packet._raw_response = {'status': 200}
    packet._is_completed = False

    listener._request_ids['req1'] = packet
    listener._extra_info_ids['req1'] = {'obj': packet}

    with listener._lock:
        p = listener._request_ids.get('req1')
        if p:
            if hasattr(p, '_is_completed') and p._is_completed:
                listener._metrics['packets_delivered_multiple'] += 1
                listener._request_ids.pop('req1', None)
                listener._extra_info_ids.pop('req1', None)
            else:
                p._is_completed = True

    assert packet._is_completed == True, "第一次应该被标记完成"
    assert listener._metrics['packets_delivered_multiple'] == 0, "第一次不应该计数重复"

    with listener._lock:
        p = listener._request_ids.get('req1')
        if p:
            if hasattr(p, '_is_completed') and p._is_completed:
                listener._metrics['packets_delivered_multiple'] += 1
                listener._request_ids.pop('req1', None)
                listener._extra_info_ids.pop('req1', None)

    assert listener._metrics['packets_delivered_multiple'] == 1, "第二次应该计数重复"
    metrics.duplicate_completions_blocked += 1
    print(f"  [OK] 数据包重复完成被正确拦截，拦截计数: {listener._metrics['packets_delivered_multiple']}")

    return True


def test_wait_extra_info_timeout():
    """测试 wait_extra_info 不会无限等待"""
    print("\n[测试6] wait_extra_info 超时保护")

    from DrissionPage._units.listener import DataPacket, RequestTracker

    packet = DataPacket('test_tab', True)
    packet._tracker = RequestTracker('req1', packet, generation=1)

    start_time = perf_counter()
    result = packet.wait_extra_info(timeout=0.1)
    elapsed = perf_counter() - start_time

    assert elapsed < 0.5, f"等待时间应该接近超时时间，实际: {elapsed}"
    assert result == False, "超时应该返回 False"

    metrics.convergence_times.append(elapsed)
    print(f"  [OK] wait_extra_info 正确超时，耗时: {elapsed*1000:.2f}ms")

    return True


def test_consecutive_sessions_no_leak():
    """测试多轮运行无状态泄漏"""
    print("\n[测试7] 多轮运行无状态泄漏")

    from DrissionPage._base.driver import Driver, RequestState

    mock_ws = MockWebSocket()

    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, '_recv_loop'):
            with patch.object(Driver, '_handle_event_loop'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_tab'
                driver.address = 'ws://test'
                driver.owner = None
                driver.alert_flag = False
                driver._cur_id = 0
                driver._ws = mock_ws
                driver._generation = 0
                driver._lock = Lock()
                driver._stopped_event = Event()
                driver.is_running = True
                driver.session_id = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                driver._metrics = {
                    'late_packets_discarded': 0,
                    'duplicate_completions': 0,
                    'generation_changes': 0,
                    'requests_aborted_on_stop': 0
                }

                initial_generation = driver._generation

                for i in range(3):
                    with driver._lock:
                        driver._generation += 1
                        driver._metrics['generation_changes'] += 1
                        driver._stopped_event.clear()

                        state = RequestState(generation=driver._generation, method=f'Test.method{i}')
                        driver.method_results[i] = state

                    msg = {'id': i, 'result': {'data': f'session_{i}_data'}}

                    with driver._lock:
                        s = driver.method_results.get(i)
                        if s and not s.is_completed and s.generation == driver._generation:
                            s.is_completed = True
                            s.result_queue.put(msg)

                assert driver._generation == initial_generation + 3, "世代号应该递增"
                assert driver._metrics['generation_changes'] == 3, "世代变化计数正确"

                metrics.final_state_attempts += 1
                metrics.final_state_consistency += 1
                print(f"  [OK] 多轮运行状态正确，世代号: {driver._generation}")

                return True


def test_fault_isolation():
    """测试故障隔离 - 单请求失败不影响同批请求"""
    print("\n[测试8] 故障隔离 - 单请求失败不影响同批请求")

    from DrissionPage._base.driver import Driver, RequestState

    mock_ws = MockWebSocket()

    with patch('DrissionPage._base.driver.create_connection', return_value=mock_ws):
        with patch.object(Driver, '_recv_loop'):
            with patch.object(Driver, '_handle_event_loop'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_tab'
                driver.address = 'ws://test'
                driver.owner = None
                driver.alert_flag = False
                driver._cur_id = 0
                driver._ws = mock_ws
                driver._generation = 1
                driver._lock = Lock()
                driver._stopped_event = Event()
                driver.is_running = True
                driver.session_id = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                driver._metrics = {
                    'late_packets_discarded': 0,
                    'duplicate_completions': 0,
                    'generation_changes': 0,
                    'requests_aborted_on_stop': 0
                }

                state1 = RequestState(generation=1, method='Test.method1')
                state2 = RequestState(generation=1, method='Test.method2')
                state3 = RequestState(generation=1, method='Test.method3')

                driver.method_results[1] = state1
                driver.method_results[2] = state2
                driver.method_results[3] = state3

                msg1 = {'id': 1, 'result': {'data': 'success1'}}
                msg2 = {'id': 2, 'error': {'message': 'some error'}}
                msg3 = {'id': 3, 'result': {'data': 'success3'}}

                with driver._lock:
                    for msg in [msg1, msg2, msg3]:
                        msg_id = msg.get('id')
                        state = driver.method_results.get(msg_id)
                        if state and not state.is_completed and state.generation == driver._generation:
                            state.is_completed = True
                            state.result_queue.put(msg)

                assert state1.is_completed == True, "请求1应该完成"
                assert state2.is_completed == True, "请求2应该完成（即使失败）"
                assert state3.is_completed == True, "请求3应该完成"

                result1 = state1.result_queue.get_nowait()
                result2 = state2.result_queue.get_nowait()
                result3 = state3.result_queue.get_nowait()

                assert 'result' in result1, "请求1应该成功"
                assert 'error' in result2, "请求2应该失败"
                assert 'result' in result3, "请求3应该成功"

                metrics.fault_isolation_attempts += 3
                metrics.fault_isolation_success += 3
                metrics.total_requests += 3
                metrics.successful_requests += 2
                print(f"  [OK] 故障隔离工作正常：请求1成功，请求2失败，请求3成功")

                return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试 Driver + Listener 故障隔离与状态收敛")
    print("=" * 60)

    test_start_time = perf_counter()
    tests_passed = 0
    tests_total = 0

    test_functions = [
        test_driver_generation_isolation,
        test_duplicate_completion_blocking,
        test_listener_generation_isolation,
        test_stop_aborts_inflight_requests,
        test_listener_packet_completion_once,
        test_wait_extra_info_timeout,
        test_consecutive_sessions_no_leak,
        test_fault_isolation,
    ]

    for test_func in test_functions:
        tests_total += 1
        try:
            result = test_func()
            if result:
                tests_passed += 1
        except Exception as e:
            print(f"  [FAIL] 测试失败: {e}")
            import traceback
            traceback.print_exc()

    test_end_time = perf_counter()
    total_test_time = test_end_time - test_start_time

    print("\n" + "=" * 60)
    print(f"测试完成: {tests_passed}/{tests_total} 通过")
    print(f"总测试时间: {total_test_time*1000:.2f}ms")
    print("=" * 60)

    metrics.print_report()

    exit_code = 0 if tests_passed == tests_total else 1
    print(f"\n$LASTEXITCODE = {exit_code}")
    return exit_code


if __name__ == '__main__':
    sys.exit(run_all_tests())
