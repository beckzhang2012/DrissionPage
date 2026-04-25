# -*- coding:utf-8 -*-
"""
Listener 内存保护单元测试
覆盖：小体积正常保留、大体积降级、混合流量稳定、stop后内存收敛、多轮一致性
"""
import sys
import unittest
from queue import Queue
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, '..')

from DrissionPage._units.listener import (
    Listener, ListenerMemoryStats, DataPacket, FrameListener
)


class TestListenerMemoryStats(unittest.TestCase):
    """测试 ListenerMemoryStats 统计类"""

    def test_initial_state(self):
        """测试初始状态"""
        stats = ListenerMemoryStats()
        self.assertEqual(stats._total_packets, 0)
        self.assertEqual(stats._degraded_count, 0)
        self.assertEqual(stats._truncated_count, 0)
        self.assertEqual(stats._skipped_count, 0)
        self.assertEqual(stats._peak_queue_size, 0)
        self.assertEqual(stats._peak_body_bytes, 0)
        self.assertEqual(stats._total_body_bytes, 0)
        self.assertEqual(stats._retained_count, 0)
        self.assertIsNone(stats._stop_time)

    def test_retention_rate_empty(self):
        """测试空统计时的保留率"""
        stats = ListenerMemoryStats()
        self.assertEqual(stats.retention_rate, 1.0)

    def test_degradation_rate_empty(self):
        """测试空统计时的降级率"""
        stats = ListenerMemoryStats()
        self.assertEqual(stats.degradation_rate, 0.0)

    def test_record_packet_normal(self):
        """测试记录正常数据包"""
        stats = ListenerMemoryStats()
        stats.record_packet(body_size=100, is_degraded=False)
        self.assertEqual(stats._total_packets, 1)
        self.assertEqual(stats._retained_count, 1)
        self.assertEqual(stats._degraded_count, 0)
        self.assertEqual(stats._peak_body_bytes, 100)
        self.assertEqual(stats._total_body_bytes, 100)
        self.assertEqual(stats.retention_rate, 1.0)
        self.assertEqual(stats.degradation_rate, 0.0)

    def test_record_packet_degraded(self):
        """测试记录降级数据包"""
        stats = ListenerMemoryStats()
        stats.record_packet(body_size=1000, is_degraded=True, is_truncated=True)
        self.assertEqual(stats._total_packets, 1)
        self.assertEqual(stats._retained_count, 1)
        self.assertEqual(stats._degraded_count, 1)
        self.assertEqual(stats._truncated_count, 1)
        self.assertEqual(stats.retention_rate, 1.0)
        self.assertEqual(stats.degradation_rate, 1.0)

    def test_record_packet_skipped(self):
        """测试记录跳过的数据包"""
        stats = ListenerMemoryStats()
        stats.record_packet(body_size=1000, is_degraded=True, is_skipped=True)
        self.assertEqual(stats._total_packets, 1)
        self.assertEqual(stats._retained_count, 0)
        self.assertEqual(stats._degraded_count, 1)
        self.assertEqual(stats._skipped_count, 1)
        self.assertEqual(stats.retention_rate, 0.0)
        self.assertEqual(stats.degradation_rate, 1.0)

    def test_record_queue_size(self):
        """测试记录队列大小"""
        stats = ListenerMemoryStats()
        stats.record_queue_size(10)
        self.assertEqual(stats._peak_queue_size, 10)
        stats.record_queue_size(5)
        self.assertEqual(stats._peak_queue_size, 10)
        stats.record_queue_size(15)
        self.assertEqual(stats._peak_queue_size, 15)

    def test_reset(self):
        """测试重置统计"""
        stats = ListenerMemoryStats()
        stats.record_packet(body_size=100, is_degraded=False)
        stats.record_queue_size(10)
        stats.mark_stop()
        stats.reset()
        self.assertEqual(stats._total_packets, 0)
        self.assertEqual(stats._peak_queue_size, 0)
        self.assertEqual(stats._peak_body_bytes, 0)
        self.assertIsNone(stats._stop_time)

    def test_to_dict(self):
        """测试转换为字典"""
        stats = ListenerMemoryStats()
        stats.record_packet(body_size=100, is_degraded=False)
        stats.record_packet(body_size=200, is_degraded=True, is_truncated=True)
        stats.record_queue_size(5)
        result = stats.to_dict()
        self.assertEqual(result['total_packets'], 2)
        self.assertEqual(result['retained_count'], 2)
        self.assertEqual(result['degraded_count'], 1)
        self.assertEqual(result['truncated_count'], 1)
        self.assertEqual(result['skipped_count'], 0)
        self.assertEqual(result['peak_queue_size'], 5)
        self.assertEqual(result['peak_body_bytes'], 200)
        self.assertEqual(result['total_body_bytes'], 300)


class TestDataPacketDegradationFlags(unittest.TestCase):
    """测试 DataPacket 降级标记"""

    def test_initial_flags(self):
        """测试初始标记状态"""
        packet = DataPacket(tab_id='test-tab', target='test-target')
        self.assertFalse(packet.is_body_degraded)
        self.assertFalse(packet.is_body_truncated)
        self.assertFalse(packet.is_body_skipped)
        self.assertEqual(packet.original_body_size, 0)

    def test_set_degraded_flags(self):
        """测试设置降级标记"""
        packet = DataPacket(tab_id='test-tab', target='test-target')
        packet._body_degraded = True
        packet._body_truncated = True
        packet._original_body_size = 1000
        self.assertTrue(packet.is_body_degraded)
        self.assertTrue(packet.is_body_truncated)
        self.assertFalse(packet.is_body_skipped)
        self.assertEqual(packet.original_body_size, 1000)

    def test_set_skipped_flags(self):
        """测试设置跳过标记"""
        packet = DataPacket(tab_id='test-tab', target='test-target')
        packet._body_degraded = True
        packet._body_skipped = True
        packet._original_body_size = 2000
        self.assertTrue(packet.is_body_degraded)
        self.assertFalse(packet.is_body_truncated)
        self.assertTrue(packet.is_body_skipped)
        self.assertEqual(packet.original_body_size, 2000)


class TestListenerMemoryLimits(unittest.TestCase):
    """测试 Listener 内存限制配置"""

    def setUp(self):
        """设置测试环境 - 创建 mock owner"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'

    def test_default_memory_limits(self):
        """测试默认内存限制"""
        listener = Listener(self.mock_owner)
        self.assertEqual(listener._body_size_limit, 10 * 1024 * 1024)
        self.assertEqual(listener._queue_size_limit, 1000)
        self.assertEqual(listener._degradation_mode, 'truncate')
        self.assertIsInstance(listener._memory_stats, ListenerMemoryStats)

    def test_set_memory_limits_valid(self):
        """测试设置有效内存限制"""
        listener = Listener(self.mock_owner)
        listener.set_memory_limits(
            body_size_limit=1024 * 1024,
            queue_size_limit=100,
            degradation_mode='skip'
        )
        self.assertEqual(listener._body_size_limit, 1024 * 1024)
        self.assertEqual(listener._queue_size_limit, 100)
        self.assertEqual(listener._degradation_mode, 'skip')

    def test_set_memory_limits_partial(self):
        """测试部分设置内存限制"""
        listener = Listener(self.mock_owner)
        original_body_limit = listener._body_size_limit
        original_queue_limit = listener._queue_size_limit
        original_mode = listener._degradation_mode

        listener.set_memory_limits(body_size_limit=512)
        self.assertEqual(listener._body_size_limit, 512)
        self.assertEqual(listener._queue_size_limit, original_queue_limit)
        self.assertEqual(listener._degradation_mode, original_mode)

    def test_set_memory_limits_invalid_body_size(self):
        """测试无效的 body 大小限制"""
        listener = Listener(self.mock_owner)
        with self.assertRaises(ValueError):
            listener.set_memory_limits(body_size_limit=-1)

    def test_set_memory_limits_invalid_queue_size(self):
        """测试无效的队列大小限制"""
        listener = Listener(self.mock_owner)
        with self.assertRaises(ValueError):
            listener.set_memory_limits(queue_size_limit=-1)

    def test_set_memory_limits_invalid_mode(self):
        """测试无效的降级模式"""
        listener = Listener(self.mock_owner)
        with self.assertRaises(ValueError):
            listener.set_memory_limits(degradation_mode='invalid')

    def test_memory_stats_property(self):
        """测试 memory_stats 属性"""
        listener = Listener(self.mock_owner)
        stats = listener.memory_stats
        self.assertIsInstance(stats, ListenerMemoryStats)
        self.assertIs(stats, listener._memory_stats)


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
        self.listener.set_memory_limits(body_size_limit=100)
        packet = DataPacket(tab_id='test', target='test')
        body = 'small body'
        is_base64 = False

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        self.assertEqual(result_body, body)
        self.assertEqual(result_base64, is_base64)
        self.assertEqual(original_size, len(body))
        self.assertFalse(packet.is_body_degraded)
        self.assertFalse(packet.is_body_truncated)
        self.assertFalse(packet.is_body_skipped)

    def test_process_body_large_truncate_mode(self):
        """测试大 body 在截断模式下的处理"""
        self.listener.set_memory_limits(body_size_limit=5, degradation_mode='truncate')
        packet = DataPacket(tab_id='test', target='test')
        body = 'This is a very long body content'
        is_base64 = False

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        self.assertEqual(len(result_body), 5)
        self.assertEqual(result_body, body[:5])
        self.assertEqual(original_size, len(body))
        self.assertTrue(packet.is_body_degraded)
        self.assertTrue(packet.is_body_truncated)
        self.assertFalse(packet.is_body_skipped)

    def test_process_body_large_skip_mode(self):
        """测试大 body 在跳过模式下的处理"""
        self.listener.set_memory_limits(body_size_limit=5, degradation_mode='skip')
        packet = DataPacket(tab_id='test', target='test')
        body = 'This is a very long body content'
        is_base64 = False

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, is_base64
        )

        self.assertEqual(result_body, '')
        self.assertEqual(result_base64, False)
        self.assertEqual(original_size, len(body))
        self.assertTrue(packet.is_body_degraded)
        self.assertFalse(packet.is_body_truncated)
        self.assertTrue(packet.is_body_skipped)

    def test_process_body_base64_truncate(self):
        """测试 base64 body 截断"""
        self.listener.set_memory_limits(body_size_limit=3, degradation_mode='truncate')
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
        self.assertTrue(packet.is_body_degraded)
        self.assertTrue(packet.is_body_truncated)

    def test_process_body_zero_limit(self):
        """测试 body 大小限制为 0（不限制）"""
        self.listener.set_memory_limits(body_size_limit=0)
        packet = DataPacket(tab_id='test', target='test')
        body = 'A' * 10000

        result_body, result_base64, original_size = self.listener._process_body_for_packet(
            packet, body, False
        )

        self.assertEqual(result_body, body)
        self.assertFalse(packet.is_body_degraded)


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
        self.listener.set_memory_limits(queue_size_limit=0)
        self.listener._caught = Queue(maxsize=0)

        for i in range(100):
            self.listener._caught.put(f'item-{i}')

        self.listener._enforce_queue_limit()
        self.assertEqual(self.listener._caught.qsize(), 100)

    def test_enforce_queue_limit_enabled(self):
        """测试队列限制启用"""
        self.listener.set_memory_limits(queue_size_limit=5)
        self.listener._caught = Queue(maxsize=0)
        self.listener._memory_stats = ListenerMemoryStats()

        for i in range(10):
            self.listener._caught.put(f'item-{i}')

        self.assertEqual(self.listener._caught.qsize(), 10)
        self.listener._enforce_queue_limit()
        self.assertEqual(self.listener._caught.qsize(), 4)

        remaining_items = []
        while not self.listener._caught.empty():
            remaining_items.append(self.listener._caught.get())

        self.assertEqual(remaining_items, ['item-6', 'item-7', 'item-8', 'item-9'])

    def test_peak_queue_size_recorded(self):
        """测试峰值队列大小被记录"""
        self.listener.set_memory_limits(queue_size_limit=5)
        self.listener._caught = Queue(maxsize=0)

        for i in range(10):
            self.listener._caught.put(f'item-{i}')

        self.listener._enforce_queue_limit()
        self.assertEqual(self.listener._memory_stats._peak_queue_size, 10)


class TestListenerClearAndStop(unittest.TestCase):
    """测试 Listener 的 clear 和 stop 方法"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'

    def test_clear_resets_memory_stats(self):
        """测试 clear 重置内存统计"""
        listener = Listener(self.mock_owner)
        listener._memory_stats.record_packet(body_size=100, is_degraded=False)
        listener._memory_stats.record_queue_size(10)

        listener.clear()

        self.assertEqual(listener._memory_stats._total_packets, 0)
        self.assertEqual(listener._memory_stats._peak_queue_size, 0)
        self.assertEqual(listener._caught.qsize(), 0)
        self.assertEqual(listener._request_ids, {})
        self.assertEqual(listener._extra_info_ids, {})

    def test_stop_marks_stop_time(self):
        """测试 stop 标记停止时间"""
        listener = Listener(self.mock_owner)
        listener.listening = False
        listener._driver = None

        self.assertIsNone(listener._memory_stats._stop_time)
        listener.stop()
        self.assertIsNotNone(listener._memory_stats._stop_time)

    def test_multiple_rounds_consistency(self):
        """测试多轮一致性"""
        listener = Listener(self.mock_owner)

        for round_num in range(3):
            listener._memory_stats.record_packet(body_size=100 + round_num, is_degraded=False)
            listener._memory_stats.record_queue_size(5 + round_num)

            stats = listener._memory_stats.to_dict()
            self.assertEqual(stats['total_packets'], 1)
            self.assertEqual(stats['peak_queue_size'], 5 + round_num)

            listener.clear()

            stats_after_clear = listener._memory_stats.to_dict()
            self.assertEqual(stats_after_clear['total_packets'], 0)


class TestDegradationScenarios(unittest.TestCase):
    """测试各种降级场景"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.browser._ws_address = 'ws://test:9222'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner.tab_id = 'test-tab-id'

    def test_mixed_traffic_statistics(self):
        """测试混合流量统计"""
        listener = Listener(self.mock_owner)
        listener.set_memory_limits(body_size_limit=10, degradation_mode='truncate')

        small_bodies = ['small', 'tiny', 'mini']
        large_bodies = ['this is a large body', 'another very large body here']

        for body in small_bodies:
            packet = DataPacket(tab_id='test', target='test')
            listener._process_body_for_packet(packet, body, False)
            listener._memory_stats.record_packet(
                body_size=len(body),
                is_degraded=packet.is_body_degraded,
                is_truncated=packet.is_body_truncated,
                is_skipped=packet.is_body_skipped
            )

        for body in large_bodies:
            packet = DataPacket(tab_id='test', target='test')
            listener._process_body_for_packet(packet, body, False)
            listener._memory_stats.record_packet(
                body_size=len(body),
                is_degraded=packet.is_body_degraded,
                is_truncated=packet.is_body_truncated,
                is_skipped=packet.is_body_skipped
            )

        stats = listener._memory_stats.to_dict()
        self.assertEqual(stats['total_packets'], 5)
        self.assertEqual(stats['retained_count'], 5)
        self.assertEqual(stats['degraded_count'], 2)
        self.assertEqual(stats['truncated_count'], 2)
        self.assertEqual(stats['skipped_count'], 0)
        self.assertEqual(stats['retention_rate'], 1.0)
        self.assertEqual(stats['degradation_rate'], 0.4)

    def test_skip_mode_retains_nothing(self):
        """测试跳过模式不保留大 body"""
        listener = Listener(self.mock_owner)
        listener.set_memory_limits(body_size_limit=10, degradation_mode='skip')

        large_body = 'this is a very large body content'
        packet = DataPacket(tab_id='test', target='test')
        result_body, _, _ = listener._process_body_for_packet(packet, large_body, False)

        self.assertEqual(result_body, '')
        self.assertTrue(packet.is_body_skipped)

        listener._memory_stats.record_packet(
            body_size=len(large_body),
            is_degraded=True,
            is_skipped=True
        )

        stats = listener._memory_stats.to_dict()
        self.assertEqual(stats['retention_rate'], 0.0)

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
        self.assertFalse(packet.is_body_degraded)


if __name__ == '__main__':
    unittest.main(verbosity=2)
