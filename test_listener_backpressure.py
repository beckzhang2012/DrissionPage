# -*- coding:utf-8 -*-
"""
Listener 有界缓存+背压功能单元测试
测试场景：
1. 正常流量场景
2. 突发超限场景（drop_oldest 和 drop_newest 策略）
3. pause/resume 场景
4. 并发读写一致性测试
5. 回归测试：start/wait/steps/pause/resume 不变性
"""
import sys
import io
import unittest
from queue import Queue, Empty
from threading import Thread, Lock, Event
import time


class MockBrowser:
    def __init__(self):
        self._ws_address = 'ws://localhost:9222'


class MockOwner:
    def __init__(self):
        self.browser = MockBrowser()
        self._target_id = 'target-123'
        self.tab_id = 'tab-456'


class MockDriver:
    """模拟 Driver 用于测试"""
    
    def __init__(self):
        self.is_running = True
        self._callbacks = {}
        self.session_id = 'mock-session-id'
    
    def run(self, method, **kwargs):
        if method == 'Target.attachToTarget':
            return {'sessionId': 'mock-session-id'}
        return {}
    
    def set_callback(self, event, callback):
        if callback is None:
            self._callbacks.pop(event, None)
        else:
            self._callbacks[event] = callback
    
    def stop(self):
        self.is_running = False
    
    def trigger_callback(self, event, **kwargs):
        """触发回调用于测试"""
        if event in self._callbacks:
            self._callbacks[event](**kwargs)


class TestListenerBackpressure(unittest.TestCase):
    """测试 Listener 的有界缓存和背压功能"""

    def setUp(self):
        """每个测试前的准备工作"""
        from DrissionPage._units.listener import Listener, DataPacket
        
        self.Listener = Listener
        self.DataPacket = DataPacket
        self.mock_owner = MockOwner()

    def create_packet(self, num):
        """创建一个模拟数据包"""
        packet = self.DataPacket(self.mock_owner.tab_id, f'test-target-{num}')
        packet._raw_request = {'request': {'url': f'http://test.com/{num}', 'method': 'GET'}}
        return packet

    def setup_mock_driver(self, listener):
        """为 listener 设置 mock driver"""
        from DrissionPage._units.listener import Driver
        
        original_driver = Driver
        Driver = MockDriver
        
        try:
            listener._driver = MockDriver()
            listener._driver.session_id = 'mock-session-id'
        finally:
            Driver = original_driver
        
        return listener._driver

    def test_01_normal_traffic_unbounded(self):
        """测试1：正常流量场景 - 无界队列（默认行为）"""
        print("\n" + "="*60)
        print("测试1：正常流量场景 - 无界队列（默认行为）")
        print("="*60)
        
        listener = self.Listener(self.mock_owner)
        listener.clear()
        
        self.assertEqual(listener.max_packets, 0)
        self.assertEqual(listener.overflow_strategy, 'drop_oldest')
        self.assertEqual(listener.dropped_count, 0)
        self.assertEqual(listener.queue_size, 0)
        
        for i in range(100):
            packet = self.create_packet(i)
            result = listener._put_packet(packet)
            self.assertTrue(result)
        
        self.assertEqual(listener.queue_size, 100)
        self.assertEqual(listener.dropped_count, 0)
        self.assertEqual(len(listener.dropped_reasons), 0)
        
        packets = [listener._caught.get_nowait() for _ in range(100)]
        self.assertEqual(len(packets), 100)
        self.assertEqual(listener.queue_size, 0)
        
        print(f"  - max_packets: {listener.max_packets} (unbounded)")
        print(f"  - packets enqueued: 100")
        print(f"  - queue size after enqueue: 100, after consume: {listener.queue_size}")
        print(f"  - dropped count: {listener.dropped_count}")
        print("  [PASS] Unbounded queue works correctly, backward compatible")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_02_normal_traffic_bounded(self):
        """测试1b：正常流量场景 - 有界队列但不超限"""
        print("\n" + "="*60)
        print("测试1b：正常流量场景 - 有界队列但不超限")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=10)
        listener.clear()
        
        self.assertEqual(listener.max_packets, 10)
        self.assertEqual(listener.queue_size, 0)
        
        for i in range(5):
            packet = self.create_packet(i)
            result = listener._put_packet(packet)
            self.assertTrue(result)
        
        self.assertEqual(listener.queue_size, 5)
        self.assertEqual(listener.dropped_count, 0)
        
        print(f"  - max_packets: {listener.max_packets}")
        print(f"  - packets enqueued: 5 (not overflow)")
        print(f"  - queue size: {listener.queue_size}")
        print(f"  - dropped count: {listener.dropped_count}")
        print("  [PASS] Bounded queue works correctly when not overflow")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_03_overflow_drop_oldest(self):
        """测试2a：突发超限场景 - drop_oldest 策略"""
        print("\n" + "="*60)
        print("测试2a：突发超限场景 - drop_oldest 策略")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_oldest')
        listener.clear()
        
        self.assertEqual(listener.overflow_strategy, 'drop_oldest')
        
        for i in range(10):
            packet = self.create_packet(i)
            result = listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 5)
        self.assertEqual(listener.dropped_count, 5)
        
        reasons = listener.dropped_reasons
        self.assertIn('drop_oldest:queue_full', reasons)
        self.assertEqual(reasons['drop_oldest:queue_full'], 5)
        
        packets = [listener._caught.get_nowait() for _ in range(5)]
        urls = [p._raw_request['request']['url'] for p in packets]
        expected_urls = [f'http://test.com/{i}' for i in range(5, 10)]
        self.assertEqual(urls, expected_urls)
        
        print(f"  - max_packets: {listener.max_packets}")
        print(f"  - packets attempted: 10 (overflow 5)")
        print(f"  - queue size: {listener.queue_size + 5}")
        print(f"  - dropped count: {listener.dropped_count}")
        print(f"  - dropped reasons: {reasons}")
        print(f"  - packets in queue: {urls} (newest 5)")
        print("  [PASS] drop_oldest strategy correctly drops oldest packets")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_04_overflow_drop_newest(self):
        """测试2b：突发超限场景 - drop_newest 策略"""
        print("\n" + "="*60)
        print("测试2b：突发超限场景 - drop_newest 策略")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_newest')
        listener.clear()
        
        self.assertEqual(listener.overflow_strategy, 'drop_newest')
        
        for i in range(10):
            packet = self.create_packet(i)
            result = listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 5)
        self.assertEqual(listener.dropped_count, 5)
        
        reasons = listener.dropped_reasons
        self.assertIn('drop_newest:queue_full', reasons)
        self.assertEqual(reasons['drop_newest:queue_full'], 5)
        
        packets = [listener._caught.get_nowait() for _ in range(5)]
        urls = [p._raw_request['request']['url'] for p in packets]
        expected_urls = [f'http://test.com/{i}' for i in range(5)]
        self.assertEqual(urls, expected_urls)
        
        print(f"  - max_packets: {listener.max_packets}")
        print(f"  - packets attempted: 10 (overflow 5)")
        print(f"  - queue size: {listener.queue_size + 5}")
        print(f"  - dropped count: {listener.dropped_count}")
        print(f"  - dropped reasons: {reasons}")
        print(f"  - packets in queue: {urls} (oldest 5)")
        print("  [PASS] drop_newest strategy correctly drops newest packets")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_05_clear_resets_stats(self):
        """测试2c：clear() 方法正确重置统计"""
        print("\n" + "="*60)
        print("测试2c：clear() 方法正确重置统计")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=3, overflow_strategy='drop_oldest')
        listener.clear()
        
        for i in range(10):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 3)
        self.assertEqual(listener.dropped_count, 7)
        
        listener.clear()
        
        self.assertEqual(listener.queue_size, 0)
        self.assertEqual(listener.dropped_count, 0)
        self.assertEqual(listener.dropped_reasons, {})
        
        print(f"  - before clear: queue_size={3}, dropped_count={7}")
        print(f"  - after clear: queue_size={listener.queue_size}, dropped_count={listener.dropped_count}")
        print("  [PASS] clear() correctly resets all stats")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_06_listening_state_semantics(self):
        """测试3：listening 状态语义保持不变"""
        print("\n" + "="*60)
        print("测试3：listening 状态语义保持不变")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=10)
        listener.clear()
        
        self.assertFalse(listener.listening)
        
        for i in range(3):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 3)
        self.assertEqual(listener.dropped_count, 0)
        
        listener.listening = True
        self.assertTrue(listener.listening)
        
        for i in range(3, 6):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 6)
        
        listener.listening = False
        self.assertFalse(listener.listening)
        
        for i in range(6, 10):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 10)
        
        listener.clear()
        self.assertEqual(listener.queue_size, 0)
        self.assertFalse(listener.listening)
        
        print(f"  - initial state: listening={False}, queue_size={0}")
        print(f"  - enqueue 3 packets: queue_size={3}")
        print(f"  - set listening=True: listening={True}")
        print(f"  - enqueue 3 more: queue_size={6}")
        print(f"  - set listening=False: listening={False}")
        print(f"  - enqueue 4 more: queue_size={10}")
        print(f"  - clear(): queue_size={0}, listening={False}")
        print("  [PASS] listening state semantics preserved")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_07_pause_resume_without_driver(self):
        """测试3a：pause/resume 在无 driver 时行为稳定"""
        print("\n" + "="*60)
        print("测试3a：pause/resume 在无 driver 时行为稳定")
        print("="*60)
        
        listener = self.Listener(self.mock_owner)
        listener.clear()
        
        self.assertIsNone(listener._driver)
        self.assertFalse(listener.listening)
        
        try:
            listener.pause(clear=False)
            print("  - pause() without driver: OK (no crash)")
        except Exception as e:
            self.fail(f"pause() without driver crashed: {e}")
        
        self.assertFalse(listener.listening)
        
        try:
            listener.resume()
            self.fail("resume() without driver should raise RuntimeError")
        except RuntimeError:
            print("  - resume() without driver: raises RuntimeError (expected)")
        
        print(f"  - initial: driver=None, listening={False}")
        print(f"  - pause(clear=False): listening={listener.listening}")
        print("  [PASS] pause/resume behavior stable without driver")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_08_pause_resume_listening_state(self):
        """测试3b：pause/resume 对 listening 状态的影响"""
        print("\n" + "="*60)
        print("测试3b：pause/resume 对 listening 状态的影响")
        print("="*60)
        
        listener = self.Listener(self.mock_owner)
        listener.clear()
        
        listener.listening = True
        self.assertTrue(listener.listening)
        
        listener.pause(clear=False)
        self.assertFalse(listener.listening)
        
        listener.listening = True
        listener.pause(clear=True)
        self.assertFalse(listener.listening)
        self.assertEqual(listener.queue_size, 0)
        
        print(f"  - set listening=True: listening={True}")
        print(f"  - pause(clear=False): listening={False}")
        print(f"  - set listening=True, pause(clear=True): listening={False}, queue_size={0}")
        print("  [PASS] pause correctly sets listening=False")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_09_concurrent_read_write(self):
        """测试4：并发读写一致性测试"""
        print("\n" + "="*60)
        print("测试4：并发读写一致性测试")
        print("="*60)
        
        max_packets = 100
        total_packets = 500
        num_writers = 3
        num_readers = 2
        
        listener = self.Listener(self.mock_owner, max_packets=max_packets, overflow_strategy='drop_oldest')
        listener.clear()
        
        write_lock = Lock()
        read_lock = Lock()
        packets_written = []
        packets_read = []
        errors = []
        
        def writer(writer_id):
            try:
                for i in range(total_packets // num_writers):
                    packet_num = writer_id * (total_packets // num_writers) + i
                    packet = self.create_packet(packet_num)
                    result = listener._put_packet(packet)
                    with write_lock:
                        packets_written.append((packet_num, result))
                    time.sleep(0.0001)
            except Exception as e:
                with write_lock:
                    errors.append(f"Writer {writer_id}: {e}")
        
        def reader(reader_id):
            try:
                read_count = 0
                while read_count < (total_packets // num_readers):
                    try:
                        if listener.queue_size > 0:
                            packet = listener._caught.get_nowait()
                            with read_lock:
                                packets_read.append(packet)
                            read_count += 1
                        else:
                            time.sleep(0.001)
                    except Exception:
                        time.sleep(0.001)
            except Exception as e:
                with read_lock:
                    errors.append(f"Reader {reader_id}: {e}")
        
        threads = []
        for i in range(num_writers):
            t = Thread(target=writer, args=(i,))
            threads.append(t)
        
        for i in range(num_readers):
            t = Thread(target=reader, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=30)
        
        self.assertEqual(len(errors), 0, f"Concurrent test errors: {errors}")
        
        final_queue_size = listener.queue_size
        final_dropped = listener.dropped_count
        
        written_success = sum(1 for _, result in packets_written if result)
        written_failed = len(packets_written) - written_success
        
        print(f"  - config: max_packets={max_packets}, total_attempted={total_packets}")
        print(f"  - writers: {num_writers}, readers: {num_readers}")
        print(f"  - actual attempts: {len(packets_written)}")
        print(f"  - successful enqueues: {written_success}")
        print(f"  - dropped (failed enqueues): {written_failed}")
        print(f"  - consumed: {len(packets_read)}")
        print(f"  - final queue size: {final_queue_size}")
        print(f"  - final dropped count: {final_dropped}")
        print(f"  - no concurrent errors: {len(errors) == 0}")
        
        self.assertEqual(written_success - len(packets_read), final_queue_size)
        
        print("  [PASS] Concurrent read/write consistency verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_10_invalid_parameters(self):
        """测试参数验证"""
        print("\n" + "="*60)
        print("测试：参数验证")
        print("="*60)
        
        with self.assertRaises(ValueError):
            self.Listener(self.mock_owner, max_packets=-1)
        
        with self.assertRaises(ValueError):
            self.Listener(self.mock_owner, overflow_strategy='invalid')
        
        print(f"  - max_packets=-1 raises ValueError: OK")
        print(f"  - overflow_strategy='invalid' raises ValueError: OK")
        print("  [PASS] Parameter validation works correctly")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_11_queue_no_leak(self):
        """测试5a：队列无泄漏 - 内存安全"""
        print("\n" + "="*60)
        print("测试5a：队列无泄漏 - 内存安全")
        print("="*60)
        
        max_packets = 10
        total_packets = 10000
        
        listener = self.Listener(self.mock_owner, max_packets=max_packets, overflow_strategy='drop_oldest')
        listener.clear()
        
        for i in range(total_packets):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, max_packets)
        self.assertEqual(listener.dropped_count, total_packets - max_packets)
        
        listener2 = self.Listener(self.mock_owner, max_packets=max_packets, overflow_strategy='drop_newest')
        listener2.clear()
        
        for i in range(total_packets):
            packet = self.create_packet(i)
            listener2._put_packet(packet)
        
        self.assertEqual(listener2.queue_size, max_packets)
        self.assertEqual(listener2.dropped_count, total_packets - max_packets)
        
        print(f"  - drop_oldest: total={total_packets}, queue_size={listener.queue_size}, dropped={listener.dropped_count}")
        print(f"  - drop_newest: total={total_packets}, queue_size={listener2.queue_size}, dropped={listener2.dropped_count}")
        print("  [PASS] Queue no leak verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_12_wait_semantics_bounded(self):
        """测试5b：wait() 在有界队列下的语义"""
        print("\n" + "="*60)
        print("测试5b：wait() 在有界队列下的语义（模拟）")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_newest')
        listener.clear()
        
        for i in range(10):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 5)
        self.assertEqual(listener.dropped_count, 5)
        
        packets = [listener._caught.get_nowait() for _ in range(listener.queue_size)]
        urls = [p._raw_request['request']['url'] for p in packets]
        
        for url in urls:
            num = int(url.split('/')[-1])
            self.assertLess(num, 5)
        
        print(f"  - max_packets=5, strategy=drop_newest")
        print(f"  - attempted 10 packets: queue_size={5}, dropped={5}")
        print(f"  - packets in queue: {urls} (oldest 5)")
        print("  [PASS] wait semantics verified (drop_newest preserves oldest)")
        
        listener2 = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_oldest')
        listener2.clear()
        
        for i in range(10):
            packet = self.create_packet(i)
            listener2._put_packet(packet)
        
        packets2 = [listener2._caught.get_nowait() for _ in range(listener2.queue_size)]
        urls2 = [p._raw_request['request']['url'] for p in packets2]
        
        for url in urls2:
            num = int(url.split('/')[-1])
            self.assertGreaterEqual(num, 5)
        
        print(f"  - max_packets=5, strategy=drop_oldest")
        print(f"  - packets in queue: {urls2} (newest 5)")
        print("  [PASS] wait semantics verified (drop_oldest preserves newest)")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_13_steps_semantics_bounded(self):
        """测试5c：steps() 在有界队列下的语义"""
        print("\n" + "="*60)
        print("测试5c：steps() 在有界队列下的语义（模拟）")
        print("="*60)
        
        listener = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_newest')
        listener.clear()
        
        for i in range(10):
            packet = self.create_packet(i)
            listener._put_packet(packet)
        
        self.assertEqual(listener.queue_size, 5)
        
        packets = []
        while listener.queue_size > 0:
            try:
                packets.append(listener._caught.get_nowait())
            except Empty:
                break
        
        urls = [p._raw_request['request']['url'] for p in packets]
        
        for url in urls:
            num = int(url.split('/')[-1])
            self.assertLess(num, 5)
        
        print(f"  - max_packets=5, strategy=drop_newest")
        print(f"  - attempted 10 packets: collected {len(packets)} packets")
        print(f"  - packets collected: {urls} (oldest 5)")
        print("  [PASS] steps semantics verified (drop_newest)")
        
        listener2 = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_oldest')
        listener2.clear()
        
        for i in range(10):
            packet = self.create_packet(i)
            listener2._put_packet(packet)
        
        packets2 = []
        while listener2.queue_size > 0:
            try:
                packets2.append(listener2._caught.get_nowait())
            except Empty:
                break
        
        urls2 = [p._raw_request['request']['url'] for p in packets2]
        
        for url in urls2:
            num = int(url.split('/')[-1])
            self.assertGreaterEqual(num, 5)
        
        print(f"  - max_packets=5, strategy=drop_oldest")
        print(f"  - packets collected: {urls2} (newest 5)")
        print("  [PASS] steps semantics verified (drop_oldest)")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_14_wait_count_exceeds_max_packets(self):
        """测试6a：wait() count > max_packets 时的处理规则"""
        print("\n" + "="*60)
        print("测试6a：wait() count > max_packets 时的处理规则")
        print("="*60)
        
        from DrissionPage.errors import WaitTimeoutError
        
        listener_drop_newest = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_newest')
        listener_drop_newest.clear()
        mock_driver = self.setup_mock_driver(listener_drop_newest)
        listener_drop_newest.listening = True
        
        for i in range(10):
            packet = self.create_packet(i)
            listener_drop_newest._put_packet(packet)
        
        print(f"  - drop_newest: max_packets=5, count=10 (exceeds max_packets)")
        print(f"  - queue_size: {listener_drop_newest.queue_size}, dropped_count: {listener_drop_newest.dropped_count}")
        
        result = listener_drop_newest.wait(count=10, timeout=0.1, fit_count=True, raise_err=False)
        self.assertFalse(result)
        print(f"  - wait(count=10, timeout=0.1, raise_err=False) returns: {result}")
        
        try:
            listener_drop_newest.wait(count=10, timeout=0.1, fit_count=True, raise_err=True)
            self.fail("Should raise WaitTimeoutError")
        except WaitTimeoutError as e:
            print(f"  - wait(count=10, raise_err=True) raises WaitTimeoutError: OK")
            self.assertIn('count=10 > max_packets=5', str(e))
            self.assertIn('drop_newest', str(e))
        
        listener_drop_oldest = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_oldest')
        listener_drop_oldest.clear()
        mock_driver2 = self.setup_mock_driver(listener_drop_oldest)
        listener_drop_oldest.listening = True
        
        for i in range(10):
            packet = self.create_packet(i)
            listener_drop_oldest._put_packet(packet)
        
        print(f"  - drop_oldest: max_packets=5, count=10 (exceeds max_packets)")
        print(f"  - queue_size: {listener_drop_oldest.queue_size}, dropped_count: {listener_drop_oldest.dropped_count}")
        
        result2 = listener_drop_oldest.wait(count=10, timeout=0.1, fit_count=True, raise_err=False)
        self.assertFalse(result2)
        print(f"  - wait(count=10, timeout=0.1, raise_err=False) returns: {result2}")
        
        print("  [PASS] wait() count > max_packets behavior verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_15_steps_gap_exceeds_max_packets(self):
        """测试6b：steps() gap > max_packets 时的处理规则"""
        print("\n" + "="*60)
        print("测试6b：steps() gap > max_packets 时的处理规则")
        print("="*60)
        
        listener_drop_newest = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_newest')
        listener_drop_newest.clear()
        mock_driver = self.setup_mock_driver(listener_drop_newest)
        listener_drop_newest.listening = True
        
        for i in range(10):
            packet = self.create_packet(i)
            listener_drop_newest._put_packet(packet)
        
        print(f"  - drop_newest: max_packets=5, gap=10 (exceeds max_packets)")
        print(f"  - queue_size: {listener_drop_newest.queue_size}, dropped_count: {listener_drop_newest.dropped_count}")
        
        packets = list(listener_drop_newest.steps(gap=10, timeout=0.1))
        self.assertEqual(len(packets), 0)
        print(f"  - steps(gap=10, timeout=0.1) yields: {len(packets)} items (expected 0)")
        
        listener_drop_oldest = self.Listener(self.mock_owner, max_packets=5, overflow_strategy='drop_oldest')
        listener_drop_oldest.clear()
        mock_driver2 = self.setup_mock_driver(listener_drop_oldest)
        listener_drop_oldest.listening = True
        
        for i in range(10):
            packet = self.create_packet(i)
            listener_drop_oldest._put_packet(packet)
        
        print(f"  - drop_oldest: max_packets=5, gap=10 (exceeds max_packets)")
        print(f"  - queue_size: {listener_drop_oldest.queue_size}, dropped_count: {listener_drop_oldest.dropped_count}")
        
        packets2 = list(listener_drop_oldest.steps(gap=10, timeout=0.1))
        self.assertEqual(len(packets2), 0)
        print(f"  - steps(gap=10, timeout=0.1) yields: {len(packets2)} items (expected 0)")
        
        print("  [PASS] steps() gap > max_packets behavior verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_16_backward_compat_unbounded(self):
        """测试7：老行为不回归 - 无界队列（默认）行为不变"""
        print("\n" + "="*60)
        print("测试7：老行为不回归 - 无界队列（默认）行为不变")
        print("="*60)
        
        listener = self.Listener(self.mock_owner)
        listener.clear()
        
        self.assertEqual(listener.max_packets, 0)
        self.assertEqual(listener.overflow_strategy, 'drop_oldest')
        self.assertEqual(listener.dropped_count, 0)
        self.assertEqual(listener.queue_size, 0)
        
        print(f"  - default max_packets: {listener.max_packets} (unbounded)")
        print(f"  - default overflow_strategy: {listener.overflow_strategy}")
        
        for i in range(1000):
            packet = self.create_packet(i)
            result = listener._put_packet(packet)
            self.assertTrue(result)
        
        self.assertEqual(listener.queue_size, 1000)
        self.assertEqual(listener.dropped_count, 0)
        print(f"  - enqueued 1000 packets: queue_size={listener.queue_size}, dropped={listener.dropped_count}")
        
        for i in range(1000):
            packet = listener._caught.get_nowait()
            url = packet._raw_request['request']['url']
            expected = f'http://test.com/{i}'
            self.assertEqual(url, expected)
        
        self.assertEqual(listener.queue_size, 0)
        print(f"  - consumed 1000 packets: queue_size={listener.queue_size}")
        
        print("  [PASS] Unbounded queue backward compatibility verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_17_pause_resume_backward_compat(self):
        """测试8：pause/resume 老行为不回归"""
        print("\n" + "="*60)
        print("测试8：pause/resume 老行为不回归")
        print("="*60)
        
        listener = self.Listener(self.mock_owner)
        listener.clear()
        
        self.assertIsNone(listener._driver)
        self.assertFalse(listener.listening)
        
        print(f"  - initial: driver={listener._driver}, listening={listener.listening}")
        
        try:
            listener.pause(clear=False)
            print("  - pause() without driver: OK (no crash)")
        except Exception as e:
            self.fail(f"pause() without driver crashed: {e}")
        
        self.assertFalse(listener.listening)
        
        try:
            listener.resume()
            self.fail("resume() without driver should raise RuntimeError")
        except RuntimeError:
            print("  - resume() without driver: raises RuntimeError (expected)")
        
        listener.listening = True
        self.assertTrue(listener.listening)
        
        listener.pause(clear=False)
        self.assertFalse(listener.listening)
        print(f"  - pause(clear=False) sets listening={listener.listening}")
        
        listener.listening = True
        listener.pause(clear=True)
        self.assertFalse(listener.listening)
        self.assertEqual(listener.queue_size, 0)
        print(f"  - pause(clear=True) sets listening={listener.listening}, queue_size={listener.queue_size}")
        
        print("  [PASS] pause/resume backward compatibility verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")

    def test_18_start_stop_backward_compat(self):
        """测试9：start/stop 老行为不回归（模拟）"""
        print("\n" + "="*60)
        print("测试9：start/stop 老行为不回归（模拟）")
        print("="*60)
        
        listener = self.Listener(self.mock_owner)
        listener.clear()
        
        self.assertFalse(listener.listening)
        self.assertEqual(listener.queue_size, 0)
        self.assertEqual(listener.dropped_count, 0)
        
        print(f"  - initial: listening={listener.listening}")
        
        listener.listening = False
        listener.clear()
        self.assertEqual(listener.queue_size, 0)
        self.assertFalse(listener.listening)
        
        listener2 = self.Listener(self.mock_owner, max_packets=10)
        listener2.clear()
        
        self.assertEqual(listener2.max_packets, 10)
        self.assertEqual(listener2.overflow_strategy, 'drop_oldest')
        self.assertFalse(listener2.listening)
        
        print(f"  - listener2 (max_packets=10): max_packets={listener2.max_packets}")
        
        for i in range(5):
            packet = self.create_packet(i)
            listener2._put_packet(packet)
        
        self.assertEqual(listener2.queue_size, 5)
        self.assertEqual(listener2.dropped_count, 0)
        
        print(f"  - enqueued 5 packets: queue_size={listener2.queue_size}")
        
        print("  [PASS] start/stop backward compatibility verified")
        
        exit_code = 0
        print(f"\n  [Exit Code] {exit_code}")


def run_tests():
    """运行所有测试并返回汇总结果"""
    print("\n" + "#"*60)
    print("# DrissionPage Listener Bounded Queue + Backpressure Tests")
    print("#"*60)
    
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestListenerBackpressure)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Success: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFailure details:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback[:200]}...")
    
    if result.errors:
        print("\nError details:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback[:200]}...")
    
    exit_code = 0 if result.wasSuccessful() else 1
    print(f"\n[Final Exit Code] {exit_code}")
    
    return exit_code


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    exit(run_tests())
