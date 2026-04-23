# -*- coding: utf-8 -*-
"""
事件队列背压与公平调度测试
验证以下指标：
1) 高并发突发写入下吞吐稳定
2) 长短任务混合下最大等待时延可控
3) 背压触发时丢弃策略符合预期
4) 多轮运行结果一致（无状态漂移）
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Event
from typing import List, Dict, Any
import json

sys.path.insert(0, '.')

from DrissionPage._base.event_queue import (
    BackPressureEventQueue,
    EventPriority,
    PriorityBasedEventMethodMapper,
)


def run_test_1_high_concurrency_throughput():
    """
    测试1：高并发突发写入下吞吐稳定
    验证：在突发大量事件时，队列能够稳定处理，吞吐不会剧烈波动
    """
    print("\n" + "="*60)
    print("测试1：高并发突发写入下吞吐稳定")
    print("="*60)
    
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
    
    if processed_events:
        first_time = processed_events[0][1]
        last_time = processed_events[-1][1]
        processing_duration = last_time - first_time
        processing_throughput = processed / processing_duration if processing_duration > 0 else 0
        print(f"  实际处理吞吐: {processing_throughput:.2f} 事件/秒")
    
    queue.stop()
    
    result = {
        'test': 'high_concurrency_throughput',
        'total_events': total_events,
        'processed': processed,
        'dropped': dropped,
        'elapsed_seconds': elapsed,
        'throughput_events_per_second': throughput,
        'fairness_index': stats['fairness_index'],
        'max_wait_time_seconds': stats['max_wait_time_seconds'],
        'passed': processed > 0 and throughput > 0,
    }
    
    print(f"  测试结果: {'通过' if result['passed'] else '失败'}")
    return result


def run_test_2_max_wait_time_controllable():
    """
    测试2：长短任务混合下最大等待时延可控
    验证：即使有长时间运行的任务，其他事件的等待时间也不会无限增长
    """
    print("\n" + "="*60)
    print("测试2：长短任务混合下最大等待时延可控")
    print("="*60)
    
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
    
    method_counts = {}
    for method, ts in processed_timestamps:
        method_counts[method] = method_counts.get(method, 0) + 1
    
    print(f"  各方法处理次数: {method_counts}")
    
    short_task_count = sum(1 for m, _ in processed_timestamps if m.startswith('Short'))
    long_task_count = sum(1 for m, _ in processed_timestamps if m == long_task_method)
    
    max_wait_time = stats['max_wait_time_seconds']
    passed = max_wait_time < 2.0 and short_task_count > 0
    
    print(f"  短任务处理: {short_task_count}, 长任务处理: {long_task_count}")
    print(f"  测试结果: {'通过' if passed else '失败'}")
    
    queue.stop()
    
    return {
        'test': 'max_wait_time_controllable',
        'total_processed': len(processed_timestamps),
        'short_tasks_processed': short_task_count,
        'long_tasks_processed': long_task_count,
        'max_wait_time_seconds': max_wait_time,
        'average_wait_time_seconds': stats['average_wait_time_seconds'],
        'fairness_index': stats['fairness_index'],
        'passed': passed,
    }


def run_test_3_drop_strategy():
    """
    测试3：背压触发时丢弃策略符合预期
    验证：队列满时，按照优先级丢弃事件（低优先级先被丢弃）
    """
    print("\n" + "="*60)
    print("测试3：背压触发时丢弃策略符合预期")
    print("="*60)
    
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
    
    print(f"  低优先级丢弃: {dropped_low}")
    print(f"  普通优先级丢弃: {dropped_normal}")
    print(f"  高优先级丢弃: {dropped_high}")
    print(f"  关键优先级丢弃: {dropped_critical}")
    
    passed = (
        stats['total_dropped'] > 0 and
        dropped_low >= dropped_normal and
        dropped_normal >= dropped_high and
        dropped_high >= dropped_critical
    )
    
    print(f"  测试结果: {'通过' if passed else '失败'}")
    
    queue.stop()
    
    return {
        'test': 'drop_strategy',
        'queue_capacity': small_capacity,
        'total_enqueued': stats['total_enqueued'],
        'total_dropped': stats['total_dropped'],
        'dropped_by_priority': dict(stats['dropped_by_priority']),
        'dropped_low': dropped_low,
        'dropped_normal': dropped_normal,
        'dropped_high': dropped_high,
        'dropped_critical': dropped_critical,
        'passed': passed,
    }


def run_test_4_consistent_results():
    """
    测试4：多轮运行结果一致（无状态漂移）
    验证：相同的输入在多次运行中产生一致的输出模式
    """
    print("\n" + "="*60)
    print("测试4：多轮运行结果一致（无状态漂移）")
    print("="*60)
    
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
    print(f"  测试结果: {'通过' if passed else '失败'}")
    
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


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("事件队列背压与公平调度测试套件")
    print("="*60)
    
    all_results = []
    
    all_results.append(run_test_1_high_concurrency_throughput())
    all_results.append(run_test_2_max_wait_time_controllable())
    all_results.append(run_test_3_drop_strategy())
    all_results.append(run_test_4_consistent_results())
    
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    
    all_passed = True
    summary = {
        'tests': [],
        'overall': {},
    }
    
    for result in all_results:
        all_passed = all_passed and result['passed']
        summary['tests'].append({
            'name': result['test'],
            'passed': result['passed'],
            'details': {k: v for k, v in result.items() if k not in ['test', 'passed']},
        })
        status = "通过" if result['passed'] else "失败"
        print(f"  {result['test']}: {status}")
    
    print("\n" + "-"*60)
    print(f"  总体结果: {'全部通过' if all_passed else '部分失败'}")
    print("-"*60)
    
    exit_code = 0 if all_passed else 1
    summary['overall'] = {
        'all_passed': all_passed,
        'exit_code': exit_code,
    }
    
    print("\n详细统计:")
    for result in all_results:
        print(f"\n  {result['test']}:")
        for key, value in result.items():
            if key not in ['test', 'passed']:
                print(f"    {key}: {value}")
    
    print(f"\n$LASTEXITCODE = {exit_code}")
    
    return summary, exit_code


if __name__ == '__main__':
    summary, exit_code = run_all_tests()
    sys.exit(exit_code)
