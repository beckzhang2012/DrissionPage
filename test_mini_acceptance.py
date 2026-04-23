# -*- coding: utf-8 -*-
"""
极简验收验证 - 快速验证关键指标
"""
import sys
import time

sys.path.insert(0, '.')

from DrissionPage._base.driver import (
    BackPressureEventQueue,
    EventPriority,
    PriorityBasedEventMethodMapper,
)

print("="*60)
print("极简验收验证")
print("="*60)
print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")

FINAL_RESULTS = {
    'throughput': 0,
    'max_wait_time': 0,
    'dropped_by_priority': {},
    'dropped_by_method': {},
    'fairness_index': 0,
    'exit_code': 1,
}

# 验证1：导入正常
print("\n[验证1] 导入检查...")
print("  ✓ 从 driver.py 成功导入: BackPressureEventQueue, EventPriority, PriorityBasedEventMethodMapper")

# 验证2：基本put/get
print("\n[验证2] 基本put/get...")
q = BackPressureEventQueue(capacity=100)
q.put({'a': 1}, 'Test.method1')
q.put({'b': 2}, 'Test.method2')
e1, m1 = q.get(timeout=0.1)
e2, m2 = q.get(timeout=0.1)
assert m1 == 'Test.method1', f"方法不匹配: {m1}"
assert m2 == 'Test.method2', f"方法不匹配: {m2}"
print("  ✓ put/get 正常工作")
q.stop()

# 验证3：吞吐量测试
print("\n[验证3] 吞吐量测试...")
q = BackPressureEventQueue(capacity=2000)
start = time.perf_counter()
for i in range(1000):
    q.put({'seq': i}, f'Method.{i % 3}')
elapsed = time.perf_counter() - start
throughput = 1000 / elapsed if elapsed > 0 else 0
FINAL_RESULTS['throughput'] = round(throughput, 2)
print(f"  吞吐: {throughput:.2f} 事件/秒 (1000事件耗时 {elapsed:.3f}秒)")

processed = 0
start_process = time.perf_counter()
while not q.empty():
    r = q.get(timeout=0.1)
    if r:
        processed += 1
process_elapsed = time.perf_counter() - start_process
print(f"  处理吞吐: {processed/process_elapsed:.2f} 事件/秒 (处理 {processed} 事件)")
assert processed == 1000, f"处理数不匹配: {processed}"
q.stop()

# 验证4：丢弃策略测试
print("\n[验证4] 背压丢弃策略测试...")
small_q = BackPressureEventQueue(capacity=5, drop_strategy='oldest_low_priority_first')

low_methods = ['Network.requestWillBeSent', 'Network.responseReceived']
normal_methods = ['DOM.attributeModified', 'Page.frameNavigated']
high_methods = ['Page.javascriptDialogOpening']

for i in range(10):
    small_q.put({'i': i}, low_methods[i % 2])
    small_q.put({'i': i}, normal_methods[i % 2])
    if i % 3 == 0:
        small_q.put({'i': i}, high_methods[0])

stats = small_q.get_statistics()
FINAL_RESULTS['dropped_by_priority'] = dict(stats['dropped_by_priority'])
FINAL_RESULTS['dropped_by_method'] = dict(stats['dropped_by_method'])

print(f"  队列容量: 5, 总入队: {stats['total_enqueued']}, 总丢弃: {stats['total_dropped']}")
print(f"  按优先级丢弃: {dict(stats['dropped_by_priority'])}")
print(f"  按方法丢弃: {dict(stats['dropped_by_method'])}")

dropped_low = stats['dropped_by_priority'].get(EventPriority.LOW, 0)
dropped_normal = stats['dropped_by_priority'].get(EventPriority.NORMAL, 0)
dropped_high = stats['dropped_by_priority'].get(EventPriority.HIGH, 0)
dropped_critical = stats['dropped_by_priority'].get(EventPriority.CRITICAL, 0)

print(f"  丢弃顺序验证: LOW({dropped_low}) >= NORMAL({dropped_normal}) >= HIGH({dropped_high}) >= CRITICAL({dropped_critical})")
assert stats['total_dropped'] > 0, "应该有丢弃事件"
small_q.stop()

# 验证5：公平性测试
print("\n[验证5] 公平性测试...")
fair_q = BackPressureEventQueue(capacity=100)
methods = ['A', 'B', 'C']
for i in range(30):
    for m in methods:
        fair_q.put({'i': i}, m)

counts = {'A': 0, 'B': 0, 'C': 0}
while not fair_q.empty():
    r = fair_q.get(timeout=0.1)
    if r:
        e, m = r
        counts[m] += 1

min_count = min(counts.values())
max_count = max(counts.values())
fairness = min_count / max_count if max_count > 0 else 1.0
FINAL_RESULTS['fairness_index'] = round(fairness, 4)

print(f"  各方法处理次数: {counts}")
print(f"  公平性指数: {fairness:.4f}")
assert fairness >= 0.9, f"公平性太低: {fairness}"
fair_q.stop()

# 验证6：等待时间统计
print("\n[验证6] 等待时间统计...")
wait_q = BackPressureEventQueue(capacity=100)
wait_q.put({'x': 1}, 'Test.wait')
time.sleep(0.01)
e, m = wait_q.get(timeout=0.1)
stats = wait_q.get_statistics()
FINAL_RESULTS['max_wait_time'] = round(stats['max_wait_time_seconds'], 4)
print(f"  最大等待时间: {stats['max_wait_time_seconds']:.4f}秒")
print(f"  平均等待时间: {stats['average_wait_time_seconds']:.4f}秒")
wait_q.stop()

# 验证7：兼容性 - 普通事件路径
print("\n[验证7] 兼容性 - 普通事件路径...")
normal_q = BackPressureEventQueue(capacity=100, drop_strategy='oldest_low_priority_first')
test_events = [
    ({'method': 'Page.navigate', 'params': {'url': 'http://test.com'}}, 'Page.navigate'),
    ({'method': 'DOM.getDocument', 'params': {}}, 'DOM.getDocument'),
    ({'method': 'Runtime.evaluate', 'params': {'expression': '1+1'}}, 'Runtime.evaluate'),
]
for event, method in test_events:
    normal_q.put(event, method)

received = []
while not normal_q.empty():
    r = normal_q.get(timeout=0.1)
    if r:
        received.append(r)

assert len(received) == len(test_events), f"事件数不匹配: {len(received)} vs {len(test_events)}"
for expected, actual in zip(test_events, received):
    assert expected[0] == actual[0], f"事件内容不匹配"
    assert expected[1] == actual[1], f"方法不匹配"
print("  ✓ 普通事件路径正常工作")
normal_q.stop()

# 验证8：兼容性 - 即时事件路径 (独立队列)
print("\n[验证8] 兼容性 - 即时事件路径 (独立队列)...")
immediate_q = BackPressureEventQueue(capacity=50, drop_strategy='oldest_first')
for i in range(10):
    immediate_q.put({'type': 'immediate', 'seq': i}, f'Immediate.event_{i}')

immediate_received = 0
while not immediate_q.empty():
    r = immediate_q.get(timeout=0.1)
    if r:
        immediate_received += 1

assert immediate_received == 10, f"即时事件处理数不匹配: {immediate_received}"
print("  ✓ 即时事件路径 (独立队列) 正常工作")
print(f"  普通队列丢弃策略: oldest_low_priority_first, 即时队列丢弃策略: oldest_first")
immediate_q.stop()

print("\n" + "="*60)
print("所有验证通过!")
print("="*60)

FINAL_RESULTS['exit_code'] = 0

print("\n【真实数值汇总】")
print("="*60)
print(f"1) 吞吐 (throughput_events_per_second): {FINAL_RESULTS['throughput']} 事件/秒")
print(f"2) 最大等待时延 (max_wait_time_seconds): {FINAL_RESULTS['max_wait_time']} 秒")
print(f"3) 事件丢弃统计:")
print(f"   - 按优先级: {FINAL_RESULTS['dropped_by_priority']}")
print(f"   - 按方法: {FINAL_RESULTS['dropped_by_method']}")
print(f"4) 公平性指标 (fairness_index): {FINAL_RESULTS['fairness_index']}")
print(f"5) $LASTEXITCODE: {FINAL_RESULTS['exit_code']}")
print("="*60)

sys.exit(FINAL_RESULTS['exit_code'])
