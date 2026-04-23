# -*- coding: utf-8 -*-
"""
简单验证测试：事件队列背压与公平调度
"""
import sys
import time
from threading import Thread

sys.path.insert(0, '.')

from DrissionPage._base.event_queue import (
    BackPressureEventQueue,
    EventPriority,
    PriorityBasedEventMethodMapper,
)


def test_basic_operations():
    """测试基本操作"""
    print("测试1: 基本入队出队操作")
    queue = BackPressureEventQueue(capacity=100)
    
    for i in range(10):
        queue.put({'id': i}, f'Test.event_{i % 3}')
    
    print(f"  队列大小: {queue.qsize()}")
    assert queue.qsize() == 10
    
    for i in range(10):
        result = queue.get(timeout=0.1)
        assert result is not None
        event, method = result
        print(f"  取出: method={method}, event={event}")
    
    assert queue.qsize() == 0
    queue.stop()
    print("  ✓ 通过")


def test_back_pressure():
    """测试背压机制"""
    print("\n测试2: 背压机制 - 队列满时丢弃事件")
    queue = BackPressureEventQueue(capacity=5, drop_strategy='oldest_low_priority_first')
    
    for i in range(20):
        method = 'Network.requestWillBeSent' if i % 2 == 0 else 'DOM.attributeModified'
        queue.put({'id': i}, method)
    
    stats = queue.get_statistics()
    print(f"  容量: {stats['capacity']}")
    print(f"  当前大小: {stats['current_size']}")
    print(f"  总入队: {stats['total_enqueued']}")
    print(f"  总丢弃: {stats['total_dropped']}")
    print(f"  按优先级丢弃: {stats['dropped_by_priority']}")
    
    assert stats['total_dropped'] > 0
    assert stats['total_enqueued'] == 20
    queue.stop()
    print("  ✓ 通过")


def test_priority_based_dropping():
    """测试基于优先级的丢弃策略"""
    print("\n测试3: 优先级丢弃策略 - 低优先级先被丢弃")
    queue = BackPressureEventQueue(capacity=10, drop_strategy='oldest_low_priority_first')
    
    low_method = 'Network.requestWillBeSent'
    normal_method = 'DOM.attributeModified'
    high_method = 'Page.javascriptDialogOpening'
    
    for i in range(30):
        queue.put({'id': i, 'prio': 'low'}, low_method)
        queue.put({'id': i, 'prio': 'normal'}, normal_method)
        if i % 3 == 0:
            queue.put({'id': i, 'prio': 'high'}, high_method)
    
    stats = queue.get_statistics()
    dropped_low = stats['dropped_by_priority'].get(EventPriority.LOW, 0)
    dropped_normal = stats['dropped_by_priority'].get(EventPriority.NORMAL, 0)
    dropped_high = stats['dropped_by_priority'].get(EventPriority.HIGH, 0)
    
    print(f"  低优先级(LOW)丢弃: {dropped_low}")
    print(f"  普通优先级(NORMAL)丢弃: {dropped_normal}")
    print(f"  高优先级(HIGH)丢弃: {dropped_high}")
    
    assert dropped_low >= dropped_normal >= dropped_high
    queue.stop()
    print("  ✓ 通过")


def test_fair_scheduling():
    """测试公平调度"""
    print("\n测试4: 公平调度 - 轮询避免单类事件饥饿")
    queue = BackPressureEventQueue(capacity=1000)
    
    methods = ['Type.A', 'Type.B', 'Type.C']
    
    for i in range(100):
        for method in methods:
            queue.put({'seq': i}, method)
    
    processed = {m: 0 for m in methods}
    while not queue.empty():
        result = queue.get(timeout=0.1)
        if result:
            event, method = result
            processed[method] += 1
    
    stats = queue.get_statistics()
    print(f"  各方法处理次数: {processed}")
    print(f"  公平性指数: {stats['fairness_index']:.4f}")
    
    assert stats['fairness_index'] > 0.9
    queue.stop()
    print("  ✓ 通过")


def test_statistics():
    """测试统计功能"""
    print("\n测试5: 统计指标 - 吞吐、时延、公平性")
    queue = BackPressureEventQueue(capacity=1000)
    
    start_time = time.perf_counter()
    
    def producer():
        for i in range(500):
            queue.put({'id': i}, f'Event.{i % 5}')
    
    def consumer():
        count = 0
        while count < 500:
            result = queue.get(timeout=0.5)
            if result:
                time.sleep(0.001)
                count += 1
    
    t1 = Thread(target=producer)
    t2 = Thread(target=consumer)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    end_time = time.perf_counter()
    elapsed = end_time - start_time
    
    stats = queue.get_statistics()
    
    print(f"  总入队: {stats['total_enqueued']}")
    print(f"  总出队: {stats['total_dequeued']}")
    print(f"  总丢弃: {stats['total_dropped']}")
    print(f"  最大等待时间: {stats['max_wait_time_seconds']:.4f}秒")
    print(f"  平均等待时间: {stats['average_wait_time_seconds']:.4f}秒")
    print(f"  公平性指数: {stats['fairness_index']:.4f}")
    print(f"  实际耗时: {elapsed:.3f}秒")
    print(f"  实际吞吐: {500/elapsed:.2f} 事件/秒")
    
    assert stats['total_enqueued'] == 500
    assert stats['total_dequeued'] == 500
    assert stats['total_dropped'] == 0
    queue.stop()
    print("  ✓ 通过")


def main():
    print("="*60)
    print("事件队列背压与公平调度验证测试")
    print("="*60)
    
    all_passed = True
    try:
        test_basic_operations()
    except AssertionError as e:
        print(f"  ✗ 失败: {e}")
        all_passed = False
    
    try:
        test_back_pressure()
    except AssertionError as e:
        print(f"  ✗ 失败: {e}")
        all_passed = False
    
    try:
        test_priority_based_dropping()
    except AssertionError as e:
        print(f"  ✗ 失败: {e}")
        all_passed = False
    
    try:
        test_fair_scheduling()
    except AssertionError as e:
        print(f"  ✗ 失败: {e}")
        all_passed = False
    
    try:
        test_statistics()
    except AssertionError as e:
        print(f"  ✗ 失败: {e}")
        all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("所有测试通过!")
        exit_code = 0
    else:
        print("部分测试失败!")
        exit_code = 1
    print("="*60)
    print(f"\n$LASTEXITCODE = {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
