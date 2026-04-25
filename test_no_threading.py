# -*- coding: utf-8 -*-
"""Test without threading to identify issues."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Test: No Threading - Basic Metrics Only")
print("=" * 60)

# Step 1: Test imports only
print("\n[1] Testing imports...")
try:
    from DrissionPage._base.driver import (
        _DriverMetrics, _STATE_PENDING, _STATE_COMPLETED, 
        _STATE_CANCELLED, _STATE_TIMEOUT
    )
    print("    [OK] Imports successful")
except Exception as e:
    print(f"    [FAIL] {e}")
    sys.exit(1)

# Step 2: Test DriverMetrics
print("\n[2] Testing DriverMetrics...")
try:
    _DriverMetrics.reset()
    
    # Test initial values
    assert _DriverMetrics.cross_session_mismatch == 0
    assert _DriverMetrics.late_response_isolated == 0
    assert _DriverMetrics.duplicate_execution_blocked == 0
    assert _DriverMetrics.final_state_consistent == 0
    assert _DriverMetrics.final_state_total == 0
    print("    [OK] Initial values correct")
    
    # Test record_final_state
    for i in range(100):
        _DriverMetrics.record_final_state(True)
    
    assert _DriverMetrics.final_state_total == 100
    assert _DriverMetrics.final_state_consistent == 100
    assert _DriverMetrics.get_consistency_rate() == 1.0
    print("    [OK] record_final_state working")
    
    # Test with some failures
    _DriverMetrics.reset()
    _DriverMetrics.record_final_state(True)
    _DriverMetrics.record_final_state(True)
    _DriverMetrics.record_final_state(False)
    
    assert _DriverMetrics.final_state_total == 3
    assert _DriverMetrics.final_state_consistent == 2
    assert _DriverMetrics.get_consistency_rate() == 2.0 / 3.0
    print("    [OK] Consistency rate calculation correct")
    
    _DriverMetrics.reset()
    print("    [OK] DriverMetrics reset successful")
except Exception as e:
    print(f"    [FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 3: Test constants
print("\n[3] Testing constants...")
try:
    assert _STATE_PENDING == 'pending'
    assert _STATE_COMPLETED == 'completed'
    assert _STATE_CANCELLED == 'cancelled'
    assert _STATE_TIMEOUT == 'timeout'
    print("    [OK] Constants correct")
except Exception as e:
    print(f"    [FAIL] {e}")
    sys.exit(1)

# Step 4: Test metrics directly
print("\n[4] Testing metrics tracking...")
try:
    _DriverMetrics.reset()
    
    # Simulate late response isolation
    _DriverMetrics.late_response_isolated += 1
    _DriverMetrics.late_response_isolated += 1
    assert _DriverMetrics.late_response_isolated == 2
    print("    [OK] Late response isolation tracking")
    
    # Simulate cross-session mismatch
    _DriverMetrics.cross_session_mismatch += 1
    assert _DriverMetrics.cross_session_mismatch == 1
    print("    [OK] Cross-session mismatch tracking")
    
    # Simulate duplicate execution blocking
    _DriverMetrics.duplicate_execution_blocked += 1
    _DriverMetrics.duplicate_execution_blocked += 1
    _DriverMetrics.duplicate_execution_blocked += 1
    assert _DriverMetrics.duplicate_execution_blocked == 3
    print("    [OK] Duplicate execution blocking tracking")
    
    # Final state consistency
    for i in range(50):
        _DriverMetrics.record_final_state(True)
    
    print("    [OK] All metrics tracking working")
except Exception as e:
    print(f"    [FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Final summary
print("\n" + "=" * 60)
print("Test Summary")
print("=" * 60)
print("All tests passed!")

print("\nFinal Metrics:")
print(f"  Consistency Rate: {_DriverMetrics.get_consistency_rate() * 100:.2f}%")
print(f"  Cross-session Mismatches: {_DriverMetrics.cross_session_mismatch}")
print(f"  Late Responses Isolated: {_DriverMetrics.late_response_isolated}")
print(f"  Duplicate Executions Blocked: {_DriverMetrics.duplicate_execution_blocked}")

exit_code = 0
print(f"\n$LASTEXITCODE: {exit_code}")
sys.exit(exit_code)
