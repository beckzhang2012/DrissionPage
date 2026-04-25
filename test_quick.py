# -*- coding:utf-8 -*-
"""
快速验证测试：核心功能验证
"""
import sys
from time import perf_counter, sleep
from typing import List

from DrissionPage import ChromiumPage
from DrissionPage._pages.chromium_tab import ChromiumTab


def main():
    print("=" * 60)
    print("快速验证测试")
    print("=" * 60)
    
    activation_hits = 0
    activation_misses = 0
    wrong_target_ops = 0
    convergence_times: List[float] = []
    invalid_interceptions = 0
    total_ops = 0
    
    page = None
    exit_code = 0
    
    try:
        print("\n初始化 ChromiumPage...")
        page = ChromiumPage()
        print(f"浏览器启动成功, tab_id: {page.tab_id}")
        
        print("\n=== 测试1: 快速切换 tab ===")
        tabs: List[ChromiumTab] = []
        for i in range(3):
            tab = page.new_tab()
            tabs.append(tab)
        
        try:
            for i in range(20):
                total_ops += 1
                target_idx = i % 3
                target_tab = tabs[target_idx]
                
                start = perf_counter()
                page.activate_tab(target_tab)
                end = perf_counter()
                convergence_times.append(end - start)
                
                latest = page.latest_tab
                if latest.tab_id == target_tab.tab_id:
                    activation_hits += 1
                else:
                    activation_misses += 1
                    print(f"  警告: 迭代 {i} - 期望 {target_tab.tab_id}, 实际 {latest.tab_id}")
                
                if (i + 1) % 5 == 0:
                    print(f"  完成 {i + 1}/20 次切换")
        finally:
            for tab in tabs[1:]:
                try:
                    tab.close()
                except:
                    pass
        
        print("\n=== 测试2: 切换后立即操作 ===")
        tabs2: List[ChromiumTab] = []
        tab_data = {}
        
        for i in range(3):
            tab = page.new_tab()
            test_val = f"tab_{i}_val"
            tab_data[tab.tab_id] = test_val
            tab.get("data:text/html,<html><body><div id='test'>initial</div></body></html>")
            tab.run_js(f"document.getElementById('test').innerHTML = '{test_val}';")
            tabs2.append(tab)
        
        try:
            for i in range(10):
                total_ops += 1
                target_idx = i % 3
                target_tab = tabs2[target_idx]
                expected = tab_data[target_tab.tab_id]
                
                page.activate_tab(target_tab)
                
                actual = target_tab.run_js("return document.getElementById('test').innerHTML;")
                latest = page.latest_tab
                
                if latest.tab_id == target_tab.tab_id:
                    activation_hits += 1
                else:
                    activation_misses += 1
                    print(f"  警告: 迭代 {i} - latest_tab 不一致")
                
                if actual != expected:
                    wrong_target_ops += 1
                    print(f"  严重: 迭代 {i} - 操作落错 tab! 期望 {expected}, 实际 {actual}")
                
                if (i + 1) % 5 == 0:
                    print(f"  完成 {i + 1}/10 次操作")
        finally:
            for tab in tabs2[1:]:
                try:
                    tab.close()
                except:
                    pass
        
        print("\n=== 测试3: 失效 tab 拦截 ===")
        tab_to_close = page.new_tab()
        closed_id = tab_to_close.tab_id
        tab_ref = tab_to_close
        tab_to_close.close()
        sleep(0.1)
        
        try:
            is_alive = tab_ref.states.is_alive
            print(f"  tab_ref.states.is_alive = {is_alive}")
            
            if not is_alive:
                invalid_interceptions += 1
                print("  正确: states.is_alive 通过真实 CDP 操作 (Page.getLayoutMetrics) 验证 tab 已失效")
            
            try:
                page.activate_tab(closed_id)
                print("  警告: 激活已关闭的 tab 没有抛出异常")
            except RuntimeError as e:
                invalid_interceptions += 1
                print(f"  正确: activate_tab 通过 _all_drivers 检查拦截无效 tab: {e}")
        
        except Exception as e:
            print(f"  测试异常: {e}")
        
        print("\n" + "=" * 60)
        print("测试结果汇总:")
        print("=" * 60)
        
        hit_rate = activation_hits / (activation_hits + activation_misses) if (activation_hits + activation_misses) > 0 else 1.0
        avg_conv = sum(convergence_times) / len(convergence_times) if convergence_times else 0.0
        
        print(f"  activation_hit_rate: {hit_rate:.2%}")
        print(f"  activation_hits: {activation_hits}")
        print(f"  activation_misses: {activation_misses}")
        print(f"  wrong_target_operations: {wrong_target_ops}")
        print(f"  average_convergence_time_ms: {avg_conv * 1000:.2f}ms")
        print(f"  invalid_tab_interceptions: {invalid_interceptions}")
        print(f"  total_operations: {total_ops}")
        
        if activation_misses > 0 or wrong_target_ops > 0:
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
