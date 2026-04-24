# -*- coding:utf-8 -*-
"""
Chromium tab 高频切换下 active 状态一致性测试
覆盖验收场景：快速切换、切换中关闭tab、切换后立即操作、并发读取active状态、多轮一致性
输出：激活命中率、错投次数、状态收敛时间、无效tab拦截次数、$LASTEXITCODE
"""
import sys
import threading
from time import perf_counter, sleep
from typing import List, Dict, Any

from DrissionPage import ChromiumPage
from DrissionPage._pages.chromium_tab import ChromiumTab


class TestMetrics:
    def __init__(self):
        self.activation_hits: int = 0
        self.activation_misses: int = 0
        self.wrong_target_ops: int = 0
        self.state_convergence_times: List[float] = []
        self.invalid_tab_interceptions: int = 0
        self.total_operations: int = 0

    @property
    def activation_hit_rate(self) -> float:
        total = self.activation_hits + self.activation_misses
        return self.activation_hits / total if total > 0 else 1.0

    @property
    def avg_convergence_time(self) -> float:
        return sum(self.state_convergence_times) / len(self.state_convergence_times) if self.state_convergence_times else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'activation_hit_rate': f'{self.activation_hit_rate:.2%}',
            'activation_hits': self.activation_hits,
            'activation_misses': self.activation_misses,
            'wrong_target_operations': self.wrong_target_ops,
            'average_convergence_time_ms': f'{self.avg_convergence_time * 1000:.2f}ms',
            'invalid_tab_interceptions': self.invalid_tab_interceptions,
            'total_operations': self.total_operations
        }


def test_fast_switch(page: ChromiumPage, metrics: TestMetrics, num_tabs: int = 5, iterations: int = 30) -> None:
    """
    测试快速切换 tab
    """
    print(f"\n=== 测试快速切换 tab ({iterations} 次) ===")
    
    tabs: List[ChromiumTab] = []
    for i in range(num_tabs):
        tab = page.new_tab()
        tabs.append(tab)
    
    try:
        for i in range(iterations):
            metrics.total_operations += 1
            target_idx = i % num_tabs
            target_tab = tabs[target_idx]
            
            start_time = perf_counter()
            page.activate_tab(target_tab)
            end_time = perf_counter()
            
            metrics.state_convergence_times.append(end_time - start_time)
            
            latest_tab = page.latest_tab
            if latest_tab.tab_id == target_tab.tab_id:
                metrics.activation_hits += 1
            else:
                metrics.activation_misses += 1
                print(f"  警告: 迭代 {i} - 期望 tab {target_tab.tab_id}, 实际 latest_tab {latest_tab.tab_id}")
            
            if (i + 1) % 20 == 0:
                print(f"  完成 {i + 1}/{iterations} 次切换")
    
    finally:
        for tab in tabs[1:]:
            tab.close()


def test_switch_while_closing(page: ChromiumPage, metrics: TestMetrics) -> None:
    """
    测试切换中关闭 tab
    """
    print("\n=== 测试切换中关闭 tab ===")
    
    tab1 = page.new_tab()
    tab2 = page.new_tab()
    tab3 = page.new_tab()
    
    try:
        for i in range(20):
            metrics.total_operations += 1
            
            page.activate_tab(tab1)
            sleep(0.01)
            
            temp_tab = page.new_tab()
            sleep(0.01)
            
            def close_temp():
                nonlocal temp_tab
                try:
                    temp_tab.close()
                except:
                    pass
            
            close_thread = threading.Thread(target=close_temp)
            close_thread.start()
            
            try:
                page.activate_tab(tab2)
                latest = page.latest_tab
                if latest.tab_id == tab2.tab_id:
                    metrics.activation_hits += 1
                else:
                    metrics.activation_misses += 1
            except RuntimeError as e:
                if "NO_SUCH_TAB" in str(e) or "不存在" in str(e):
                    metrics.invalid_tab_interceptions += 1
                    print(f"  迭代 {i}: 正确拦截了无效 tab 操作")
                else:
                    raise
            
            close_thread.join()
            
            if (i + 1) % 5 == 0:
                print(f"  完成 {i + 1}/20 次切换中关闭测试")
    
    finally:
        try:
            tab3.close()
        except:
            pass
        try:
            tab2.close()
        except:
            pass


def test_operation_immediately_after_switch(page: ChromiumPage, metrics: TestMetrics) -> None:
    """
    测试切换后立即操作
    """
    print("\n=== 测试切换后立即操作 ===")
    
    tabs: List[ChromiumTab] = []
    tab_data: Dict[str, str] = {}
    
    for i in range(3):
        tab = page.new_tab()
        tab_id = tab.tab_id
        test_value = f"tab_{i}_value_{perf_counter()}"
        tab_data[tab_id] = test_value
        
        tab.get("data:text/html,<html><body><div id='test'>initial</div></body></html>")
        tab.run_js(f"document.getElementById('test').innerHTML = '{test_value}';")
        tabs.append(tab)
    
    try:
        for i in range(50):
            metrics.total_operations += 1
            target_idx = i % 3
            target_tab = tabs[target_idx]
            expected_value = tab_data[target_tab.tab_id]
            
            page.activate_tab(target_tab)
            
            try:
                actual_value = target_tab.run_js("return document.getElementById('test').innerHTML;")
                
                latest = page.latest_tab
                if latest.tab_id == target_tab.tab_id:
                    metrics.activation_hits += 1
                else:
                    metrics.activation_misses += 1
                    print(f"  警告: 迭代 {i} - latest_tab 不一致")
                
                if actual_value == expected_value:
                    pass
                else:
                    metrics.wrong_target_ops += 1
                    print(f"  严重: 迭代 {i} - 操作落错 tab! 期望 {expected_value}, 实际 {actual_value}")
            
            except Exception as e:
                print(f"  迭代 {i} 异常: {e}")
            
            if (i + 1) % 10 == 0:
                print(f"  完成 {i + 1}/50 次切换后立即操作测试")
    
    finally:
        for tab in tabs[1:]:
            try:
                tab.close()
            except:
                pass


def test_concurrent_active_read(page: ChromiumPage, metrics: TestMetrics) -> None:
    """
    测试并发读取 active 状态
    """
    print("\n=== 测试并发读取 active 状态 ===")
    
    tabs: List[ChromiumTab] = []
    for i in range(4):
        tab = page.new_tab()
        tabs.append(tab)
    
    results_lock = threading.Lock()
    read_results: List[tuple] = []
    
    def read_active_state(thread_id: int):
        nonlocal read_results
        for _ in range(30):
            try:
                latest = page.latest_tab
                active_id = page.browser._active_tab_id
                with results_lock:
                    read_results.append((thread_id, perf_counter(), latest.tab_id, active_id))
            except:
                pass
    
    def switch_tabs():
        for i in range(20):
            target_idx = i % 4
            page.activate_tab(tabs[target_idx])
            sleep(0.02)
    
    try:
        switch_thread = threading.Thread(target=switch_tabs)
        read_threads = [threading.Thread(target=read_active_state, args=(i,)) for i in range(5)]
        
        switch_thread.start()
        for t in read_threads:
            t.start()
        
        switch_thread.join()
        for t in read_threads:
            t.join()
        
        inconsistencies = 0
        for i in range(1, len(read_results)):
            prev_thread, prev_time, prev_latest, prev_active = read_results[i-1]
            curr_thread, curr_time, curr_latest, curr_active = read_results[i]
            
            if curr_active and curr_latest != curr_active:
                inconsistencies += 1
                print(f"  警告: 并发读取不一致 - latest={curr_latest}, active={curr_active}")
        
        total_reads = len(read_results)
        consistent_reads = total_reads - inconsistencies
        metrics.activation_hits += consistent_reads
        metrics.activation_misses += inconsistencies
        metrics.total_operations += total_reads
        
        print(f"  并发读取总数: {total_reads}, 不一致次数: {inconsistencies}")
    
    finally:
        for tab in tabs[1:]:
            try:
                tab.close()
            except:
                pass


def test_multiple_rounds_consistency(page: ChromiumPage, metrics: TestMetrics) -> None:
    """
    测试多轮一致性
    """
    print("\n=== 测试多轮一致性 ===")
    
    for round_num in range(5):
        print(f"  第 {round_num + 1} 轮测试...")
        
        tabs: List[ChromiumTab] = []
        for i in range(3):
            tab = page.new_tab()
            tabs.append(tab)
        
        try:
            for i in range(20):
                metrics.total_operations += 1
                target_idx = i % 3
                target_tab = tabs[target_idx]
                
                page.activate_tab(target_tab)
                
                latest = page.latest_tab
                if latest.tab_id == target_tab.tab_id:
                    metrics.activation_hits += 1
                else:
                    metrics.activation_misses += 1
        
        finally:
            for tab in tabs[1:]:
                try:
                    tab.close()
                except:
                    pass
        
        print(f"    第 {round_num + 1} 轮完成")


def test_invalid_tab_operations(page: ChromiumPage, metrics: TestMetrics) -> None:
    """
    测试失效 tab 拦截
    """
    print("\n=== 测试失效 tab 拦截 ===")
    
    tab_to_close = page.new_tab()
    closed_tab_id = tab_to_close.tab_id
    
    tab_ref = tab_to_close
    tab_to_close.close()
    
    sleep(0.1)
    
    try:
        is_alive = tab_ref.states.is_alive
        print(f"  tab_ref.states.is_alive = {is_alive}")
        
        if not is_alive:
            metrics.invalid_tab_interceptions += 1
            print("  正确: states.is_alive 通过真实 CDP 操作验证 tab 已失效")
        
        try:
            page.activate_tab(closed_tab_id)
            print("  警告: 激活已关闭的 tab 没有抛出异常")
        except RuntimeError as e:
            metrics.invalid_tab_interceptions += 1
            print(f"  正确: 激活已关闭的 tab 抛出异常: {e}")
    
    except Exception as e:
        print(f"  测试异常: {e}")


def main():
    print("=" * 60)
    print("Chromium tab Active 状态一致性测试")
    print("=" * 60)
    
    metrics = TestMetrics()
    page = None
    exit_code = 0
    
    try:
        print("\n初始化 ChromiumPage...")
        page = ChromiumPage()
        print(f"浏览器启动成功, tab_id: {page.tab_id}")
        
        test_fast_switch(page, metrics, iterations=100)
        
        test_switch_while_closing(page, metrics)
        
        test_operation_immediately_after_switch(page, metrics)
        
        test_concurrent_active_read(page, metrics)
        
        test_multiple_rounds_consistency(page, metrics)
        
        test_invalid_tab_operations(page, metrics)
        
        print("\n" + "=" * 60)
        print("测试结果汇总:")
        print("=" * 60)
        for key, value in metrics.to_dict().items():
            print(f"  {key}: {value}")
        
        if metrics.activation_misses > 0 or metrics.wrong_target_ops > 0:
            exit_code = 1
            print("\n⚠️  发现一致性问题!")
        else:
            print("\n✅ 所有测试通过!")
        
        print(f"\n$LASTEXITCODE = {exit_code}")
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 2
    
    finally:
        if page:
            try:
                page.quit()
            except:
                pass
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
