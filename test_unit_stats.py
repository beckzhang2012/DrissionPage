# -*- coding:utf-8 -*-
"""
单元测试验证新增的统计返回功能
验证:
1. DownloadManager.clear_tab_info() 的 return_stats 参数
2. Listener.stop() 和 clear() 的 return_stats 参数
3. Driver._stop() 的统计返回功能
4. 向后兼容性验证
"""
import unittest
from unittest.mock import Mock, MagicMock, patch
from queue import Queue


class TestDownloadManagerStats(unittest.TestCase):
    """测试 DownloadManager.clear_tab_info 的统计返回功能"""

    def setUp(self):
        from DrissionPage._units.downloader import DownloadManager, TabDownloadSettings, DownloadMission
        
        self.mock_browser = Mock()
        self.mock_browser.download_path = '/tmp/test'
        self.mock_browser._download_path = '/tmp/test'
        
        TabDownloadSettings.TABS.clear()
        self.dl_mgr = DownloadManager(self.mock_browser)
    
    def test_clear_tab_info_without_stats_returns_none(self):
        """验证不使用 return_stats 时返回 None（向后兼容）"""
        result = self.dl_mgr.clear_tab_info('non_existent_tab')
        self.assertIsNone(result)
    
    def test_clear_tab_info_with_stats_returns_dict(self):
        """使用 return_stats=True 时返回统计字典"""
        result = self.dl_mgr.clear_tab_info('non_existent_tab', return_stats=True)
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('skipped', result)
        self.assertIn('failed', result)
        self.assertIn('missions_cleared', result)
        self.assertIn('tab_missions_cleared', result)
        self.assertIn('flags_cleared', result)
        self.assertIn('settings_cleared', result)
        self.assertIn('waiting_cleared', result)
        self.assertIn('_return_stats', result)
    
    def test_clear_tab_info_skips_when_no_data(self):
        """验证没有数据时返回 skipped=1"""
        result = self.dl_mgr.clear_tab_info('non_existent_tab', return_stats=True)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['success'], 0)
    
    def test_clear_tab_info_clears_missions(self):
        """验证能正确清理任务并返回统计"""
        from DrissionPage._units.downloader import TabDownloadSettings
        
        test_tab_id = 'test_tab_123'
        
        TabDownloadSettings(test_tab_id)
        self.assertIn(test_tab_id, TabDownloadSettings.TABS)
        
        self.dl_mgr._flags[test_tab_id] = True
        self.dl_mgr._waiting_tab.add(test_tab_id)
        
        result = self.dl_mgr.clear_tab_info(test_tab_id, return_stats=True)
        
        self.assertEqual(result['settings_cleared'], 1)
        self.assertEqual(result['flags_cleared'], 1)
        self.assertEqual(result['waiting_cleared'], 1)
        self.assertGreater(result['success'], 0)
        
        self.assertNotIn(test_tab_id, TabDownloadSettings.TABS)
        self.assertNotIn(test_tab_id, self.dl_mgr._flags)
        self.assertNotIn(test_tab_id, self.dl_mgr._waiting_tab)


class TestListenerStats(unittest.TestCase):
    """测试 Listener.stop() 和 clear() 的统计返回功能"""

    def setUp(self):
        from DrissionPage._units.listener import Listener
        
        self.mock_owner = Mock()
        self.mock_owner.browser = Mock()
        self.mock_owner.browser._ws_address = 'ws://localhost:9222'
        self.mock_owner._target_id = 'test_target'
        self.mock_owner.tab_id = 'test_tab'
        
        with patch.object(Listener, 'start'):
            self.listener = Listener(self.mock_owner)
            self.listener._driver = None
            self.listener.listening = False
            self.listener._caught = Queue()
            self.listener._request_ids = {}
            self.listener._extra_info_ids = {}
    
    def test_clear_without_stats_returns_none(self):
        """验证 clear() 不使用 return_stats 时返回 None（向后兼容）"""
        result = self.listener.clear()
        self.assertIsNone(result)
    
    def test_clear_with_stats_returns_dict(self):
        """验证 clear(return_stats=True) 返回统计字典"""
        result = self.listener.clear(return_stats=True)
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('skipped', result)
        self.assertIn('failed', result)
        self.assertIn('packets_cleared', result)
        self.assertIn('requests_cleared', result)
        self.assertIn('_return_stats', result)
    
    def test_clear_clears_queues(self):
        """验证 clear() 正确清空队列并返回统计"""
        self.listener._caught.put('test_packet_1')
        self.listener._caught.put('test_packet_2')
        self.listener._request_ids = {'req1': 'data1', 'req2': 'data2'}
        
        result = self.listener.clear(return_stats=True)
        
        self.assertEqual(result['packets_cleared'], 2)
        self.assertEqual(result['requests_cleared'], 2)
        self.assertEqual(result['success'], 1)
        self.assertEqual(self.listener._caught.qsize(), 0)
        self.assertEqual(len(self.listener._request_ids), 0)
    
    def test_stop_without_stats_returns_none(self):
        """验证 stop() 不使用 return_stats 时返回 None（向后兼容）"""
        result = self.listener.stop()
        self.assertIsNone(result)
    
    def test_stop_with_stats_returns_dict(self):
        """验证 stop(return_stats=True) 返回统计字典"""
        result = self.listener.stop(return_stats=True)
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('skipped', result)
        self.assertIn('failed', result)
        self.assertIn('packets_cleared', result)
        self.assertIn('requests_cleared', result)
        self.assertIn('driver_stopped', result)
        self.assertIn('_return_stats', result)
    
    def test_stop_skips_when_already_stopped(self):
        """验证已经停止时返回 skipped=1"""
        self.listener._driver = None
        self.listener.listening = False
        
        result = self.listener.stop(return_stats=True)
        self.assertEqual(result['skipped'], 1)


class TestDriverStats(unittest.TestCase):
    """测试 Driver._stop() 的统计返回功能"""

    def setUp(self):
        from DrissionPage._base.driver import Driver
        
        with patch('DrissionPage._base.driver.create_connection'):
            with patch.object(Driver, 'start'):
                self.driver = Driver.__new__(Driver)
                self.driver.id = 'test_driver'
                self.driver.address = 'ws://localhost:9222'
                self.driver.is_running = False
                self.driver._ws = None
                self.driver.event_handlers = {}
                self.driver.immediate_event_handlers = {}
                self.driver.method_results = {}
                self.driver.event_queue = Queue()
                self.driver.immediate_event_queue = Queue()
    
    def test__stop_without_stats_returns_boolean(self):
        """验证 _stop() 不使用 return_stats 时返回布尔值（向后兼容）"""
        result = self.driver._stop()
        self.assertIsInstance(result, bool)
    
    def test__stop_with_stats_returns_dict(self):
        """验证 _stop(return_stats=True) 返回统计字典"""
        result = self.driver._stop(return_stats=True)
        self.assertIsInstance(result, dict)
        self.assertIn('success', result)
        self.assertIn('skipped', result)
        self.assertIn('failed', result)
        self.assertIn('threads_joined', result)
        self.assertIn('handlers_cleared', result)
        self.assertIn('queues_cleared', result)
        self.assertIn('_return_stats', result)
    
    def test__stop_skips_when_not_running(self):
        """验证未运行时返回 skipped=1"""
        self.driver.is_running = False
        result = self.driver._stop(return_stats=True)
        self.assertEqual(result['skipped'], 1)
    
    def test__stop_clears_handlers(self):
        """验证 _stop() 正确清理处理器并返回统计"""
        self.driver.is_running = True
        self.driver._ws = None
        self.driver.event_handlers = {'event1': lambda: None, 'event2': lambda: None}
        self.driver.immediate_event_handlers = {'event3': lambda: None}
        self.driver.method_results = {'id1': Queue()}
        self.driver.event_queue.put('event_data')
        
        result = self.driver._stop(return_stats=True)
        
        self.assertEqual(result['handlers_cleared'], 3)
        self.assertEqual(result['queues_cleared'], 1)
        self.assertGreater(result['success'], 0)


class TestBackwardCompatibility(unittest.TestCase):
    """测试向后兼容性"""

    def test_download_manager_clear_tab_info_backward_compatible(self):
        """验证 DownloadManager.clear_tab_info() 原有调用方式仍然有效"""
        from DrissionPage._units.downloader import DownloadManager, TabDownloadSettings
        
        mock_browser = Mock()
        mock_browser.download_path = '/tmp/test'
        mock_browser._download_path = '/tmp/test'
        
        TabDownloadSettings.TABS.clear()
        dl_mgr = DownloadManager(mock_browser)
        
        result1 = dl_mgr.clear_tab_info('tab1')
        self.assertIsNone(result1)
        
        test_tab = 'tab2'
        TabDownloadSettings(test_tab)
        result2 = dl_mgr.clear_tab_info(test_tab)
        self.assertIsNone(result2)
    
    def test_listener_clear_backward_compatible(self):
        """验证 Listener.clear() 原有调用方式仍然有效"""
        from DrissionPage._units.listener import Listener
        
        mock_owner = Mock()
        mock_owner.browser = Mock()
        mock_owner.browser._ws_address = 'ws://localhost:9222'
        mock_owner._target_id = 'test_target'
        mock_owner.tab_id = 'test_tab'
        
        with patch.object(Listener, 'start'):
            listener = Listener(mock_owner)
            listener._driver = None
            listener.listening = False
            listener._caught = Queue()
            listener._request_ids = {}
            listener._extra_info_ids = {}
            
            result = listener.clear()
            self.assertIsNone(result)
    
    def test_listener_stop_backward_compatible(self):
        """验证 Listener.stop() 原有调用方式仍然有效"""
        from DrissionPage._units.listener import Listener
        
        mock_owner = Mock()
        mock_owner.browser = Mock()
        mock_owner.browser._ws_address = 'ws://localhost:9222'
        mock_owner._target_id = 'test_target'
        mock_owner.tab_id = 'test_tab'
        
        with patch.object(Listener, 'start'):
            listener = Listener(mock_owner)
            listener._driver = None
            listener.listening = False
            listener._caught = Queue()
            listener._request_ids = {}
            listener._extra_info_ids = {}
            
            result = listener.stop()
            self.assertIsNone(result)
    
    def test_driver_stop_backward_compatible(self):
        """验证 Driver.stop() 原有调用方式仍然有效"""
        from DrissionPage._base.driver import Driver
        
        with patch('DrissionPage._base.driver.create_connection'):
            with patch.object(Driver, 'start'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_driver'
                driver.address = 'ws://localhost:9222'
                driver.is_running = False
                driver._ws = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                driver._recv_th = Mock()
                driver._recv_th.is_alive = Mock(return_value=False)
                driver._handle_event_th = Mock()
                driver._handle_event_th.is_alive = Mock(return_value=False)
                driver._handle_immediate_event_th = None
                
                result = driver.stop()
                self.assertIsInstance(result, bool)


class TestStatsDictStructure(unittest.TestCase):
    """测试统计字典的结构一致性"""

    def test_download_manager_stats_structure(self):
        """验证 DownloadManager.clear_tab_info 返回的统计字典结构"""
        from DrissionPage._units.downloader import DownloadManager, TabDownloadSettings
        
        mock_browser = Mock()
        mock_browser.download_path = '/tmp/test'
        mock_browser._download_path = '/tmp/test'
        
        TabDownloadSettings.TABS.clear()
        dl_mgr = DownloadManager(mock_browser)
        
        stats = dl_mgr.clear_tab_info('test_tab', return_stats=True)
        
        expected_keys = {
            'success', 'skipped', 'failed',
            'missions_cleared', 'tab_missions_cleared',
            'flags_cleared', 'settings_cleared', 'waiting_cleared',
            '_return_stats'
        }
        self.assertEqual(set(stats.keys()), expected_keys)
        
        for key in ['success', 'skipped', 'failed', 'missions_cleared',
                   'tab_missions_cleared', 'flags_cleared',
                   'settings_cleared', 'waiting_cleared']:
            self.assertIsInstance(stats[key], int)
        
        self.assertIsInstance(stats['_return_stats'], bool)
    
    def test_listener_clear_stats_structure(self):
        """验证 Listener.clear 返回的统计字典结构"""
        from DrissionPage._units.listener import Listener
        
        mock_owner = Mock()
        mock_owner.browser = Mock()
        mock_owner.browser._ws_address = 'ws://localhost:9222'
        mock_owner._target_id = 'test_target'
        mock_owner.tab_id = 'test_tab'
        
        with patch.object(Listener, 'start'):
            listener = Listener(mock_owner)
            listener._driver = None
            listener.listening = False
            listener._caught = Queue()
            listener._request_ids = {}
            listener._extra_info_ids = {}
            
            stats = listener.clear(return_stats=True)
            
            expected_keys = {
                'success', 'skipped', 'failed',
                'packets_cleared', 'requests_cleared',
                '_return_stats'
            }
            self.assertEqual(set(stats.keys()), expected_keys)
            
            for key in ['success', 'skipped', 'failed', 'packets_cleared', 'requests_cleared']:
                self.assertIsInstance(stats[key], int)
            
            self.assertIsInstance(stats['_return_stats'], bool)
    
    def test_listener_stop_stats_structure(self):
        """验证 Listener.stop 返回的统计字典结构"""
        from DrissionPage._units.listener import Listener
        
        mock_owner = Mock()
        mock_owner.browser = Mock()
        mock_owner.browser._ws_address = 'ws://localhost:9222'
        mock_owner._target_id = 'test_target'
        mock_owner.tab_id = 'test_tab'
        
        with patch.object(Listener, 'start'):
            listener = Listener(mock_owner)
            listener._driver = None
            listener.listening = False
            listener._caught = Queue()
            listener._request_ids = {}
            listener._extra_info_ids = {}
            
            stats = listener.stop(return_stats=True)
            
            expected_keys = {
                'success', 'skipped', 'failed',
                'packets_cleared', 'requests_cleared',
                'driver_stopped', '_return_stats'
            }
            self.assertEqual(set(stats.keys()), expected_keys)
            
            for key in ['success', 'skipped', 'failed', 'packets_cleared', 'requests_cleared']:
                self.assertIsInstance(stats[key], int)
            
            self.assertIsInstance(stats['driver_stopped'], bool)
            self.assertIsInstance(stats['_return_stats'], bool)
    
    def test_driver__stop_stats_structure(self):
        """验证 Driver._stop 返回的统计字典结构"""
        from DrissionPage._base.driver import Driver
        
        with patch('DrissionPage._base.driver.create_connection'):
            with patch.object(Driver, 'start'):
                driver = Driver.__new__(Driver)
                driver.id = 'test_driver'
                driver.address = 'ws://localhost:9222'
                driver.is_running = False
                driver._ws = None
                driver.event_handlers = {}
                driver.immediate_event_handlers = {}
                driver.method_results = {}
                driver.event_queue = Queue()
                driver.immediate_event_queue = Queue()
                
                stats = driver._stop(return_stats=True)
                
                expected_keys = {
                    'success', 'skipped', 'failed',
                    'threads_joined', 'handlers_cleared', 'queues_cleared',
                    '_return_stats'
                }
                self.assertEqual(set(stats.keys()), expected_keys)
                
                for key in ['success', 'skipped', 'failed', 'threads_joined',
                           'handlers_cleared', 'queues_cleared']:
                    self.assertIsInstance(stats[key], int)
                
                self.assertIsInstance(stats['_return_stats'], bool)


def run_tests():
    """运行所有测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestDownloadManagerStats))
    suite.addTests(loader.loadTestsFromTestCase(TestListenerStats))
    suite.addTests(loader.loadTestsFromTestCase(TestDriverStats))
    suite.addTests(loader.loadTestsFromTestCase(TestBackwardCompatibility))
    suite.addTests(loader.loadTestsFromTestCase(TestStatsDictStructure))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*60)
    print("测试汇总:")
    print(f"  运行测试数: {result.testsRun}")
    print(f"  通过: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  失败: {len(result.failures)}")
    print(f"  错误: {len(result.errors)}")
    print("="*60)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    exit_code = run_tests()
    print(f"\n$LASTEXITCODE = {exit_code}")
    exit(exit_code)
