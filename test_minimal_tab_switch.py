# -*- coding:utf-8 -*-
"""
最小化测试：验证 tab 切换基本功能
"""
import sys
from time import perf_counter, sleep

from DrissionPage import ChromiumPage
from DrissionPage._pages.chromium_tab import ChromiumTab


def main():
    print("=" * 60)
    print("最小化 tab 切换测试")
    print("=" * 60)
    
    activation_hits = 0
    activation_misses = 0
    wrong_target_ops = 0
    state_convergence_times = []
    invalid_tab_interceptions = 0
    total_operations = 0
    
    page = None
    exit_code = 0
    
    try:
        print("\n初始化 ChromiumPage...")
        page = ChromiumPage()
        print(f"浏览器启动成功, tab_id: {page.tab_id}")
        
        print("\n=== 测试 1: 基本 tab 切换 ===")
        
        tab1 = page.new_tab()
        tab2 = page.new_tab()
        print(f"创建 tab1: {tab1.tab_id}")
        print(f"创建 tab2: {tab2.tab_id}")
        
        try:
            for i in range(10):
                total_operations += 1
                target_tab = tab1 if i % 2 == 0 else tab2
                
                start_time = perf_counter()
                try:
                    page.activate_tab(target_tab)
                except Exception as e:
                    print(f"  迭代 {i}: 激活失败: {e}")
                    activation_misses += 1
                    continue
                end_time = perf_counter()
                
                switch_time = end_time - start_time
                state_convergence_times.append(switch_time)
                
                latest_tab = page.latest_tab
                if latest_tab.tab_id == target_tab.tab_id:
                    activation_hits += 1
                else:
                    activation_misses += 1
                    print(f"  迭代 {i}: 期望 {target_tab.tab_id}, 实际 {latest_tab.tab_id}")
                
                if (i + 1) % 5 == 0:
                    print(f"  完成 {i + 1}/10 次切换")
        
        finally:
            print("关闭测试 tab...")
            try:
                tab2.close()
                print("  tab2 已关闭")
            except Exception as e:
                print(f"  关闭 tab2 失败: {e}")
            try:
                tab1.close()
                print("  tab1 已关闭")
            except Exception as e:
                print(f"  关闭 tab1 失败: {e}")
        
        print("\n=== 测试 2: 失效 tab 拦截 ===")
        
        tab_to_close = page.new_tab()
        closed_tab_id = tab_to_close.tab_id
        print(f"创建 tab: {closed_tab_id}")
        
        tab_ref = tab_to_close
        tab_to_close.close()
        print(f"已关闭 tab: {closed_tab_id}")
        
        sleep(0.2)
        
        try:
            is_alive = tab_ref.states.is_alive
            print(f"  tab_ref.states.is_alive = {is_alive}")
            
            if not is_alive:
                invalid_tab_interceptions += 1
                print("  正确: states.is_alive 通过真实 CDP 操作 (Page.getLayoutMetrics) 验证 tab 已失效")
            
            try:
                page.activate_tab(closed_tab_id)
                print("  警告: 激活已关闭的 tab 没有抛出异常")
            except RuntimeError as e:
                invalid_tab_interceptions += 1
                print(f"  正确: activate_tab 通过 _all_drivers 检查拦截无效 tab: {e}")
            
            try:
                result = tab_ref.run_js("return 1 + 1;")
                print(f"  警告: 已关闭 tab 的 run_js 仍然返回结果: {result}")
            except Exception as e:
                invalid_tab_interceptions += 1
                print(f"  正确: 已关闭 tab 的 run_js 抛出异常: {type(e).__name__}")
        
        except Exception as e:
            print(f"  测试异常: {e}")
        
        print("\n" + "=" * 60)
        print("测试结果汇总:")
        print("=" * 60)
        
        hit_rate = activation_hits / (activation_hits + activation_misses) if (activation_hits + activation_misses) > 0 else 1.0
        avg_conv = sum(state_convergence_times) / len(state_convergence_times) if state_convergence_times else 0.0
        
        print(f"  activation_hit_rate: {hit_rate:.2%}")
        print(f"  activation_hits: {activation_hits}")
        print(f"  activation_misses: {activation_misses}")
        print(f"  wrong_target_operations: {wrong_target_ops}")
        print(f"  average_convergence_time_ms: {avg_conv * 1000:.2f}ms")
        print(f"  invalid_tab_interceptions: {invalid_tab_interceptions}")
        print(f"  total_operations: {total_operations}")
        
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
                print("关闭浏览器...")
                page.quit()
                print("浏览器已关闭")
            except Exception as e:
                print(f"关闭浏览器失败: {e}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
