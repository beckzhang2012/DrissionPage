# -*- coding:utf-8 -*-
"""
Unit tests for tab lifecycle race condition protection
These tests verify the context validation logic without requiring a real browser.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Dict, Optional

sys.path.insert(0, 'd:\\work\\solo-coder\\task\\20260422-drissionpage-3314-tab-lifecycle-race-fix\\repo\\DrissionPage')

from DrissionPage._units.lifecycle_stats import lifecycle_stats


class TestLifecycleStats(unittest.TestCase):
    """Test lifecycle statistics tracking"""
    
    def setUp(self):
        lifecycle_stats.reset()
    
    def test_tab_state_transitions(self):
        """Test tab state transitions are tracked correctly"""
        tab_id = 'tab_123'
        
        lifecycle_stats.record_tab_state_change(tab_id, 'created')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'target_created')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'listener_bound')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'bound')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'closed')
        self.assertFalse(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'target_created')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'target_destroyed')
        self.assertFalse(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'listener_bound')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'listener_unbound')
        self.assertFalse(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'bound')
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'context_invalidated')
        self.assertFalse(lifecycle_stats.is_tab_alive(tab_id))
    
    def test_dropped_events_tracking(self):
        """Test dropped events are tracked correctly"""
        tab_id = 'tab_123'
        
        lifecycle_stats.record_dropped_event('Network.requestWillBeSent', tab_id, 'context_invalid')
        lifecycle_stats.record_dropped_event('Network.responseReceived', tab_id, 'tab_id_mismatch')
        lifecycle_stats.record_dropped_event('Network.requestWillBeSent', tab_id, 'context_invalid')
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_dropped'], 3)
        
        dropped = summary['events']['dropped_by_type']
        self.assertEqual(dropped.get('Network.requestWillBeSent:context_invalid', 0), 2)
        self.assertEqual(dropped.get('Network.responseReceived:tab_id_mismatch', 0), 1)
    
    def test_session_mappings(self):
        """Test session to tab mappings"""
        tab_id = 'tab_123'
        session_id = 'session_456'
        
        lifecycle_stats.bind_session_to_tab(tab_id, session_id)
        self.assertEqual(lifecycle_stats.get_session_for_tab(tab_id), session_id)
        
        lifecycle_stats.unbind_session_from_tab(tab_id)
        self.assertIsNone(lifecycle_stats.get_session_for_tab(tab_id))
    
    def test_event_hits_tracking(self):
        """Test event hits are tracked correctly"""
        tab_id_1 = 'tab_1'
        tab_id_2 = 'tab_2'
        
        lifecycle_stats.record_event_hit(tab_id_1)
        lifecycle_stats.record_event_hit(tab_id_1)
        lifecycle_stats.record_event_hit(tab_id_2)
        lifecycle_stats.record_event_validated(tab_id_1)
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_hits'], 3)
        self.assertEqual(summary['events']['total_validated'], 1)
        self.assertEqual(summary['events']['hits_by_tab'].get(tab_id_1, 0), 2)
        self.assertEqual(summary['events']['hits_by_tab'].get(tab_id_2, 0), 1)


class TestDriverContextValidation(unittest.TestCase):
    """Test Driver context validation logic"""
    
    def setUp(self):
        lifecycle_stats.reset()
    
    def test_bind_to_tab_sets_context_valid(self):
        """Test bind_to_tab sets context_valid to True"""
        from DrissionPage._base.driver import Driver
        
        driver = MagicMock(spec=Driver)
        driver._bound_tab_id = None
        driver._bound_session_id = None
        driver._context_valid = False
        
        def mock_bind(tab_id, session_id=None):
            driver._bound_tab_id = tab_id
            driver._bound_session_id = session_id
            driver._context_valid = True
            if tab_id:
                lifecycle_stats.record_tab_state_change(tab_id, 'bound')
                if session_id:
                    lifecycle_stats.bind_session_to_tab(tab_id, session_id)
        
        driver.bind_to_tab = mock_bind
        driver.bind_to_tab('tab_123', 'session_456')
        
        self.assertTrue(driver._context_valid)
        self.assertEqual(driver._bound_tab_id, 'tab_123')
        self.assertTrue(lifecycle_stats.is_tab_alive('tab_123'))
        self.assertEqual(lifecycle_stats.get_session_for_tab('tab_123'), 'session_456')
    
    def test_invalidate_context_sets_context_invalid(self):
        """Test invalidate_context sets context_valid to False"""
        from DrissionPage._base.driver import Driver
        
        driver = MagicMock(spec=Driver)
        driver._bound_tab_id = 'tab_123'
        driver._bound_session_id = 'session_456'
        driver._context_valid = True
        
        lifecycle_stats.record_tab_state_change('tab_123', 'bound')
        self.assertTrue(lifecycle_stats.is_tab_alive('tab_123'))
        
        def mock_invalidate():
            driver._context_valid = False
            if driver._bound_tab_id:
                lifecycle_stats.record_tab_state_change(
                    driver._bound_tab_id, 
                    'context_invalidated',
                    {'session_id': driver._bound_session_id}
                )
        
        driver.invalidate_context = mock_invalidate
        driver.invalidate_context()
        
        self.assertFalse(driver._context_valid)
        self.assertFalse(lifecycle_stats.is_tab_alive('tab_123'))
    
    def test_is_context_valid_checks_all_conditions(self):
        """Test _is_context_valid checks all conditions"""
        from DrissionPage._base.driver import Driver
        
        driver = MagicMock(spec=Driver)
        driver._context_valid = True
        driver.is_running = True
        driver._bound_tab_id = 'tab_123'
        
        lifecycle_stats.record_tab_state_change('tab_123', 'bound')
        
        def mock_is_valid():
            if not driver._context_valid:
                return False
            if not driver.is_running:
                return False
            if driver._bound_tab_id and not lifecycle_stats.is_tab_alive(driver._bound_tab_id):
                return False
            return True
        
        driver._is_context_valid = mock_is_valid
        
        self.assertTrue(driver._is_context_valid())
        
        driver._context_valid = False
        self.assertFalse(driver._is_context_valid())
        
        driver._context_valid = True
        driver.is_running = False
        self.assertFalse(driver._is_context_valid())
        
        driver.is_running = True
        lifecycle_stats.record_tab_state_change('tab_123', 'context_invalidated')
        self.assertFalse(driver._is_context_valid())


class TestListenerContextValidation(unittest.TestCase):
    """Test Listener context validation logic"""
    
    def setUp(self):
        lifecycle_stats.reset()
    
    def test_listener_is_context_valid(self):
        """Test Listener._is_context_valid checks all conditions"""
        from DrissionPage._units.listener import Listener
        
        listener = MagicMock(spec=Listener)
        listener._context_valid = True
        listener._driver = MagicMock()
        listener._driver.is_running = True
        listener._bound_tab_id = 'tab_123'
        listener._owner = MagicMock()
        listener._owner.tab_id = 'tab_123'
        
        lifecycle_stats.record_tab_state_change('tab_123', 'bound')
        
        def mock_is_valid():
            if not listener._context_valid:
                return False
            if not listener._driver or not listener._driver.is_running:
                return False
            if listener._bound_tab_id and not lifecycle_stats.is_tab_alive(listener._bound_tab_id):
                return False
            if listener._owner and hasattr(listener._owner, 'tab_id'):
                if listener._owner.tab_id != listener._bound_tab_id:
                    return False
            return True
        
        listener._is_context_valid = mock_is_valid
        
        self.assertTrue(listener._is_context_valid())
        
        listener._owner.tab_id = 'tab_456'
        self.assertFalse(listener._is_context_valid())
        
        listener._owner.tab_id = 'tab_123'
        lifecycle_stats.record_tab_state_change('tab_123', 'closed')
        self.assertFalse(listener._is_context_valid())
    
    def test_validate_event_context_records_dropped_events(self):
        """Test _validate_event_context records dropped events"""
        from DrissionPage._units.listener import Listener
        
        listener = MagicMock(spec=Listener)
        listener._context_valid = False
        listener._bound_tab_id = 'tab_123'
        listener._owner = None
        
        def mock_is_valid():
            return listener._context_valid
        
        listener._is_context_valid = mock_is_valid
        
        def mock_validate(event_method):
            if not listener._is_context_valid():
                lifecycle_stats.record_dropped_event(
                    event_method=event_method,
                    tab_id=listener._bound_tab_id,
                    reason='listener_context_invalid'
                )
                return False
            
            if listener._owner and hasattr(listener._owner, 'tab_id'):
                owner_tab_id = listener._owner.tab_id
                if owner_tab_id != listener._bound_tab_id:
                    lifecycle_stats.record_dropped_event(
                        event_method=event_method,
                        tab_id=listener._bound_tab_id,
                        reason='tab_id_mismatch'
                    )
                    return False
            
            return True
        
        listener._validate_event_context = mock_validate
        
        result = listener._validate_event_context('Network.requestWillBeSent')
        self.assertFalse(result)
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_dropped'], 1)
        self.assertIn('Network.requestWillBeSent:listener_context_invalid', summary['events']['dropped_by_type'])


class TestRaceConditionScenarios(unittest.TestCase):
    """Test race condition scenarios"""
    
    def setUp(self):
        lifecycle_stats.reset()
    
    def test_rapid_close_reopen_scenario(self):
        """Test rapid close and reopen scenario"""
        tab1_id = 'tab_old'
        tab2_id = 'tab_new'
        
        lifecycle_stats.record_tab_state_change(tab1_id, 'created')
        lifecycle_stats.record_tab_state_change(tab1_id, 'listener_bound')
        
        self.assertTrue(lifecycle_stats.is_tab_alive(tab1_id))
        
        lifecycle_stats.record_tab_state_change(tab1_id, 'closed')
        
        self.assertFalse(lifecycle_stats.is_tab_alive(tab1_id))
        
        lifecycle_stats.record_tab_state_change(tab2_id, 'created')
        lifecycle_stats.record_tab_state_change(tab2_id, 'listener_bound')
        
        self.assertTrue(lifecycle_stats.is_tab_alive(tab2_id))
        self.assertFalse(lifecycle_stats.is_tab_alive(tab1_id))
        
        lifecycle_stats.record_dropped_event('Network.requestWillBeSent', tab1_id, 'context_invalid')
        lifecycle_stats.record_event_hit(tab2_id)
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_dropped'], 1)
        self.assertEqual(summary['events']['total_hits'], 1)
        self.assertIn(tab1_id, summary['tabs']['dead_tabs'])
        self.assertIn(tab2_id, summary['tabs']['alive_tabs'])
    
    def test_concurrent_switch_scenario(self):
        """Test concurrent tab switch scenario"""
        tab1_id = 'tab_1'
        tab2_id = 'tab_2'
        tab3_id = 'tab_3'
        
        for tid in [tab1_id, tab2_id, tab3_id]:
            lifecycle_stats.record_tab_state_change(tid, 'created')
            lifecycle_stats.record_tab_state_change(tid, 'listener_bound')
        
        for tid in [tab1_id, tab2_id, tab3_id]:
            self.assertTrue(lifecycle_stats.is_tab_alive(tid))
        
        for i, tid in enumerate([tab1_id, tab2_id, tab3_id]):
            for _ in range(5):
                lifecycle_stats.record_event_hit(tid)
                lifecycle_stats.record_event_validated(tid)
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_hits'], 15)
        self.assertEqual(summary['events']['total_validated'], 15)
        self.assertEqual(len(summary['tabs']['alive_tabs']), 3)
    
    def test_stale_events_after_reconnect_scenario(self):
        """Test stale events after reconnect scenario"""
        tab_id = 'tab_1'
        old_session_id = 'session_old'
        new_session_id = 'session_new'
        
        lifecycle_stats.record_tab_state_change(tab_id, 'created')
        lifecycle_stats.bind_session_to_tab(tab_id, old_session_id)
        
        self.assertEqual(lifecycle_stats.get_session_for_tab(tab_id), old_session_id)
        
        lifecycle_stats.record_tab_state_change(tab_id, 'context_invalidated')
        lifecycle_stats.unbind_session_from_tab(tab_id)
        
        self.assertIsNone(lifecycle_stats.get_session_for_tab(tab_id))
        self.assertFalse(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_tab_state_change(tab_id, 'bound')
        lifecycle_stats.bind_session_to_tab(tab_id, new_session_id)
        
        self.assertEqual(lifecycle_stats.get_session_for_tab(tab_id), new_session_id)
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_dropped_event('Network.responseReceived', tab_id, 'tab_id_mismatch')
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_dropped'], 1)
        self.assertEqual(summary['session_mappings'][tab_id], new_session_id)
    
    def test_abort_recovery_scenario(self):
        """Test abort and recovery scenario"""
        tab_id = 'tab_1'
        
        lifecycle_stats.record_tab_state_change(tab_id, 'created')
        lifecycle_stats.record_tab_state_change(tab_id, 'listener_bound')
        
        for _ in range(3):
            lifecycle_stats.record_event_hit(tab_id)
        
        lifecycle_stats.record_tab_state_change(tab_id, 'listener_unbound')
        
        self.assertFalse(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_dropped_event('Network.requestWillBeSent', tab_id, 'listener_context_invalid')
        
        lifecycle_stats.record_tab_state_change(tab_id, 'listener_bound')
        
        self.assertTrue(lifecycle_stats.is_tab_alive(tab_id))
        
        lifecycle_stats.record_event_hit(tab_id)
        lifecycle_stats.record_event_validated(tab_id)
        
        summary = lifecycle_stats.get_summary()
        self.assertEqual(summary['events']['total_hits'], 4)
        self.assertEqual(summary['events']['total_validated'], 1)
        self.assertEqual(summary['events']['total_dropped'], 1)


def run_tests():
    """Run all tests and return results"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestLifecycleStats))
    suite.addTests(loader.loadTestsFromTestCase(TestDriverContextValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestListenerContextValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestRaceConditionScenarios))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    final_stats = lifecycle_stats.get_summary()
    print(f"\nFinal Statistics:")
    print(f"  Events Dropped: {final_stats['events']['total_dropped']}")
    print(f"  Events Validated: {final_stats['events']['total_validated']}")
    print(f"  Tabs Tracked: {final_stats['tabs']['total_tracked']}")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
