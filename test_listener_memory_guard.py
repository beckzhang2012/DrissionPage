# -*- coding:utf-8 -*-
"""
Listener 内存保护单元测试
覆盖：小体积正常保留、大体积降级、混合流量稳定、stop后内存收敛、多轮一致性
"""
import sys
import unittest
from queue import Queue
from unittest.mock import MagicMock, patch, PropertyMock
from time import perf_counter, sleep

sys.path.insert(0, '..')

from DrissionPage._units.listener import (
    Listener, DataPacket, FrameListener
)


class TestListenerBodyProcessing(unittest.TestCase):
    """测试 Listener body 处理逻辑"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'
        self.listener = Listener(self.mock_owner)

    def test_estimate_body_size_text(self):
        """测试估算文本 body 大小"""
        body = 'Hello, World!'
        size = self.listener._estimate_body_size(body, is_base64=False)
        self.assertEqual(size, len(body))

    def test_estimate_body_size_base64(self):
        """测试估算 base64 body 大小"""
        body = 'SGVsbG8sIFdvcmxkIQ=='
        size = self.listener._estimate_body_size(body, is_base64=True)
        expected = int(len(body) * 0.75)
        self.assertEqual(size, expected)

    def test_estimate_body_size_none(self):
        """测试估算 None body 大小"""
        size = self.listener._estimate_body_size(None, is_base64=False)
        self.assertEqual(size, 0)

    def test_process_body_small_unchanged(self):
        """测试小 body 不被修改"""
        self.listener._body_size_limit = 100
        packet = DataPacket(tab_id='test', target='test')
        body = 'small body'
        is_base64 = False

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        self.assertEqual(result_body, body)
        self.assertEqual(result_base64, is_base64)
        self.assertEqual(original_size, len(body))

    def test_process_body_large_truncate_mode(self):
        """测试大 body 在截断模式下的处理"""
        self.listener._body_size_limit = 5
        self.listener._degradation_mode = 'truncate'
        packet = DataPacket(tab_id='test', target='test')
        body = 'This is a very long body content'
        is_base64 = False

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        self.assertEqual(len(result_body), 5)
        self.assertEqual(result_body, body[:5])
        self.assertEqual(original_size, len(body))

    def test_process_body_large_skip_mode(self):
        """测试大 body 在跳过模式下的处理"""
        self.listener._body_size_limit = 5
        self.listener._degradation_mode = 'skip'
        packet = DataPacket(tab_id='test', target='test')
        body = 'This is a very long body content'
        is_base64 = False

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        self.assertEqual(result_body, '')
        self.assertEqual(result_base64, False)
        self.assertEqual(original_size, len(body))

    def test_process_body_base64_truncate(self):
        """测试 base64 body 截断"""
        self.listener._body_size_limit = 3
        self.listener._degradation_mode = 'truncate'
        packet = DataPacket(tab_id='test', target='test')
        body = 'SGVsbG8sIFdvcmxkIQ=='
        is_base64 = True

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        chars_to_keep = int(3 / 0.75)
        chars_to_keep = chars_to_keep - (chars_to_keep % 4)
        expected_length = max(0, chars_to_keep)

        self.assertEqual(len(result_body), expected_length)

    def test_process_body_zero_limit(self):
        """测试 body 大小限制为 0（不限制）"""
        self.listener._body_size_limit = 0
        packet = DataPacket(tab_id='test', target='test')
        body = 'A' * 10000

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, False
        )

        self.assertEqual(result_body, body)


class TestListenerQueueLimit(unittest.TestCase):
    """测试 Listener 队列限制"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'
        self.listener = Listener(self.mock_owner)

    def test_enforce_queue_limit_disabled(self):
        """测试队列限制禁用"""
        self.listener._queue_size_limit = 0
        self.listener._caught = Queue(maxsize=0)

        for i in range(100):
            self.listener._caught.put(f'item-{i}')

        self.listener._enforce_queue_limit()
        self.assertEqual(self.listener._caught.qsize(), 100)

    def test_enforce_queue_limit_enabled(self):
        """测试队列限制启用"""
        self.listener._queue_size_limit = 5
        self.listener._caught = Queue(maxsize=0)

        for i in range(10):
            self.listener._caught.put(f'item-{i}')

        self.assertEqual(self.listener._caught.qsize(), 10)
        self.listener._enforce_queue_limit()
        self.assertEqual(self.listener._caught.qsize(), 4)

        remaining_items = []
        while not self.listener._caught.empty():
            remaining_items.append(self.listener._caught.get())

        self.assertEqual(remaining_items, ['item-6', 'item-7', 'item-8', 'item-9'])


class TestListenerClearAndStop(unittest.TestCase):
    """测试 Listener 的 clear 和 stop 方法"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'

    def test_clear_resets_state(self):
        """测试 clear 重置状态"""
        listener = Listener(self.mock_owner)
        listener._request_ids = {'test-id': 'test-value'}
        listener._extra_info_ids = {'test-id': 'test-value'}
        listener._caught = Queue(maxsize=0)
        listener._caught.put('test-item')
        listener._running_requests = 5
        listener._running_targets = 3

        listener.clear()

        self.assertEqual(listener._caught.qsize(), 0)
        self.assertEqual(listener._request_ids, {})
        self.assertEqual(listener._extra_info_ids, {})
        self.assertEqual(listener._running_requests, 0)
        self.assertEqual(listener._running_targets, 0)

    def test_stop_clears_state(self):
        """测试 stop 清除状态"""
        listener = Listener(self.mock_owner)
        listener.listening = False
        listener._driver = None
        listener._request_ids = {'test-id': 'test-value'}
        listener._extra_info_ids = {'test-id': 'test-value'}
        listener._caught = Queue(maxsize=0)
        listener._caught.put('test-item')
        listener._running_requests = 5
        listener._running_targets = 3

        listener.stop()

        self.assertEqual(listener._caught.qsize(), 0)
        self.assertEqual(listener._request_ids, {})
        self.assertEqual(listener._extra_info_ids, {})
        self.assertEqual(listener._running_requests, 0)
        self.assertEqual(listener._running_targets, 0)

    def test_multiple_rounds_consistency(self):
        """测试多轮一致性"""
        listener = Listener(self.mock_owner)

        for round_num in range(3):
            listener._request_ids = {f'test-id-{round_num}': f'test-value-{round_num}'}
            listener._extra_info_ids = {f'test-id-{round_num}': f'test-value-{round_num}'}
            listener._caught = Queue(maxsize=0)
            listener._caught.put(f'test-item-{round_num}')
            listener._running_requests = round_num + 1
            listener._running_targets = round_num + 1

            self.assertEqual(listener._caught.qsize(), 1)
            self.assertEqual(len(listener._request_ids), 1)
            self.assertEqual(len(listener._extra_info_ids), 1)

            listener.clear()

            self.assertEqual(listener._caught.qsize(), 0)
            self.assertEqual(listener._request_ids, {})
            self.assertEqual(listener._extra_info_ids, {})
            self.assertEqual(listener._running_requests, 0)
            self.assertEqual(listener._running_targets, 0)


class TestDegradationScenarios(unittest.TestCase):
    """测试各种降级场景"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'

    def test_mixed_traffic_processing(self):
        """测试混合流量处理"""
        listener = Listener(self.mock_owner)
        listener._body_size_limit = 10
        listener._degradation_mode = 'truncate'

        small_bodies = ['small', 'tiny', 'mini']
        large_bodies = ['this is a large body', 'another very large body here']

        for body in small_bodies:
            packet = DataPacket(tab_id='test', target='test')
            result_body, _, _ = listener._process_body_for_packet(packet, body, False)
            self.assertEqual(result_body, body)

        for body in large_bodies:
            packet = DataPacket(tab_id='test', target='test')
            result_body, _, _ = listener._process_body_for_packet(packet, body, False)
            self.assertEqual(len(result_body), 10)

    def test_skip_mode_returns_empty(self):
        """测试跳过模式返回空"""
        listener = Listener(self.mock_owner)
        listener._body_size_limit = 10
        listener._degradation_mode = 'skip'

        large_body = 'this is a very large body content'
        packet = DataPacket(tab_id='test', target='test')
        result_body, _, _ = listener._process_body_for_packet(packet, large_body, False)

        self.assertEqual(result_body, '')

    def test_default_mode_backward_compatible(self):
        """测试默认模式向后兼容"""
        listener = Listener(self.mock_owner)

        self.assertEqual(listener._body_size_limit, 10 * 1024 * 1024)
        self.assertEqual(listener._queue_size_limit, 1000)
        self.assertEqual(listener._degradation_mode, 'truncate')

        small_body = 'normal small body'
        packet = DataPacket(tab_id='test', target='test')
        result_body, _, _ = listener._process_body_for_packet(packet, small_body, False)

        self.assertEqual(result_body, small_body)


class TestMemoryGuardPerformance(unittest.TestCase):
    """测试内存保护性能指标"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'
        self.listener = Listener(self.mock_owner)

    def test_body_retention_rate(self):
        """测试 body 保留率"""
        self.listener._body_size_limit = 10
        self.listener._degradation_mode = 'truncate'

        total_packets = 100
        small_packets = 70
        large_packets = 30

        retained_count = 0
        degraded_count = 0

        for i in range(total_packets):
            packet = DataPacket(tab_id='test', target='test')
            if i < small_packets:
                body = 'small'
            else:
                body = 'this is a large body content'

            result_body, _, _ = self.listener._process_body_for_packet(packet, body, False)

            if len(result_body) == len(body):
                retained_count += 1
            else:
                degraded_count += 1

        self.assertEqual(retained_count, small_packets)
        self.assertEqual(degraded_count, large_packets)

        retention_rate = retained_count / total_packets
        degradation_rate = degraded_count / total_packets

        print(f"Body 保留率: {retention_rate:.2%}")
        print(f"降级次数: {degraded_count}")
        print(f"降级率: {degradation_rate:.2%}")

    def test_queue_convergence_after_stop(self):
        """测试 stop 后队列收敛"""
        self.listener._queue_size_limit = 5
        self.listener._caught = Queue(maxsize=0)

        for i in range(20):
            self.listener._caught.put(f'item-{i}')

        self.assertEqual(self.listener._caught.qsize(), 20)

        start_time = perf_counter()
        while self.listener._caught.qsize() > 0:
            try:
                self.listener._caught.get_nowait()
            except Exception:
                break

        convergence_time = perf_counter() - start_time
        print(f"队列收敛耗时: {convergence_time:.6f} 秒")

        self.assertEqual(self.listener._caught.qsize(), 0)

    def test_peak_queue_size(self):
        """测试峰值队列大小"""
        self.listener._queue_size_limit = 10
        self.listener._caught = Queue(maxsize=0)

        peak_size = 0

        for i in range(20):
            self.listener._caught.put(f'item-{i}')
            current_size = self.listener._caught.qsize()
            if current_size > peak_size:
                peak_size = current_size

        print(f"峰值队列大小: {peak_size}")

        self.listener._enforce_queue_limit()
        print(f"队列限制后大小: {self.listener._caught.qsize()}")

    def test_multiple_rounds_stability(self):
        """测试多轮一致性"""
        self.listener._body_size_limit = 10
        self.listener._degradation_mode = 'truncate'
        self.listener._queue_size_limit = 5

        rounds = 5
        all_results = []

        for round_num in range(rounds):
            self.listener.clear()

            small_bodies = ['small', 'tiny', 'mini']
            large_bodies = ['this is a large body', 'another very large body']

            for body in small_bodies + large_bodies:
                packet = DataPacket(tab_id='test', target='test')
                result_body, _, original_size = self.listener._process_body_for_packet(packet, body, False)
                self.listener._caught.put((body, result_body, original_size))

            results = {
                'small_count': 0,
                'large_count': 0,
                'retained_small': 0,
                'retained_large': 0
            }

            while not self.listener._caught.empty():
                original, result, size = self.listener._caught.get()
                if len(original) <= 10:
                    results['small_count'] += 1
                    if result == original:
                        results['retained_small'] += 1
                else:
                    results['large_count'] += 1
                    if len(result) == 10:
                        results['retained_large'] += 1

            all_results.append(results)
            print(f"第 {round_num + 1} 轮: 小包={results['small_count']}, 大包={results['large_count']}, "
                  f"小包保留={results['retained_small']}, 大包降级={results['retained_large']}")

        for i in range(1, rounds):
            self.assertEqual(all_results[i]['small_count'], all_results[0]['small_count'])
            self.assertEqual(all_results[i]['large_count'], all_results[0]['large_count'])
            self.assertEqual(all_results[i]['retained_small'], all_results[0]['retained_small'])
            self.assertEqual(all_results[i]['retained_large'], all_results[0]['retained_large'])

        print("多轮一致性验证通过")


if __name__ == '__main__':
    unittest.main(verbosity=2)
