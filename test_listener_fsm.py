# -*- coding:utf-8 -*-
"""
Network 事件状态机测试
测试乱序事件、幂等性、降级策略
"""
import unittest
from unittest.mock import MagicMock, patch
from queue import Queue


class TestNetworkFSM(unittest.TestCase):
    """测试 Network 事件状态机"""

    def setUp(self):
        """设置测试环境"""
        self.mock_owner = MagicMock()
        self.mock_owner.tab_id = 'test-tab-id'
        self.mock_owner._target_id = 'test-target-id'
        self.mock_owner._is_diff_domain = False
        self.mock_owner._frame_id = 'test-frame-id'
        self.mock_owner.browser._ws_address = 'ws://test'

    def _create_mock_driver(self):
        """创建模拟的 Driver 对象"""
        mock_driver = MagicMock()
        mock_driver.is_running = True
        mock_driver.run.return_value = {}
        return mock_driver

    def _create_listener(self):
        """创建 Listener 实例"""
        from DrissionPage._units.listener import Listener
        listener = Listener(self.mock_owner)
        listener._driver = self._create_mock_driver()
        listener._caught = Queue(maxsize=0)
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._running_requests = 0
        listener._running_targets = 0
        listener._targets = True
        listener._method = True
        listener._res_type = True
        return listener

    def test_normal_sequence(self):
        """测试正常事件序列"""
        listener = self._create_listener()
        rid = 'req-1'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )
        self.assertEqual(listener._running_requests, 1)
        self.assertEqual(listener._running_targets, 1)

        listener._requestWillBeSentExtraInfo(
            requestId=rid,
            headers={'X-Test': 'test'}
        )

        listener._response_received(
            requestId=rid,
            response={'status': 200},
            type='XHR'
        )

        listener._responseReceivedExtraInfo(
            requestId=rid,
            statusCode=200,
            headers={'Content-Type': 'text/html'}
        )

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        packet = listener._caught.get_nowait()
        self.assertFalse(packet.is_failed)

    def test_out_of_order_response_before_request(self):
        """测试乱序：responseReceived 在 requestWillBeSent 之前"""
        listener = self._create_listener()
        rid = 'req-2'

        listener._response_received(
            requestId=rid,
            response={'status': 200},
            type='XHR'
        )

        self.assertEqual(listener._running_requests, 0)

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._running_requests, 1)
        self.assertIn(rid, listener._request_ids)
        packet = listener._request_ids[rid]
        self.assertIsNotNone(packet._raw_response)

    def test_out_of_order_loading_before_response(self):
        """测试乱序：loadingFinished 在 responseReceived 之前"""
        listener = self._create_listener()
        rid = 'req-3'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._running_requests, 1)

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        packet = listener._caught.get_nowait()
        self.assertFalse(packet.is_failed)

        listener._response_received(
            requestId=rid,
            response={'status': 200},
            type='XHR'
        )
        self.assertEqual(listener._caught.qsize(), 0)

    def test_idempotent_loading_finished(self):
        """测试幂等性：同一个 requestId 多次调用 loadingFinished"""
        listener = self._create_listener()
        rid = 'req-4'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._running_requests, 1)
        self.assertEqual(listener._running_targets, 1)

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        listener._loading_finished(
            requestId=rid,
            timestamp=12346
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        listener._loading_failed(
            requestId=rid,
            errorText='test error',
            type='XHR'
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

    def test_idempotent_loading_failed(self):
        """测试幂等性：同一个 requestId 多次调用 loadingFailed"""
        listener = self._create_listener()
        rid = 'req-5'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._running_requests, 1)
        self.assertEqual(listener._running_targets, 1)

        listener._loading_failed(
            requestId=rid,
            errorText='test error',
            type='XHR'
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        packet = listener._caught.get_nowait()
        self.assertTrue(packet.is_failed)

        listener._loading_failed(
            requestId=rid,
            errorText='test error 2',
            type='XHR'
        )
        self.assertEqual(listener._caught.qsize(), 0)

        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )
        self.assertEqual(listener._caught.qsize(), 0)

    def test_running_requests_counter(self):
        """测试 running_requests 计数正确性"""
        listener = self._create_listener()
        rid1 = 'req-6'
        rid2 = 'req-7'

        self.assertEqual(listener._running_requests, 0)

        listener._requestWillBeSent(
            requestId=rid1,
            request={'url': 'http://test1.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )
        self.assertEqual(listener._running_requests, 1)

        listener._requestWillBeSentExtraInfo(
            requestId=rid1,
            headers={'X-Test': 'test'}
        )
        self.assertEqual(listener._running_requests, 1)

        listener._response_received(
            requestId=rid1,
            response={'status': 200},
            type='XHR'
        )
        self.assertEqual(listener._running_requests, 1)

        listener._responseReceivedExtraInfo(
            requestId=rid1,
            statusCode=200,
            headers={}
        )
        self.assertEqual(listener._running_requests, 1)

        listener._requestWillBeSent(
            requestId=rid2,
            request={'url': 'http://test2.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )
        self.assertEqual(listener._running_requests, 2)

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid1,
            timestamp=12345
        )
        self.assertEqual(listener._running_requests, 1)

        listener._loading_finished(
            requestId=rid2,
            timestamp=12346
        )
        self.assertEqual(listener._running_requests, 0)

    def test_complex_out_of_order_scenario(self):
        """测试复杂乱序场景"""
        listener = self._create_listener()
        rid = 'req-8'

        listener._requestWillBeSentExtraInfo(
            requestId=rid,
            headers={'X-Test': 'test'}
        )
        self.assertEqual(listener._running_requests, 0)

        listener._responseReceivedExtraInfo(
            requestId=rid,
            statusCode=200,
            headers={'Content-Type': 'text/html'}
        )
        self.assertEqual(listener._running_requests, 0)

        listener._response_received(
            requestId=rid,
            response={'status': 200},
            type='XHR'
        )
        self.assertEqual(listener._running_requests, 0)

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )
        self.assertEqual(listener._running_requests, 1)

        self.assertIn(rid, listener._request_ids)
        packet = listener._request_ids[rid]
        self.assertIsNotNone(packet._raw_response)
        self.assertIsNotNone(packet._requestExtraInfo)
        self.assertIsNotNone(packet._responseExtraInfo)

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)


if __name__ == '__main__':
    unittest.main()
