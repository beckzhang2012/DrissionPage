# -*- coding: utf-8 -*-
"""
快速验收测试 - 输出真实数值：
1) 吞吐 (throughput_events_per_second)
2) 最大等待时延 (max_wait_time_seconds)
3) 事件丢弃统计（按优先级/方法）
4) 公平性指标 (fairness_index)
5) $LASTEXITCODE
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Event

sys.path.insert(0, '.')

from DrissionPage._base.driver import (
    BackPressureEventQueue,
    EventPriority,
    PriorityBasedEventMethodMapper,
)

ALL_PASSED = True
FINAL_STATS = {}


def test_throughput():
    """测试1：高并发吞吐"""
    global ALL_PASSED
    queue = BackPressureEventQueue(capacity=1000, drop_strategy='oldest_low_priority_first')
    stop_event = Event()
    processed_events = []
    
    def consumer():
        while not stop_event.is_set() or not queue.empty():
            try:
                result = queue.get(timeout=0.1)
                if result:
                    processed_events.append(time.perf_counter())
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
            queue.put({'pid': pid, 'seq': i, 'method': method}, method)
    
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
    throughput = processed / elapsed if elapsed > 0 else 0
    
    FINAL_STATS['throughput'] = {
        'throughput_events_per_second': round(throughput, 2),
        'total_events': total_events,
        'processed': processed,
        'elapsed_seconds': round(elapsed, 3),
    }
    
    print(f"\n[吞吐测试]")
    print(f"  吞吐率: {throughput:.2f} 事件/秒")
    print(f"  总事件: {total_events}, 已处理: {processed}, 耗时: {elapsed:.3f}秒")
    print(f"  公平性指数: {stats['fairness_index']:.4f}")
    
    passed = processed > 0 and throughput > 0
    if not passed:
        ALL_PASSED = False
    
    queue.stop()
    return passed


def test_wait_time():
    """测试2：最大等待时延"""
    global ALL_PASSED
    queue = BackPressureEventQueue(capacity=500, drop_strategy='oldest_low_priority_first')
    
    short_task_methods = ['Short.task1', 'Short.task2', 'Short.task3']
    long_task_method = 'Long.task'
    processed_timestamps = []
    
    def consumer():
        while len(processed_timestamps) < 200:
            result = queue.get(timeout=0.5)
            if result:
                event, method = result
                if method == long_task_method:
                    time.sleep(0.05)
                else:
                    time.sleep(0.001)
                processed_timestamps.append(time.perf_counter())
    
    consumer_thread = Thread(target=consumer, daemon=True)
    consumer_thread.start()
    
    for i in range(100):
        for method in short_task_methods:
            queue.put({'type': 'short', 'seq': i, 'method': method}, method)
        if i % 5 == 0:
            queue.put({'type': 'long', 'seq': i, 'method': long_task_method}, long_task_method)
    
    consumer_thread.join(timeout=10)
    
    stats = queue.get_statistics()
    
    FINAL_STATS['wait_time'] = {
        'max_wait_time_seconds': round(stats['max_wait_time_seconds'], 4),
        'average_wait_time_seconds': round(stats['average_wait_time_seconds'], 4),
        'total_processed': len(processed_timestamps),
        'fairness_index': round(stats['fairness_index'], 4),
    }
    
    print(f"\n[等待时延测试]")
    print(f"  最大等待时间: {stats['max_wait_time_seconds']:.4f}秒")
    print(f"  平均等待时间: {stats['average_wait_time_seconds']:.4f}秒")
    print(f"  公平性指数: {stats['fairness_index']:.4f}")
    print(f"  总处理: {len(processed_timestamps)} 个事件")
    
    passed = stats['max_wait_time_seconds'] < 2.0 and len(processed_timestamps) > 0
    if not passed:
        ALL_PASSED = False
    
    queue.stop()
    return passed


def test_drop_strategy():
    """测试3：背压丢弃策略"""
    global ALL_PASSED
    small_capacity = 10
    queue = BackPressureEventQueue(capacity=small_capacity, drop_strategy='oldest_low_priority_first')
    
    low_priority_events = ['Network.requestWillBeSent', 'Network.responseReceived', 'Network.dataReceived']
    normal_priority_events = ['DOM.attributeModified', 'DOM.childNodeInserted', 'Page.frameNavigated']
    high_priority_events = ['Page.javascriptDialogOpening', 'Target.attachedToTarget']
    
    for i in range(50):
        method = low_priority_events[i % len(low_priority_events)]
        queue.put({'type': 'low', 'seq': i, 'method': method}, method)
        
        method = normal_priority_events[i % len(normal_priority_events)]
        queue.put({'type': 'normal', 'seq': i, 'method': method}, method)
        
        if i % 5 == 0:
            method = high_priority_events[i % len(high_priority_events)]
            queue.put({'type': 'high', 'seq': i, 'method': method}, method)
    
    stats = queue.get_statistics()
    
    dropped_low = stats['dropped_by_priority'].get(EventPriority.LOW, 0)
    dropped_normal = stats['dropped_by_priority'].get(EventPriority.NORMAL, 0)
    dropped_high = stats['dropped_by_priority'].get(EventPriority.HIGH, 0)
    dropped_critical = stats['dropped_by_priority'].get(EventPriority.CRITICAL, 0)
    
    FINAL_STATS['drop_strategy'] = {
        'total_dropped': stats['total_dropped'],
        'dropped_by_priority': {
            'LOW': dropped_low,
            'NORMAL': dropped_normal,
            'HIGH': dropped_high,
            'CRITICAL': dropped_critical,
        },
        'dropped_by_method': dict(stats['dropped_by_method']),
        'queue_capacity': small_capacity,
        'total_enqueued': stats['total_enqueued'],
    }
    
    print(f"\n[丢弃策略测试]")
    print(f"  队列容量: {small_capacity}")
    print(f"  总入队: {stats['total_enqueued']}, 总丢弃: {stats['total_dropped']}")
    print(f"  按优先级丢弃: LOW={dropped_low}, NORMAL={dropped_normal}, HIGH={dropped_high}, CRITICAL={dropped_critical}")
    print(f"  按方法丢弃: {dict(stats['dropped_by_method'])}")
    
    passed = (
        stats['total_dropped'] > 0 and
        dropped_low >= dropped_normal and
        dropped_normal >= dropped_high and
        dropped_high >= dropped_critical
    )
    if not passed:
        ALL_PASSED = False
    
    queue.stop()
    return passed


def test_fairness():
    """测试4：公平性指标"""
    global ALL_PASSED
    queue = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
    methods = ['Test.A', 'Test.B', 'Test.C']
    
    for i in range(50):
        for method in methods:
            queue.put({'seq': i, 'method': method}, method)
    
    processed = []
    while not queue.empty():
        result = queue.get(timeout=0.1)
        if result:
            event, method = result
            processed.append(method)
    
    stats = queue.get_statistics()
    method_counts = {m: processed.count(m) for m in methods}
    min_count = min(method_counts.values())
    max_count = max(method_counts.values())
    fairness = min_count / max_count if max_count > 0 else 1.0
    
    FINAL_STATS['fairness'] = {
        'fairness_index': round(fairness, 4),
        'method_counts': method_counts,
        'stats_fairness_index': round(stats['fairness_index'], 4),
    }
    
    print(f"\n[公平性测试]")
    print(f"  各方法处理次数: {method_counts}")
    print(f"  公平性指数: {fairness:.4f}")
    print(f"  统计公平性指数: {stats['fairness_index']:.4f}")
    
    passed = fairness >= 0.8
    if not passed:
        ALL_PASSED = False
    
    queue.stop()
    return passed


def test_compatibility_normal():
    """测试5：兼容性回归 - 普通事件路径"""
    global ALL_PASSED
    queue = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
    
    test_events = [
        ({'method': 'Test.event1', 'params': {'a': 1}}, 'Test.event1'),
        ({'method': 'Test.event2', 'params': {'b': 2}}, 'Test.event2'),
        ({'method': 'Test.event3', 'params': {'c': 3}}, 'Test.event3'),
    ]
    
    for event, method in test_events:
        queue.put(event, method)
    
    received_events = []
    while not queue.empty():
        result = queue.get(timeout=0.1)
        if result:
            received_events.append(result)
    
    print(f"\n[兼容性测试 - 普通事件路径]")
    print(f"  入队事件数: {len(test_events)}, 出队事件数: {len(received_events)}")
    
    passed = len(received_events) == len(test_events)
    if passed:
        for expected, received in zip(test_events, received_events):
            assert expected[0] == received[0], f"事件内容不匹配"
            assert expected[1] == received[1], f"方法不匹配"
        print("  ✓ 所有事件正确处理")
    else:
        print("  ✗ 事件数不匹配")
        ALL_PASSED = False
    
    queue.stop()
    return passed


def test_compatibility_immediate():
    """测试6：兼容性回归 - 即时事件路径"""
    global ALL_PASSED
    normal_queue = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
    immediate_queue = BackPressureEventQueue(capacity=50, drop_strategy='oldest_first')
    
    for i in range(10):
        normal_queue.put({'type': 'normal', 'seq': i}, f'Normal.event_{i}')
        immediate_queue.put({'type': 'immediate', 'seq': i}, f'Immediate.event_{i}')
    
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
    
    print(f"\n[兼容性测试 - 即时事件路径]")
    print(f"  普通队列容量: {normal_queue.capacity}, 丢弃策略: oldest_low_priority_first")
    print(f"  即时队列容量: {immediate_queue.capacity}, 丢弃策略: oldest_first")
    print(f"  普通事件处理: {normal_received}, 即时事件处理: {immediate_received}")
    
    passed = normal_received == 10 and immediate_received == 10
    if not passed:
        ALL_PASSED = False
    
    normal_queue.stop()
    immediate_queue.stop()
    return passed


def main():
    print("="*70)
    print("快速验收测试 - 输出真实数值")
    print("="*70)
    print(f"日期: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")
    
    test_throughput()
    test_wait_time()
    test_drop_strategy()
    test_fairness()
    test_compatibility_normal()
    test_compatibility_immediate()
    
    exit_code = 0 if ALL_PASSED else 1
    
    print("\n" + "="*70)
    print("【真实数值汇总】")
    print("="*70)
    
    print(f"\n1) 吞吐 (throughput_events_per_second):")
    print(f"   数值: {FINAL_STATS.get('throughput', {}).get('throughput_events_per_second', 0)} 事件/秒")
    print(f"   详情: 总事件={FINAL_STATS.get('throughput', {}).get('total_events', 0)}, "
          f"已处理={FINAL_STATS.get('throughput', {}).get('processed', 0)}, "
          f"耗时={FINAL_STATS.get('throughput', {}).get('elapsed_seconds', 0)}秒")
    
    print(f"\n2) 最大等待时延 (max_wait_time_seconds):")
    print(f"   数值: {FINAL_STATS.get('wait_time', {}).get('max_wait_time_seconds', 0)} 秒")
    print(f"   详情: 平均等待={FINAL_STATS.get('wait_time', {}).get('average_wait_time_seconds', 0)}秒, "
          f"公平性指数={FINAL_STATS.get('wait_time', {}).get('fairness_index', 0)}")
    
    print(f"\n3) 事件丢弃统计 (按优先级/方法):")
    drop_stats = FINAL_STATS.get('drop_strategy', {})
    print(f"   总丢弃: {drop_stats.get('total_dropped', 0)}")
    print(f"   按优先级丢弃: {drop_stats.get('dropped_by_priority', {})}")
    print(f"   按方法丢弃: {drop_stats.get('dropped_by_method', {})}")
    print(f"   详情: 队列容量={drop_stats.get('queue_capacity', 0)}, 总入队={drop_stats.get('total_enqueued', 0)}")
    
    print(f"\n4) 公平性指标 (fairness_index):")
    fairness_stats = FINAL_STATS.get('fairness', {})
    print(f"   数值: {fairness_stats.get('fairness_index', 0)}")
    print(f"   详情: 各方法处理次数={fairness_stats.get('method_counts', {})}")
    
    print(f"\n5) $LASTEXITCODE:")
    print(f"   数值: {exit_code}")
    
    print("\n" + "="*70)
    print(f"总体结果: {'全部通过' if ALL_PASSED else '部分失败'}")
    print("="*70)
    
    return exit_code


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
