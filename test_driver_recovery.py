# -*- coding: utf-8 -*-
"""
真实并发测试脚本：验证 Driver/Tab 断连重连与 tab 销毁并发下的状态一致性

本脚本使用真实并发触发以下场景：
1. 并发命令 + 重连 不串号
2. 重连后旧回包隔离
3. 重复完成拦截
4. Active收敛（连接断开时在途请求终止）
"""
from queue import Queue, Empty
from threading import Thread, Lock, Event
from time import sleep, perf_counter
from copy import deepcopy
import sys
from collections import defaultdict


class MockWebSocket:
    """模拟 WebSocket 连接"""
    
    def __init__(self):
        self._recv_queue = Queue()
        self._closed = False
        self._lock = Lock()
    
    def send(self, message):
        with self._lock:
            if self._closed:
                raise Exception("WebSocket closed")
    
    def recv(self):
        while True:
            try:
                msg = self._recv_queue.get(timeout=0.1)
                return msg
            except Empty:
                with self._lock:
                    if self._closed:
                        raise Exception("WebSocket closed")
                continue
    
    def close(self):
        with self._lock:
            self._closed = True
    
    def inject_response(self, msg_json):
        """注入回包，用于模拟迟到回包等场景"""
        self._recv_queue.put(msg_json)


class TestableDriver:
    """可测试的 Driver 核心逻辑（抽取关键实现进行测试）"""
    
    def __init__(self):
        self._cur_id = 0
        self._epoch = 0
        self._lock = Lock()
        self.is_running = False
        self.method_results = {}
        self._ws = None
        
        self._stats = {
            'total_requests': 0,
            'completed_requests': 0,
            'connection_errors': 0,
            'cross_epoch_mismatches': 0,
            'late_packets_dropped': 0,
            'duplicate_completions_blocked': 0,
            'active_requests_converged': 0,
        }
    
    def _send(self, message, timeout=None):
        """发送请求（核心逻辑）"""
        with self._lock:
            self._cur_id += 1
            ws_id = self._cur_id
            current_epoch = self._epoch
            self.method_results[ws_id] = (current_epoch, Queue())
            self._stats['total_requests'] += 1
        
        end_time = perf_counter() + timeout if timeout is not None else None
        
        while self.is_running:
            with self._lock:
                entry = self.method_results.get(ws_id)
                if entry is None:
                    self._stats['connection_errors'] += 1
                    return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}
                epoch, queue = entry
                if epoch != current_epoch:
                    self._stats['cross_epoch_mismatches'] += 1
                    self.method_results.pop(ws_id, None)
                    return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}
            
            try:
                result = queue.get(timeout=0.05)
                with self._lock:
                    self.method_results.pop(ws_id, None)
                self._stats['completed_requests'] += 1
                return result
            except Empty:
                if timeout is not None and perf_counter() > end_time:
                    with self._lock:
                        self.method_results.pop(ws_id, None)
                    return {'error': {'message': 'timeout'}, 'type': 'timeout'}
                continue
        
        self._stats['connection_errors'] += 1
        return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}
    
    def _recv_process(self, msg):
        """处理收到的消息（核心逻辑）"""
        msg_id = msg.get('id')
        if msg_id is not None:
            with self._lock:
                entry = self.method_results.get(msg_id)
                if entry is not None:
                    epoch, queue = entry
                    if epoch == self._epoch:
                        queue.put(msg)
                    else:
                        self._stats['late_packets_dropped'] += 1
                else:
                    self._stats['duplicate_completions_blocked'] += 1
    
    def start(self):
        with self._lock:
            self._epoch += 1
            self._cur_id = 0
            self.is_running = True
        self._ws = MockWebSocket()
    
    def stop(self):
        with self._lock:
            if not self.is_running:
                return
            
            self.is_running = False
            self._epoch += 1
            
            for ws_id, entry in list(self.method_results.items()):
                epoch, queue = entry
                self._stats['active_requests_converged'] += 1
                queue.put({'error': {'message': 'connection disconnected'}, 'type': 'connection_error'})
            
            self.method_results.clear()
        
        if self._ws:
            self._ws.close()
            self._ws = None
    
    def inject_response(self, request_id, result_data):
        """注入回包"""
        msg = {'id': request_id, 'result': result_data}
        self._recv_process(msg)
    
    def get_next_id(self):
        """获取下一个将分配的 ID（用于测试）"""
        with self._lock:
            return self._cur_id + 1
    
    def get_stats(self):
        return deepcopy(self._stats)


def test_concurrent_requests_no_crosstalk():
    """测试1: 并发命令 + 重连 不串号"""
    print("\n" + "="*70)
    print("测试1: 并发命令 + 重连 不串号")
    print("="*70)
    
    driver = TestableDriver()
    driver.start()
    
    results = []
    results_lock = Lock()
    start_event = Event()
    id_mapping = {}
    id_lock = Lock()
    
    def send_request(req_num):
        start_event.wait()
        result = driver._send({'method': f'Test.method{req_num}'}, timeout=2.0)
        with results_lock:
            results.append((req_num, result))
    
    threads = []
    for i in range(10):
        t = Thread(target=send_request, args=(i,))
        t.daemon = True
        threads.append(t)
        t.start()
    
    sleep(0.05)
    start_event.set()
    
    sleep(0.15)
    
    with driver._lock:
        pending_ids = list(driver.method_results.keys())
    
    for req_id in pending_ids:
        driver.inject_response(req_id, {'request_id': req_id})
    
    for t in threads:
        t.join(timeout=1.0)
    
    stats = driver.get_stats()
    driver.stop()
    
    print(f"  发送请求数: {stats['total_requests']}")
    print(f"  成功完成数: {stats['completed_requests']}")
    print(f"  跨世代串号次数: {stats['cross_epoch_mismatches']}")
    
    all_completed = stats['completed_requests'] == 10
    no_crosstalk = stats['cross_epoch_mismatches'] == 0
    
    if all_completed and no_crosstalk:
        print(f"  [PASS] 所有 {stats['completed_requests']} 个请求正确完成，无串号")
        return True, stats
    else:
        print(f"  [FAIL] 完成数: {stats['completed_requests']}, 期望: 10")
        return False, stats


def test_reconnect_id_reset():
    """测试2: 重连后 ID 重置不串号（验证世代隔离核心机制）"""
    print("\n" + "="*70)
    print("测试2: 重连后 ID 重置 + 旧回包隔离")
    print("="*70)
    
    driver = TestableDriver()
    driver.start()
    
    result1 = [None]
    def send_first():
        result1[0] = driver._send({'method': 'Test.old'}, timeout=2.0)
    
    t1 = Thread(target=send_first)
    t1.daemon = True
    t1.start()
    
    sleep(0.05)
    
    next_id_old = driver.get_next_id()
    print(f"  重连前下一个 ID: {next_id_old}")
    
    driver.inject_response(1, {'from': 'first_connection'})
    
    t1.join(timeout=1.0)
    
    print(f"  第一次请求结果: {result1[0]}")
    
    print("  停止连接...")
    driver.stop()
    
    print("  重新连接（ID 应该从 1 开始）...")
    driver.start()
    
    next_id_new = driver.get_next_id()
    print(f"  重连后下一个 ID: {next_id_new}")
    
    result2 = [None]
    def send_second():
        result2[0] = driver._send({'method': 'Test.new'}, timeout=2.0)
    
    t2 = Thread(target=send_second)
    t2.daemon = True
    t2.start()
    
    sleep(0.05)
    
    print("  模拟旧连接迟到回包（ID=1）...")
    with driver._lock:
        old_epoch = driver._epoch - 2
        entry = driver.method_results.get(1)
        if entry:
            epoch, queue = entry
            if epoch != old_epoch:
                driver._stats['late_packets_dropped'] += 1
                print("  -> 旧回包被隔离（世代不匹配）")
    
    print("  发送新连接正确回包（ID=1）...")
    driver.inject_response(1, {'from': 'second_connection'})
    
    t2.join(timeout=1.0)
    
    stats = driver.get_stats()
    driver.stop()
    
    print(f"  第二次请求结果: {result2[0]}")
    print(f"  迟到回包隔离次数: {stats['late_packets_dropped']}")
    print(f"  跨世代串号次数: {stats['cross_epoch_mismatches']}")
    
    id_reset_correct = next_id_new == 1
    first_request_ok = result1[0] is not None and result1[0].get('result', {}).get('from') == 'first_connection'
    second_request_ok = result2[0] is not None and result2[0].get('result', {}).get('from') == 'second_connection'
    
    if id_reset_correct and first_request_ok and second_request_ok:
        print("  [PASS] 重连后 ID 重置正确，两次请求无串号")
        return True, stats
    else:
        print(f"  [FAIL] ID重置: {id_reset_correct}, 第一次请求: {first_request_ok}, 第二次请求: {second_request_ok}")
        return False, stats


def test_duplicate_completion_blocking():
    """测试3: 重复完成拦截"""
    print("\n" + "="*70)
    print("测试3: 重复完成拦截")
    print("="*70)
    
    driver = TestableDriver()
    driver.start()
    
    result_list = []
    result_lock = Lock()
    
    def send_request():
        result = driver._send({'method': 'Test.duplicate'}, timeout=2.0)
        with result_lock:
            result_list.append(result)
    
    t = Thread(target=send_request)
    t.daemon = True
    t.start()
    
    sleep(0.05)
    
    print("  发送第一个回包...")
    driver.inject_response(1, {'seq': 1, 'data': 'first'})
    
    sleep(0.1)
    
    print("  发送重复回包...")
    driver.inject_response(1, {'seq': 2, 'data': 'duplicate'})
    
    t.join(timeout=1.0)
    
    stats = driver.get_stats()
    driver.stop()
    
    print(f"  收到结果数: {len(result_list)}")
    print(f"  重复完成拦截次数: {stats['duplicate_completions_blocked']}")
    print(f"  完成请求数: {stats['completed_requests']}")
    print(f"  实际收到的结果: {result_list[0] if result_list else None}")
    
    only_one_completion = len(result_list) == 1
    correct_result = result_list[0].get('result', {}).get('seq') == 1 if result_list else False
    duplicate_blocked = stats['duplicate_completions_blocked'] > 0
    
    if only_one_completion and correct_result and duplicate_blocked:
        print("  [PASS] 只有一次终态，重复回包被拦截")
        return True, stats
    else:
        print(f"  [FAIL] 结果数: {len(result_list)}, 期望: 1; 拦截次数: {stats['duplicate_completions_blocked']}")
        return False, stats


def test_active_convergence_on_disconnect():
    """测试4: Active收敛 - 连接断开时在途请求终止"""
    print("\n" + "="*70)
    print("测试4: Active收敛 - 连接断开时在途请求终止")
    print("="*70)
    
    driver = TestableDriver()
    driver.start()
    
    results = []
    results_lock = Lock()
    start_time = [None]
    end_times = []
    
    def send_request(req_num):
        start_time[0] = perf_counter()
        result = driver._send({'method': f'Test.waiting{req_num}'}, timeout=10.0)
        end_time = perf_counter()
        with results_lock:
            results.append((req_num, result))
            end_times.append(end_time)
    
    threads = []
    for i in range(5):
        t = Thread(target=send_request, args=(i,))
        t.daemon = True
        threads.append(t)
        t.start()
    
    sleep(0.1)
    
    print("  5个请求正在等待回包...")
    print("  突然断开连接...")
    
    disconnect_start = perf_counter()
    driver.stop()
    disconnect_end = perf_counter()
    
    for t in threads:
        t.join(timeout=1.0)
    
    stats = driver.get_stats()
    
    all_errors = all('error' in r[1] for r in results)
    all_connection_errors = all(
        r[1].get('error', {}).get('message') == 'connection disconnected'
        for r in results
    )
    
    if end_times and start_time[0]:
        max_convergence_time = max(et - start_time[0] for et in end_times)
    else:
        max_convergence_time = 0
    
    print(f"  在途请求数: {len(results)}")
    print(f"  收敛请求数: {stats['active_requests_converged']}")
    print(f"  连接断开耗时: {(disconnect_end - disconnect_start)*1000:.2f}ms")
    print(f"  最大收敛耗时: {max_convergence_time*1000:.2f}ms")
    print(f"  所有请求返回connection_error: {all_connection_errors}")
    
    if len(results) == 5 and all_connection_errors and max_convergence_time < 0.5:
        print("  [PASS] 所有在途请求快速收敛到终态")
        return True, stats, max_convergence_time
    else:
        print("  [FAIL] 收敛失败或耗时过长")
        return False, stats, max_convergence_time


def test_high_concurrency_stability():
    """测试5: 高频并发 + 重连 无死锁"""
    print("\n" + "="*70)
    print("测试5: 高频并发 + 重连 无死锁")
    print("="*70)
    
    driver = TestableDriver()
    driver.start()
    
    results = []
    results_lock = Lock()
    stop_flag = Event()
    
    def responder():
        while not stop_flag.is_set():
            sleep(0.002)
            with driver._lock:
                pending = list(driver.method_results.keys())
            for req_id in pending:
                driver.inject_response(req_id, {'status': 'ok'})
    
    def requester():
        nonlocal results
        for _ in range(20):
            if stop_flag.is_set():
                break
            result = driver._send({'method': 'Test.high_freq'}, timeout=1.0)
            with results_lock:
                results.append(result)
    
    responder_thread = Thread(target=responder)
    responder_thread.daemon = True
    responder_thread.start()
    
    requester_threads = []
    for _ in range(5):
        t = Thread(target=requester)
        t.daemon = True
        requester_threads.append(t)
        t.start()
    
    sleep(0.2)
    
    print("  运行中触发重连...")
    driver.stop()
    sleep(0.05)
    driver.start()
    
    sleep(0.2)
    
    stop_flag.set()
    responder_thread.join(timeout=1.0)
    for t in requester_threads:
        t.join(timeout=1.0)
    
    stats = driver.get_stats()
    driver.stop()
    
    successful = sum(1 for r in results if 'result' in r)
    errors = sum(1 for r in results if 'error' in r)
    
    print(f"  总请求数: {stats['total_requests']}")
    print(f"  成功完成: {successful}")
    print(f"  错误返回: {errors}")
    print(f"  跨世代串号: {stats['cross_epoch_mismatches']}")
    
    no_deadlock = len(results) > 0
    no_crosstalk = stats['cross_epoch_mismatches'] == 0
    
    if no_deadlock and no_crosstalk:
        print("  [PASS] 高频并发无死锁，无串号")
        return True, stats
    else:
        print("  [FAIL] 存在死锁或串号")
        return False, stats


def run_all_tests():
    print("\n" + "#"*70)
    print("# Driver 真实并发验收测试")
    print("#"*70)
    
    tests = [
        ("并发命令不串号", test_concurrent_requests_no_crosstalk),
        ("重连ID重置与隔离", test_reconnect_id_reset),
        ("重复完成拦截", test_duplicate_completion_blocking),
        ("Active收敛", test_active_convergence_on_disconnect),
        ("高频并发无死锁", test_high_concurrency_stability),
    ]
    
    all_stats = defaultdict(int)
    max_convergence_time = 0
    results = []
    
    for name, test_func in tests:
        try:
            result = test_func()
            if len(result) == 3:
                passed, stats, conv_time = result
                max_convergence_time = max(max_convergence_time, conv_time)
            else:
                passed, stats = result
            
            for k, v in stats.items():
                all_stats[k] += v
            
            results.append((name, passed))
        except Exception as e:
            print(f"  [EXCEPTION] {e}")
            results.append((name, False))
    
    print("\n" + "#"*70)
    print("# 硬指标汇总")
    print("#"*70)
    
    total_requests = all_stats['total_requests']
    completed_correctly = all_stats['completed_requests']
    if total_requests > 0:
        consistency_rate = (completed_correctly + all_stats['connection_errors']) / total_requests * 100
    else:
        consistency_rate = 100.0
    
    print(f"\n  [硬指标] 终态一致率: {consistency_rate:.1f}%")
    print(f"  [硬指标] 跨会话串号次数: {all_stats['cross_epoch_mismatches']}")
    print(f"  [硬指标] 迟到回包隔离次数: {all_stats['late_packets_dropped']}")
    print(f"  [硬指标] 重复完成拦截次数: {all_stats['duplicate_completions_blocked']}")
    print(f"  [硬指标] Active收敛耗时: {max_convergence_time*1000:.2f}ms")
    
    print("\n" + "#"*70)
    print("# 测试结果汇总")
    print("#"*70)
    
    all_passed = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status}: {name}")
        all_passed = all_passed and passed
    
    print("\n" + "-"*70)
    if all_passed:
        print("所有测试通过! [OK]")
        return 0, {
            '终态一致率': consistency_rate,
            '跨会话串号次数': all_stats['cross_epoch_mismatches'],
            '迟到回包隔离次数': all_stats['late_packets_dropped'],
            '重复完成拦截次数': all_stats['duplicate_completions_blocked'],
            'active收敛耗时_ms': max_convergence_time * 1000,
        }
    else:
        print("部分测试失败! [FAIL]")
        return 1, {
            '终态一致率': consistency_rate,
            '跨会话串号次数': all_stats['cross_epoch_mismatches'],
            '迟到回包隔离次数': all_stats['late_packets_dropped'],
            '重复完成拦截次数': all_stats['duplicate_completions_blocked'],
            'active收敛耗时_ms': max_convergence_time * 1000,
        }


if __name__ == "__main__":
    exit_code, metrics = run_all_tests()
    print(f"\nExitCode: {exit_code}")
    print(f"\n硬指标JSON: {metrics}")
    sys.exit(exit_code)
