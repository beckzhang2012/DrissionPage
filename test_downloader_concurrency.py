# -*- coding:utf-8 -*-
"""
测试 DownloadManager 并发状态一致性问题
"""
import threading
import time
from unittest.mock import MagicMock, patch
from DrissionPage._units.downloader import DownloadManager, DownloadMission, TabDownloadSettings


class MockBrowser:
    """模拟浏览器对象"""
    def __init__(self):
        self._driver = MagicMock()
        self._frames = {}
        self._relation = {}
        self._download_path = '/tmp/test'
        self.download_path = '/tmp/test'
    
    def _run_cdp(self, *args, **kwargs):
        return {}


def create_mission(mgr, mission_id='test_guid_1', tab_id='tab_1', state='running'):
    """创建一个模拟的 DownloadMission"""
    mission = MagicMock(spec=DownloadMission)
    mission._mgr = mgr
    mission.id = mission_id
    mission.tab_id = tab_id
    mission.from_tab = None
    mission.url = 'http://test.com/file.zip'
    mission.name = 'file.zip'
    mission.folder = '/tmp/test'
    mission.state = state
    mission.total_bytes = 1000
    mission.received_bytes = 0
    mission.final_path = None
    mission.tmp_path = '/tmp/test'
    mission._overwrite = None
    mission._is_done = False
    return mission


def test_concurrent_set_done():
    """测试并发调用 set_done 的竞态"""
    print("\n" + "="*60)
    print("测试1: 并发 set_done 竞态")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    mission = create_mission(mgr)
    mgr._missions[mission.id] = mission
    mgr._tab_missions.setdefault(mission.tab_id, set()).add(mission)
    
    print(f"初始状态:")
    print(f"  _missions 数量: {len(mgr._missions)}")
    print(f"  _tab_missions['tab_1'] 数量: {len(mgr._tab_missions.get('tab_1', set()))}")
    print(f"  mission.state: {mission.state}")
    print(f"  mission._is_done: {mission._is_done}")
    
    effective_calls = [0]
    state_after_first_call = [None]
    
    original_set_done = mgr.set_done
    
    def tracked_set_done(mission, state, final_path=None):
        is_effective = not mission._is_done and mission.id in mgr._missions
        original_set_done(mission, state, final_path)
        if is_effective:
            effective_calls[0] += 1
            if state_after_first_call[0] is None:
                state_after_first_call[0] = mission.state
    
    mgr.set_done = tracked_set_done
    
    threads = []
    results = []
    
    def worker(mission, state):
        try:
            mgr.set_done(mission, state)
            results.append((state, mission._is_done, mission.state))
        except Exception as e:
            results.append((state, 'error', str(e)))
    
    for i in range(10):
        state = 'completed' if i % 2 == 0 else 'canceled'
        t = threading.Thread(target=worker, args=(mission, state))
        threads.append(t)
    
    start_time = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    end_time = time.time()
    
    print(f"\n并发测试结果:")
    print(f"  线程数: 10")
    print(f"  耗时: {end_time - start_time:.4f}s")
    print(f"  实际有效调用次数: {effective_calls[0]} (预期: 1)")
    print(f"  各线程结果 (状态, is_done, final_state): {results}")
    
    print(f"\n最终状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 0)")
    print(f"  _tab_missions['tab_1'] 数量: {len(mgr._tab_missions.get('tab_1', set()))} (预期: 0)")
    print(f"  mission.state: {mission.state}")
    print(f"  mission._is_done: {mission._is_done} (预期: True)")
    
    all_results_consistent = all(r[1] == True and r[2] == mission.state for r in results if r[1] != 'error')
    
    issues = []
    
    if effective_calls[0] != 1:
        issues.append(f"BUG: 有效调用次数应该为 1，但实际为 {effective_calls[0]}")
    
    if len(mgr._missions) != 0:
        issues.append(f"BUG: _missions 应该为空，但有 {len(mgr._missions)} 个任务")
    
    if mission._is_done is not True:
        issues.append(f"BUG: _is_done 应该为 True，但为 {mission._is_done}")
    
    if not all_results_consistent:
        issues.append(f"BUG: 各线程看到的状态不一致")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题] 幂等性验证通过，所有线程看到一致的最终状态")
    
    return issues


def test_cancel_then_set_done():
    """测试先调用 cancel 再触发回调的竞态"""
    print("\n" + "="*60)
    print("测试2: cancel 后回调竞态")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    mission = create_mission(mgr)
    mgr._missions[mission.id] = mission
    mgr._tab_missions.setdefault(mission.tab_id, set()).add(mission)
    
    print(f"初始状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 1)")
    print(f"  _tab_missions['tab_1'] 数量: {len(mgr._tab_missions.get('tab_1', set()))} (预期: 1)")
    print(f"  mission.state: {mission.state} (预期: running)")
    print(f"  mission._is_done: {mission._is_done} (预期: False)")
    
    print(f"\n调用 cancel()...")
    mgr.cancel(mission)
    
    print(f"\ncancel 后状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 0)")
    print(f"  _tab_missions['tab_1'] 数量: {len(mgr._tab_missions.get('tab_1', set()))} (预期: 0)")
    print(f"  mission.state: {mission.state} (预期: canceled)")
    print(f"  mission._is_done: {mission._is_done} (预期: True)")
    
    issues = []
    
    if mission.id in mgr._missions:
        issues.append("BUG: cancel() 后任务仍在 _missions 中，可能导致回调重复处理")
    
    if mission._is_done is not True:
        issues.append("BUG: cancel() 后 _is_done 应该为 True")
    
    print(f"\n模拟浏览器回调触发 'canceled' 状态...")
    callback_would_process = mission.id in mgr._missions
    print(f"  回调是否会处理: {'是 - 存在竞态风险!' if callback_would_process else '否 - 正确'}")
    
    if callback_would_process:
        issues.append("BUG: 回调可能会重复处理已 cancel 的任务")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题]")
    
    return issues


def test_skip_then_set_done():
    """测试先调用 skip 再触发回调的竞态"""
    print("\n" + "="*60)
    print("测试3: skip 后回调竞态")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    mission = create_mission(mgr)
    mgr._missions[mission.id] = mission
    mgr._tab_missions.setdefault(mission.tab_id, set()).add(mission)
    
    print(f"初始状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 1)")
    print(f"  mission.state: {mission.state} (预期: running)")
    print(f"  mission._is_done: {mission._is_done} (预期: False)")
    
    print(f"\n调用 skip()...")
    mgr.skip(mission)
    
    print(f"\nskip 后状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 0)")
    print(f"  mission.state: {mission.state} (预期: skipped)")
    print(f"  mission._is_done: {mission._is_done} (预期: True)")
    
    issues = []
    
    if mission.id in mgr._missions:
        issues.append("BUG: skip() 后任务仍在 _missions 中，可能导致回调重复处理")
    
    if mission._is_done is not True:
        issues.append("BUG: skip() 后 _is_done 应该为 True")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题]")
    
    return issues


def test_tab_clear_leak():
    """测试 tab 清理后任务泄漏"""
    print("\n" + "="*60)
    print("测试4: tab 清理后任务泄漏")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    missions = []
    for i in range(5):
        mission = create_mission(mgr, mission_id=f'guid_{i}', tab_id=f'tab_{i % 2}')
        missions.append(mission)
        mgr._missions[mission.id] = mission
        mgr._tab_missions.setdefault(mission.tab_id, set()).add(mission)
    
    mgr._flags['tab_0'] = [True, missions[0]]
    mgr._flags['tab_1'] = [False, missions[1]]
    
    print(f"初始状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 5)")
    print(f"  _tab_missions 键: {list(mgr._tab_missions.keys())} (预期: ['tab_0', 'tab_1'])")
    print(f"  _tab_missions['tab_0'] 数量: {len(mgr._tab_missions.get('tab_0', set()))} (预期: 3)")
    print(f"  _tab_missions['tab_1'] 数量: {len(mgr._tab_missions.get('tab_1', set()))} (预期: 2)")
    print(f"  _flags 键: {list(mgr._flags.keys())} (预期: ['tab_0', 'tab_1'])")
    
    print(f"\n调用 clear_tab_info('tab_0')...")
    mgr.clear_tab_info('tab_0')
    
    print(f"\n清理后状态:")
    print(f"  _missions 数量: {len(mgr._missions)} (预期: 2 - 只保留 tab_1 的任务)")
    print(f"  _tab_missions 键: {list(mgr._tab_missions.keys())} (预期: ['tab_1'])")
    print(f"  _flags 键: {list(mgr._flags.keys())} (预期: ['tab_1'])")
    
    tab_0_missions_leaked = [m for m in missions if m.tab_id == 'tab_0' and m.id in mgr._missions]
    tab_1_missions_remaining = [m for m in missions if m.tab_id == 'tab_1' and m.id in mgr._missions]
    tab_0_missions_is_done = [m._is_done for m in missions if m.tab_id == 'tab_0']
    
    print(f"\n任务详细情况:")
    print(f"  属于 tab_0 但仍在 _missions 中的任务: {len(tab_0_missions_leaked)} 个 (预期: 0)")
    print(f"  属于 tab_1 且仍在 _missions 中的任务: {len(tab_1_missions_remaining)} 个 (预期: 2)")
    print(f"  tab_0 任务的 _is_done 状态: {tab_0_missions_is_done} (预期: 全部 True)")
    
    issues = []
    
    if len(tab_0_missions_leaked) > 0:
        issues.append(f"BUG: 清理 tab_0 后，其任务仍泄漏在 _missions 中: {[m.id for m in tab_0_missions_leaked]}")
    
    if not all(tab_0_missions_is_done):
        issues.append(f"BUG: 清理 tab_0 后，其任务的 _is_done 应该全部为 True")
    
    if len(tab_1_missions_remaining) != 2:
        issues.append(f"BUG: tab_1 的任务数量不对，预期 2，实际 {len(tab_1_missions_remaining)}")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题]")
    
    return issues


def test_state_priority():
    """测试状态优先级：canceled/skipped 应该优先于 completed"""
    print("\n" + "="*60)
    print("测试5: 状态优先级验证")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    print(f"\n场景1: 先 cancel，再尝试 completed")
    mission1 = create_mission(mgr, 'guid_1')
    mgr._missions[mission1.id] = mission1
    mgr._tab_missions.setdefault(mission1.tab_id, set()).add(mission1)
    
    mgr.cancel(mission1)
    state_after_cancel = mission1.state
    
    mgr.set_done(mission1, 'completed', '/final/path')
    
    print(f"  cancel 后的 state: {state_after_cancel} (预期: canceled)")
    print(f"  尝试 set_done(completed) 后的 state: {mission1.state} (预期: canceled - 不应被覆盖)")
    print(f"  尝试 set_done(completed) 后的 _is_done: {mission1._is_done} (预期: True)")
    
    print(f"\n场景2: 先 skip，再尝试 completed")
    mission2 = create_mission(mgr, 'guid_2')
    mgr._missions[mission2.id] = mission2
    mgr._tab_missions.setdefault(mission2.tab_id, set()).add(mission2)
    
    mgr.skip(mission2)
    state_after_skip = mission2.state
    
    mgr.set_done(mission2, 'completed', '/final/path')
    
    print(f"  skip 后的 state: {state_after_skip} (预期: skipped)")
    print(f"  尝试 set_done(completed) 后的 state: {mission2.state} (预期: skipped - 不应被覆盖)")
    print(f"  尝试 set_done(completed) 后的 _is_done: {mission2._is_done} (预期: True)")
    
    issues = []
    
    if mission1.state != 'canceled':
        issues.append(f"BUG: canceled 状态被 completed 覆盖了! 当前 state: {mission1.state}")
    
    if mission2.state != 'skipped':
        issues.append(f"BUG: skipped 状态被 completed 覆盖了! 当前 state: {mission2.state}")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题]")
    
    return issues


def test_repeated_calls_idempotency():
    """测试重复调用的幂等性"""
    print("\n" + "="*60)
    print("测试6: 重复调用幂等性验证")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    mission = create_mission(mgr, 'test_guid')
    mgr._missions[mission.id] = mission
    mgr._tab_missions.setdefault(mission.tab_id, set()).add(mission)
    
    print(f"初始状态:")
    print(f"  _missions 数量: {len(mgr._missions)}")
    print(f"  mission._is_done: {mission._is_done}")
    
    print(f"\n第一次调用 set_done...")
    mgr.set_done(mission, 'completed', '/path/to/file')
    state1 = mission.state
    is_done1 = mission._is_done
    missions_count1 = len(mgr._missions)
    
    print(f"  结果: state={state1}, _is_done={is_done1}, _missions={missions_count1}")
    
    print(f"\n第二次调用 set_done (相同参数)...")
    mgr.set_done(mission, 'completed', '/path/to/file')
    state2 = mission.state
    is_done2 = mission._is_done
    missions_count2 = len(mgr._missions)
    
    print(f"  结果: state={state2}, _is_done={is_done2}, _missions={missions_count2}")
    
    print(f"\n第三次调用 set_done (不同状态)...")
    mgr.set_done(mission, 'canceled', '/different/path')
    state3 = mission.state
    is_done3 = mission._is_done
    missions_count3 = len(mgr._missions)
    
    print(f"  结果: state={state3}, _is_done={is_done3}, _missions={missions_count3}")
    
    issues = []
    
    if state1 != 'completed':
        issues.append(f"BUG: 第一次 set_done 后状态应该为 completed，实际为 {state1}")
    
    if state2 != 'completed':
        issues.append(f"BUG: 第二次 set_done 后状态应该保持 completed，实际为 {state2}")
    
    if state3 != 'completed':
        issues.append(f"BUG: 第三次 set_done 后状态应该保持 completed (幂等性)，实际为 {state3}")
    
    if not (is_done1 == is_done2 == is_done3 == True):
        issues.append(f"BUG: _is_done 应该始终为 True")
    
    if not (missions_count1 == missions_count2 == missions_count3 == 0):
        issues.append(f"BUG: _missions 应该始终为空")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题] 幂等性验证通过，重复调用不会改变状态")
    
    return issues


def test_cancel_idempotency():
    """测试 cancel 的幂等性"""
    print("\n" + "="*60)
    print("测试7: cancel 幂等性验证")
    print("="*60)
    
    browser = MockBrowser()
    mgr = DownloadManager(browser)
    
    mission = create_mission(mgr, 'test_guid')
    mgr._missions[mission.id] = mission
    mgr._tab_missions.setdefault(mission.tab_id, set()).add(mission)
    
    print(f"初始状态:")
    print(f"  _missions 数量: {len(mgr._missions)}")
    print(f"  mission._is_done: {mission._is_done}")
    print(f"  mission.state: {mission.state}")
    
    print(f"\n第一次调用 cancel...")
    mgr.cancel(mission)
    state1 = mission.state
    is_done1 = mission._is_done
    missions_count1 = len(mgr._missions)
    
    print(f"  结果: state={state1}, _is_done={is_done1}, _missions={missions_count1}")
    
    print(f"\n第二次调用 cancel...")
    mgr.cancel(mission)
    state2 = mission.state
    is_done2 = mission._is_done
    missions_count2 = len(mgr._missions)
    
    print(f"  结果: state={state2}, _is_done={is_done2}, _missions={missions_count2}")
    
    issues = []
    
    if state1 != 'canceled':
        issues.append(f"BUG: 第一次 cancel 后状态应该为 canceled，实际为 {state1}")
    
    if state2 != 'canceled':
        issues.append(f"BUG: 第二次 cancel 后状态应该保持 canceled，实际为 {state2}")
    
    if not (is_done1 == is_done2 == True):
        issues.append(f"BUG: _is_done 应该为 True")
    
    if not (missions_count1 == missions_count2 == 0):
        issues.append(f"BUG: _missions 应该为空")
    
    if issues:
        print(f"\n[问题发现]")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print(f"\n[无问题] cancel 幂等性验证通过")
    
    return issues


def main():
    """运行所有测试"""
    print("="*60)
    print("DownloadManager 并发状态一致性测试")
    print("="*60)
    
    all_issues = []
    
    tests = [
        test_concurrent_set_done,
        test_cancel_then_set_done,
        test_skip_then_set_done,
        test_tab_clear_leak,
        test_state_priority,
        test_repeated_calls_idempotency,
        test_cancel_idempotency,
    ]
    
    for test in tests:
        issues = test()
        all_issues.extend(issues)
    
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    if all_issues:
        print(f"共发现 {len(all_issues)} 个问题:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("所有测试通过，未发现问题")
    
    return all_issues


if __name__ == '__main__':
    main()
