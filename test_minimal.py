# -*- coding: utf-8 -*-
"""Minimal test to verify basic imports and functionality."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Step 1: Testing basic imports...")
try:
    from queue import Queue
    from threading import Thread, Lock
    print("  [OK] Standard library imports")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("Step 2: Testing DrissionPage imports...")
try:
    from DrissionPage._base.driver import (
        Driver, _DriverMetrics, _STATE_PENDING, _STATE_COMPLETED, 
        _STATE_CANCELLED, _STATE_TIMEOUT
    )
    print("  [OK] DrissionPage._base.driver imports")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Step 3: Testing DriverMetrics...")
try:
    _DriverMetrics.reset()
    assert _DriverMetrics.cross_session_mismatch == 0
    assert _DriverMetrics.late_response_isolated == 0
    assert _DriverMetrics.duplicate_execution_blocked == 0
    assert _DriverMetrics.final_state_consistent == 0
    assert _DriverMetrics.final_state_total == 0
    
    _DriverMetrics.record_final_state(True)
    _DriverMetrics.record_final_state(True)
    _DriverMetrics.record_final_state(False)
    
    assert _DriverMetrics.final_state_total == 3
    assert _DriverMetrics.final_state_consistent == 2
    assert _DriverMetrics.get_consistency_rate() == 2.0 / 3.0
    
    _DriverMetrics.reset()
    print("  [OK] DriverMetrics working correctly")
except Exception as e:
    print(f"  [FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("Step 4: Testing constants...")
try:
    assert _STATE_PENDING == 'pending'
    assert _STATE_COMPLETED == 'completed'
    assert _STATE_CANCELLED == 'cancelled'
    assert _STATE_TIMEOUT == 'timeout'
    print("  [OK] Constants correct")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print("\n" + "=" * 50)
print("All minimal tests passed!")
print("=" * 50)
print("\n$LASTEXITCODE: 0")
sys.exit(0)
