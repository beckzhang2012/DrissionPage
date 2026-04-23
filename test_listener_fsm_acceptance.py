# -*- coding:utf-8 -*-
"""
Network 事件状态机验收测试
覆盖：乱序事件、竞争条件、stop/pause收敛、旧行为回归
"""
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from queue import Queue
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from DrissionPage._units.listener import Listener, RequestState, _TERMINAL_STATES


class TestAcceptanceScenarios(unittest.TestCase):
    """验收测试：补齐所有需要实测的场景"""

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
        listener = Listener(self.mock_owner)
        listener._driver = self._create_mock_driver()
        listener._caught = Queue(maxsize=0)
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._fsm_states = {}
        listener._pending_events = {}
        listener._fsm_stats = {
            'out_of_order_count': 0,
            'missing_events_count': 0,
            'duplicate_terminal_count': 0,
        }
        listener._running_requests = 0
        listener._running_targets = 0
        listener._targets = True
        listener._method = True
        listener._res_type = True
        return listener

    # ========================================================================
    # 场景1：response先于request（乱序）
    # ========================================================================
    def test_response_before_request(self):
        """验收场景：response先于request到达"""
        listener = self._create_listener()
        rid = 'test-resp-before-req'

        listener._response_received(
            requestId=rid,
            response={'status': 200, 'url': 'http://test.com/api'},
            type='XHR'
        )

        self.assertEqual(listener._fsm_stats['out_of_order_count'], 1)
        self.assertEqual(listener._fsm_states[rid], RequestState.PENDING)
        self.assertIn('responseReceived', listener._pending_events[rid])

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com/api', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._fsm_states[rid], RequestState.ACTIVE)
        self.assertEqual(listener._running_requests, 1)

        packet = listener._request_ids.get(rid)
        self.assertIsNotNone(packet)
        self.assertIsNotNone(packet._raw_response)

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_states[rid], RequestState.COMPLETED)
        self.assertEqual(listener._caught.qsize(), 1)

    # ========================================================================
    # 场景2：extraInfo晚到/缺失
    # ========================================================================
    def test_extra_info_arrives_late(self):
        """验收场景：extraInfo在loadingFinished之后才到达"""
        listener = self._create_listener()
        rid = 'test-extra-info-late'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com/api', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        listener._response_received(
            requestId=rid,
            response={'status': 200, 'url': 'http://test.com/api'},
            type='XHR'
        )

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_states[rid], RequestState.COMPLETED)

        listener._responseReceivedExtraInfo(
            requestId=rid,
            statusCode=200,
            headers={'X-Extra-Info': 'late-arrival'}
        )

        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 1)

    def test_extra_info_missing(self):
        """验收场景：extraInfo完全缺失"""
        listener = self._create_listener()
        rid = 'test-extra-info-missing'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com/api', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        listener._response_received(
            requestId=rid,
            response={'status': 200, 'url': 'http://test.com/api'},
            type='XHR'
        )

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_states[rid], RequestState.COMPLETED)
        self.assertEqual(listener._caught.qsize(), 1)

        packet = listener._caught.get_nowait()
        self.assertIsNotNone(packet)
        self.assertIsNone(packet._requestExtraInfo)
        self.assertIsNone(packet._responseExtraInfo)

    # ========================================================================
    # 场景3：loadingFailed与loadingFinished竞争
    # ========================================================================
    def test_loading_finished_then_failed(self):
        """验收场景：loadingFinished先到，loadingFailed后到"""
        listener = self._create_listener()
        rid = 'test-finished-then-failed'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com/api', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        listener._response_received(
            requestId=rid,
            response={'status': 200, 'url': 'http://test.com/api'},
            type='XHR'
        )

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_states[rid], RequestState.COMPLETED)
        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        listener._loading_failed(
            requestId=rid,
            errorText='network error',
            type='XHR'
        )

        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 1)
        self.assertEqual(listener._fsm_states[rid], RequestState.COMPLETED)
        self.assertEqual(listener._caught.qsize(), 1)
        packet = listener._caught.get_nowait()
        self.assertFalse(packet.is_failed)

    def test_loading_failed_then_finished(self):
        """验收场景：loadingFailed先到，loadingFinished后到"""
        listener = self._create_listener()
        rid = 'test-failed-then-finished'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com/api', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        listener._response_received(
            requestId=rid,
            response={'status': 200, 'url': 'http://test.com/api'},
            type='XHR'
        )

        listener._loading_failed(
            requestId=rid,
            errorText='network error',
            type='XHR'
        )

        self.assertEqual(listener._fsm_states[rid], RequestState.FAILED)
        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 1)
        self.assertEqual(listener._fsm_states[rid], RequestState.FAILED)
        self.assertEqual(listener._caught.qsize(), 1)
        packet = listener._caught.get_nowait()
        self.assertTrue(packet.is_failed)

    # ========================================================================
    # 场景4：同requestId重复终态去重
    # ========================================================================
    def test_duplicate_terminal_states(self):
        """验收场景：同requestId多次终态事件"""
        listener = self._create_listener()
        rid = 'test-duplicate-terminals'

        listener._requestWillBeSent(
            requestId=rid,
            request={'url': 'http://test.com/api', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 0)
        self.assertEqual(listener._caught.qsize(), 1)

        listener._loading_finished(
            requestId=rid,
            timestamp=12346
        )
        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 1)

        listener._loading_failed(
            requestId=rid,
            errorText='error1',
            type='XHR'
        )
        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 2)

        listener._loading_finished(
            requestId=rid,
            timestamp=12347
        )
        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 3)

        self.assertEqual(listener._caught.qsize(), 1)
        self.assertEqual(listener._running_targets, 0)

    # ========================================================================
    # 场景5：stop/pause期间在途请求收敛
    # ========================================================================
    def test_pause_with_inflight_requests(self):
        """验收场景：pause时有在途请求"""
        listener = self._create_listener()
        rid1 = 'inflight-1'
        rid2 = 'inflight-2'

        listener._requestWillBeSent(
            requestId=rid1,
            request={'url': 'http://test.com/api1', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )
        listener._requestWillBeSent(
            requestId=rid2,
            request={'url': 'http://test.com/api2', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._running_requests, 2)
        self.assertEqual(listener._running_targets, 2)

        listener.listening = True
        listener.pause(clear=False)

        self.assertFalse(listener.listening)

        listener._response_received(
            requestId=rid1,
            response={'status': 200},
            type='XHR'
        )

        listener._driver.run.return_value = {'body': 'test body', 'base64Encoded': False}
        listener._loading_finished(
            requestId=rid1,
            timestamp=12345
        )

        self.assertEqual(listener._fsm_states[rid1], RequestState.COMPLETED)
        self.assertEqual(listener._running_requests, 1)

    def test_stop_with_inflight_requests(self):
        """验收场景：stop时有在途请求"""
        listener = self._create_listener()
        rid1 = 'inflight-stop-1'
        rid2 = 'inflight-stop-2'

        listener._requestWillBeSent(
            requestId=rid1,
            request={'url': 'http://test.com/api1', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )
        listener._requestWillBeSent(
            requestId=rid2,
            request={'url': 'http://test.com/api2', 'method': 'GET'},
            type='XHR',
            frameId='test-frame-id'
        )

        self.assertEqual(listener._running_requests, 2)
        self.assertEqual(listener._running_targets, 2)

        listener.listening = True
        listener._driver.stop = MagicMock()
        listener.stop()

        self.assertFalse(listener.listening)
        self.assertEqual(listener._running_requests, 0)
        self.assertEqual(listener._running_targets, 0)
        self.assertEqual(len(listener._fsm_states), 0)
        self.assertEqual(listener._caught.qsize(), 0)


class TestOldBehaviorRegression(unittest.TestCase):
    """旧行为不回归验证：覆盖 start/wait/steps/pause/resume"""

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
        listener = Listener(self.mock_owner)
        listener._driver = self._create_mock_driver()
        listener._caught = Queue(maxsize=0)
        listener._request_ids = {}
        listener._extra_info_ids = {}
        listener._fsm_states = {}
        listener._pending_events = {}
        listener._fsm_stats = {
            'out_of_order_count': 0,
            'missing_events_count': 0,
            'duplicate_terminal_count': 0,
        }
        listener._running_requests = 0
        listener._running_targets = 0
        listener._targets = True
        listener._method = True
        listener._res_type = True
        return listener

    def test_start_listening(self):
        """旧行为回归：start启动监听"""
        listener = self._create_listener()
        listener.listening = False

        self.assertFalse(listener.listening)

        with patch('DrissionPage._units.listener.Driver') as mock_driver_class:
            mock_driver = MagicMock()
            mock_driver.is_running = True
            mock_driver.run.return_value = {'sessionId': 'test-session'}
            mock_driver_class.return_value = mock_driver

            listener._set_callback = MagicMock()

            listener.start()

            self.assertTrue(listener.listening)
            mock_driver_class.assert_called_once()
            listener._set_callback.assert_called_once()

    def test_clear_resets_all_state(self):
        """旧行为回归：clear重置所有状态"""
        listener = self._create_listener()

        listener._request_ids = {'test1': 'data1'}
        listener._extra_info_ids = {'test1': 'info1'}
        listener._fsm_states = {'test1': RequestState.ACTIVE}
        listener._pending_events = {'test1': {'response': True}}
        listener._fsm_stats = {
            'out_of_order_count': 5,
            'missing_events_count': 3,
            'duplicate_terminal_count': 2,
        }
        listener._running_requests = 3
        listener._running_targets = 2
        listener._caught.put('test-packet')

        listener.clear()

        self.assertEqual(listener._request_ids, {})
        self.assertEqual(listener._extra_info_ids, {})
        self.assertEqual(listener._fsm_states, {})
        self.assertEqual(listener._pending_events, {})
        self.assertEqual(listener._fsm_stats['out_of_order_count'], 0)
        self.assertEqual(listener._fsm_stats['missing_events_count'], 0)
        self.assertEqual(listener._fsm_stats['duplicate_terminal_count'], 0)
        self.assertEqual(listener._running_requests, 0)
        self.assertEqual(listener._running_targets, 0)
        self.assertEqual(listener._caught.qsize(), 0)

    def test_pause_resume_cycle(self):
        """旧行为回归：pause/resume循环"""
        listener = self._create_listener()
        listener.listening = True

        listener._driver.set_callback = MagicMock()

        listener.pause(clear=False)

        self.assertFalse(listener.listening)
        self.assertEqual(listener._driver.set_callback.call_count, 4)

        listener._set_callback = MagicMock()
        listener.resume()

        self.assertTrue(listener.listening)
        listener._set_callback.assert_called_once()

    def test_pause_with_clear(self):
        """旧行为回归：pause时clear"""
        listener = self._create_listener()
        listener.listening = True

        listener._request_ids = {'test': 'data'}
        listener._running_requests = 1
        listener._driver.set_callback = MagicMock()

        listener.pause(clear=True)

        self.assertFalse(listener.listening)
        self.assertEqual(listener._request_ids, {})
        self.assertEqual(listener._running_requests, 0)

    def test_resume_already_listening(self):
        """旧行为回归：resume时已经在监听"""
        listener = self._create_listener()
        listener.listening = True

        listener._set_callback = MagicMock()
        listener.resume()

        listener._set_callback.assert_not_called()
        self.assertTrue(listener.listening)

    def test_wait_timeout_with_timeout(self):
        """旧行为回归：wait超时"""
        listener = self._create_listener()
        listener.listening = True
        listener._driver.is_running = True

        result = listener.wait(count=1, timeout=0.01)

        self.assertFalse(result)

    def test_wait_success(self):
        """旧行为回归：wait成功"""
        listener = self._create_listener()
        listener.listening = True
        listener._driver.is_running = True

        test_packet = MagicMock()
        listener._caught.put(test_packet)

        result = listener.wait(count=1, timeout=1)

        self.assertEqual(result, test_packet)

    def test_wait_multiple(self):
        """旧行为回归：wait多个包"""
        listener = self._create_listener()
        listener.listening = True
        listener._driver.is_running = True

        packet1 = MagicMock()
        packet2 = MagicMock()
        listener._caught.put(packet1)
        listener._caught.put(packet2)

        result = listener.wait(count=2, timeout=1)

        self.assertEqual(result, [packet1, packet2])

    def test_steps_generator(self):
        """旧行为回归：steps生成器"""
        listener = self._create_listener()
        listener.listening = True
        listener._driver.is_running = True

        packet1 = MagicMock()
        packet2 = MagicMock()
        listener._caught.put(packet1)
        listener._caught.put(packet2)

        steps_generator = listener.steps(count=2, timeout=0.1, gap=1)

        results = []
        for step in steps_generator:
            results.append(step)
            if len(results) >= 2:
                listener.listening = False
                break

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], packet1)
        self.assertEqual(results[1], packet2)


def run_acceptance_tests():
    """运行验收测试并输出统计"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestAcceptanceScenarios))
    suite.addTests(loader.loadTestsFromTestCase(TestOldBehaviorRegression))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == '__main__':
    result = run_acceptance_tests()
    sys.exit(0 if result.wasSuccessful() else 1)
