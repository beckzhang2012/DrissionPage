# -*- coding: utf-8 -*-
"""
验收测试文件：事件队列背压与公平调度
====================================
验证指标：
1) 吞吐 (throughput_events_per_second)
2) 最大等待时延 (max_wait_time_seconds)
3) 事件丢弃统计 (dropped_by_priority, dropped_by_method)
4) 公平性指标 (fairness_index)
5) $LASTEXITCODE

测试覆盖：
- 高并发突发写入
- 长短任务混合
- 背压触发丢弃策略
- 多轮一致性（无状态漂移）
- 兼容性回归：普通事件与即时事件路径
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Event
from typing import List, Dict, Any

sys.path.insert(0, '.')

from DrissionPage._base.driver import (
    BackPressureEventQueue,
    EventPriority,
    PriorityBasedEventMethodMapper,
)


class TestRunner:
    def __init__(self):
        self.results = []
        self.exit_code = 0

    def run_test(self, test_func, test_name):
        print(f"\n{'='*60}")
        print(f"测试: {test_name}")
        print(f"{'='*60}")
        try:
            result = test_func()
            self.results.append(result)
            if result.get('passed', False):
                print(f"  ✓ 通过")
            else:
                print(f"  ✗ 失败")
                self.exit_code = 1
            return result
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            import traceback
            traceback.print_exc()
            self.results.append({'test': test_name, 'passed': False, 'error': str(e)})
            self.exit_code = 1
            return None

    def print_summary(self):
        print(f"\n{'='*60}")
        print("测试汇总")
        print(f"{'='*60}")
        
        all_passed = True
        for result in self.results:
            if result:
                status = "通过" if result.get('passed', False) else "失败"
                print(f"  {result.get('test', 'unknown')}: {status}")
                if not result.get('passed', False):
                    all_passed = False
        
        print(f"\n{'-'*60}")
        print(f"  总体结果: {'全部通过' if all_passed else '部分失败'}")
        print(f"{'-'*60}")
        
        print(f"\n$LASTEXITCODE = {self.exit_code}")
        return self.exit_code


def test_1_high_concurrency_throughput() -> Dict[str, Any]:
    """
    测试1：高并发突发写入下吞吐稳定
    验证：在突发大量事件时，队列能够稳定处理
    """
    queue = BackPressureEventQueue(capacity=1000, drop_strategy='oldest_low_priority_first')
    stop_event = Event()
    
    processed_events = []
    processed_lock = Event()
    
    def consumer():
        while not stop_event.is_set() or not queue.empty():
            try:
                result = queue.get(timeout=0.1)
                if result:
                    event, method = result
                    processed_events.append((method, time.perf_counter()))
            except Exception:
                pass
    
    consumer_thread = Thread(target=consumer, daemon=True)
    consumer_thread.start()
    
    num_producers = 10
    events_per_producer = 200
    total_events = num_producers * events_per_producer
    
    start_time = time.perf_counter()
    
    def producer(pid):
        for i in range(events_per_producer):
            method = f'Test.event_{pid % 3}'
            event = {'pid': pid, 'seq': i, 'method': method}
            queue.put(event, method)
    
    with ThreadPoolExecutor(max_workers=num_producers) as executor:
        futures = [executor.submit(producer, i) for i in range(num_producers)]
        for future in as_completed(futures):
            future.result()
    
    stop_event.set()
    consumer_thread.join(timeout=5)
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    
    stats = queue.get_statistics()
    
    processed = len(processed_events)
    dropped = stats['total_dropped']
    throughput = processed / elapsed if elapsed > 0 else 0
    
    print(f"  总事件数: {total_events}")
    print(f"  已处理: {processed}")
    print(f"  已丢弃: {dropped}")
    print(f"  耗时: {elapsed:.3f}秒")
    print(f"  吞吐率: {throughput:.2f} 事件/秒")
    print(f"  公平性指数: {stats['fairness_index']:.4f}")
    print(f"  最大等待时间: {stats['max_wait_time_seconds']:.4f}秒")
    
    queue.stop()
    
    passed = processed > 0 and throughput > 0
    
    return {
        'test': 'high_concurrency_throughput',
        'total_events': total_events,
        'processed': processed,
        'dropped': dropped,
        'elapsed_seconds': elapsed,
        'throughput_events_per_second': throughput,
        'max_wait_time_seconds': stats['max_wait_time_seconds'],
        'average_wait_time_seconds': stats['average_wait_time_seconds'],
        'fairness_index': stats['fairness_index'],
        'passed': passed,
    }


def test_2_mixed_tasks_wait_time() -> Dict[str, Any]:
    """
    测试2：长短任务混合下最大等待时延可控
    验证：即使有长时间运行的任务，其他事件的等待时间也不会无限增长
    """
    queue = BackPressureEventQueue(capacity=500, drop_strategy='oldest_low_priority_first')
    
    short_task_methods = ['Short.task1', 'Short.task2', 'Short.task3']
    long_task_method = 'Long.task'
    
    processed_timestamps = []
    processing_times = []
    
    def consumer():
        while len(processed_timestamps) < 200:
            result = queue.get(timeout=0.5)
            if result:
                event, method = result
                start_process = time.perf_counter()
                
                if method == long_task_method:
                    time.sleep(0.05)
                else:
                    time.sleep(0.001)
                
                end_process = time.perf_counter()
                processing_times.append(end_process - start_process)
                processed_timestamps.append((method, time.perf_counter()))
    
    consumer_thread = Thread(target=consumer, daemon=True)
    consumer_thread.start()
    
    for i in range(100):
        for method in short_task_methods:
            event = {'type': 'short', 'seq': i, 'method': method}
            queue.put(event, method)
        
        if i % 5 == 0:
            event = {'type': 'long', 'seq': i, 'method': long_task_method}
            queue.put(event, long_task_method)
    
    consumer_thread.join(timeout=10)
    
    stats = queue.get_statistics()
    
    print(f"  总处理事件: {len(processed_timestamps)}")
    print(f"  最大等待时间: {stats['max_wait_time_seconds']:.4f}秒")
    print(f"  平均等待时间: {stats['average_wait_time_seconds']:.4f}秒")
    print(f"  公平性指数: {stats['fairness_index']:.4f}")
    print(f"  总丢弃: {stats['total_dropped']}")
    
    method_counts = {}
    for method, ts in processed_timestamps:
        method_counts[method] = method_counts.get(method, 0) + 1
    
    print(f"  各方法处理次数: {method_counts}")
    
    short_task_count = sum(1 for m, _ in processed_timestamps if m.startswith('Short'))
    long_task_count = sum(1 for m, _ in processed_timestamps if m == long_task_method)
    
    max_wait_time = stats['max_wait_time_seconds']
    passed = max_wait_time < 2.0 and short_task_count > 0
    
    print(f"  短任务处理: {short_task_count}, 长任务处理: {long_task_count}")
    
    queue.stop()
    
    return {
        'test': 'mixed_tasks_wait_time',
        'total_processed': len(processed_timestamps),
        'short_tasks_processed': short_task_count,
        'long_tasks_processed': long_task_count,
        'max_wait_time_seconds': max_wait_time,
        'average_wait_time_seconds': stats['average_wait_time_seconds'],
        'total_dropped': stats['total_dropped'],
        'fairness_index': stats['fairness_index'],
        'passed': passed,
    }


def test_3_back_pressure_drop_strategy() -> Dict[str, Any]:
    """
    测试3：背压触发时丢弃策略符合预期
    验证：队列满时，按照优先级丢弃事件（低优先级先被丢弃）
    """
    small_capacity = 10
    queue = BackPressureEventQueue(capacity=small_capacity, drop_strategy='oldest_low_priority_first')
    
    low_priority_events = [
        'Network.requestWillBeSent',
        'Network.responseReceived',
        'Network.dataReceived',
    ]
    
    normal_priority_events = [
        'DOM.attributeModified',
        'DOM.childNodeInserted',
        'Page.frameNavigated',
    ]
    
    high_priority_events = [
        'Page.javascriptDialogOpening',
        'Target.attachedToTarget',
    ]
    
    for i in range(50):
        method = low_priority_events[i % len(low_priority_events)]
        event = {'type': 'low', 'seq': i, 'method': method}
        queue.put(event, method)
        
        method = normal_priority_events[i % len(normal_priority_events)]
        event = {'type': 'normal', 'seq': i, 'method': method}
        queue.put(event, method)
        
        if i % 5 == 0:
            method = high_priority_events[i % len(high_priority_events)]
            event = {'type': 'high', 'seq': i, 'method': method}
            queue.put(event, method)
    
    stats = queue.get_statistics()
    
    print(f"  队列容量: {small_capacity}")
    print(f"  总入队: {stats['total_enqueued']}")
    print(f"  总丢弃: {stats['total_dropped']}")
    print(f"  按优先级丢弃: {stats['dropped_by_priority']}")
    print(f"  按方法丢弃: {stats['dropped_by_method']}")
    
    dropped_low = stats['dropped_by_priority'].get(EventPriority.LOW, 0)
    dropped_normal = stats['dropped_by_priority'].get(EventPriority.NORMAL, 0)
    dropped_high = stats['dropped_by_priority'].get(EventPriority.HIGH, 0)
    dropped_critical = stats['dropped_by_priority'].get(EventPriority.CRITICAL, 0)
    
    print(f"  低优先级(LOW={EventPriority.LOW})丢弃: {dropped_low}")
    print(f"  普通优先级(NORMAL={EventPriority.NORMAL})丢弃: {dropped_normal}")
    print(f"  高优先级(HIGH={EventPriority.HIGH})丢弃: {dropped_high}")
    print(f"  关键优先级(CRITICAL={EventPriority.CRITICAL})丢弃: {dropped_critical}")
    
    print(f"  丢弃策略说明: oldest_low_priority_first (低优先级最老事件先丢弃)")
    print(f"  触发条件: 队列满 (qsize() >= capacity)")
    
    passed = (
        stats['total_dropped'] > 0 and
        dropped_low >= dropped_normal and
        dropped_normal >= dropped_high and
        dropped_high >= dropped_critical
    )
    
    queue.stop()
    
    return {
        'test': 'back_pressure_drop_strategy',
        'queue_capacity': small_capacity,
        'total_enqueued': stats['total_enqueued'],
        'total_dropped': stats['total_dropped'],
        'dropped_by_priority': dict(stats['dropped_by_priority']),
        'dropped_low': dropped_low,
        'dropped_normal': dropped_normal,
        'dropped_high': dropped_high,
        'dropped_critical': dropped_critical,
        'drop_strategy': 'oldest_low_priority_first',
        'trigger_condition': 'queue full (qsize() >= capacity)',
        'passed': passed,
    }


def test_4_consistent_results() -> Dict[str, Any]:
    """
    测试4：多轮运行结果一致（无状态漂移）
    验证：相同的输入在多次运行中产生一致的输出模式
    """
    def run_single_round(round_num: int) -> Dict[str, Any]:
        queue = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
        
        methods = ['Test.A', 'Test.B', 'Test.C']
        
        for i in range(50):
            for method in methods:
                event = {'round': round_num, 'seq': i, 'method': method}
                queue.put(event, method)
        
        processed = []
        while not queue.empty():
            result = queue.get(timeout=0.1)
            if result:
                event, method = result
                processed.append(method)
        
        stats = queue.get_statistics()
        queue.stop()
        
        return {
            'processed_count': len(processed),
            'method_counts': {m: processed.count(m) for m in methods},
            'fairness_index': stats['fairness_index'],
        }
    
    num_rounds = 5
    results = []
    
    for i in range(num_rounds):
        result = run_single_round(i)
        results.append(result)
        print(f"  轮次 {i+1}: 处理 {result['processed_count']} 个事件, 公平性 {result['fairness_index']:.4f}")
    
    all_processed_counts = [r['processed_count'] for r in results]
    all_fairness = [r['fairness_index'] for r in results]
    
    consistent_processed = len(set(all_processed_counts)) == 1
    fairness_std = (sum((x - sum(all_fairness)/len(all_fairness))**2 for x in all_fairness) / len(all_fairness)) ** 0.5
    consistent_fairness = fairness_std < 0.01
    
    passed = consistent_processed and consistent_fairness
    
    print(f"  处理数一致性: {'一致' if consistent_processed else '不一致'}")
    print(f"  公平性标准差: {fairness_std:.6f}")
    
    return {
        'test': 'consistent_results',
        'num_rounds': num_rounds,
        'processed_counts': all_processed_counts,
        'fairness_indices': all_fairness,
        'fairness_std_dev': fairness_std,
        'consistent_processed': consistent_processed,
        'consistent_fairness': consistent_fairness,
        'passed': passed,
    }


def test_5_compatibility_normal_events() -> Dict[str, Any]:
    """
    测试5：兼容性回归 - 普通事件处理路径
    验证：原事件处理语义未破坏
    """
    print("  验证普通事件入队和出队...")
    
    queue = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
    
    test_events = [
        ({'method': 'Test.event1', 'params': {'a': 1}}, 'Test.event1'),
        ({'method': 'Test.event2', 'params': {'b': 2}}, 'Test.event2'),
        ({'method': 'Test.event3', 'params': {'c': 3}}, 'Test.event3'),
    ]
    
    for event, method in test_events:
        queue.put(event, method)
    
    print(f"  入队事件数: {len(test_events)}")
    print(f"  队列大小: {queue.qsize()}")
    
    received_events = []
    while not queue.empty():
        result = queue.get(timeout=0.1)
        if result:
            received_events.append(result)
    
    print(f"  出队事件数: {len(received_events)}")
    
    passed = len(received_events) == len(test_events)
    
    if passed:
        for i, (expected, received) in enumerate(zip(test_events, received_events)):
            expected_event, expected_method = expected
            received_event, received_method = received
            assert expected_method == received_method, f"方法不匹配: {expected_method} vs {received_method}"
            assert expected_event == received_event, f"事件不匹配: {expected_event} vs {received_event}"
        print("  ✓ 所有事件正确处理")
    else:
        print("  ✗ 事件数不匹配")
    
    queue.stop()
    
    return {
        'test': 'compatibility_normal_events',
        'expected_count': len(test_events),
        'received_count': len(received_events),
        'passed': passed,
    }


def test_6_compatibility_immediate_events() -> Dict[str, Any]:
    """
    测试6：兼容性回归 - 即时事件处理路径
    验证：即时事件使用独立队列和丢弃策略
    """
    print("  验证即时事件独立队列...")
    
    normal_queue = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
    immediate_queue = BackPressureEventQueue(capacity=50, drop_strategy='oldest_first')
    
    print(f"  普通队列容量: {normal_queue.capacity}, 丢弃策略: oldest_low_priority_first")
    print(f"  即时队列容量: {immediate_queue.capacity}, 丢弃策略: oldest_first")
    
    for i in range(10):
        normal_queue.put({'type': 'normal', 'seq': i}, f'Normal.event_{i}')
        immediate_queue.put({'type': 'immediate', 'seq': i}, f'Immediate.event_{i}')
    
    print(f"  普通队列大小: {normal_queue.qsize()}")
    print(f"  即时队列大小: {immediate_queue.qsize()}")
    
    normal_received = 0
    while not normal_queue.empty():
        result = normal_queue.get(timeout=0.1)
        if result:
            normal_received += 1
    
    immediate_received = 0
    while not immediate_queue.empty():
        result = immediate_queue.get(timeout=0.1)
        if result:
            immediate_received += 1
    
    print(f"  普通事件处理数: {normal_received}")
    print(f"  即时事件处理数: {immediate_received}")
    
    passed = normal_received == 10 and immediate_received == 10
    
    normal_queue.stop()
    immediate_queue.stop()
    
    return {
        'test': 'compatibility_immediate_events',
        'normal_queue_capacity': normal_queue.capacity,
        'immediate_queue_capacity': immediate_queue.capacity,
        'normal_received': normal_received,
        'immediate_received': immediate_received,
        'passed': passed,
    }


def main():
    print("\n" + "="*60)
    print("事件队列背压与公平调度验收测试")
    print("="*60)
    print(f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python版本: {sys.version}")
    
    runner = TestRunner()
    
    runner.run_test(test_1_high_concurrency_throughput, "高并发突发写入吞吐稳定")
    runner.run_test(test_2_mixed_tasks_wait_time, "长短任务混合最大等待时延可控")
    runner.run_test(test_3_back_pressure_drop_strategy, "背压触发丢弃策略符合预期")
    runner.run_test(test_4_consistent_results, "多轮运行结果一致（无状态漂移）")
    runner.run_test(test_5_compatibility_normal_events, "兼容性回归：普通事件处理路径")
    runner.run_test(test_6_compatibility_immediate_events, "兼容性回归：即时事件处理路径")
    
    exit_code = runner.print_summary()
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
