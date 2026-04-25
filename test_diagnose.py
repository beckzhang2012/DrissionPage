# -*- coding:utf-8 -*-
"""
诊断测试：定位 tab 切换卡住的问题
"""
import sys
from time import perf_counter, sleep

from DrissionPage import ChromiumPage
from DrissionPage._functions.settings import Settings


def main():
    print("=" * 60)
    print("诊断测试：tab 切换问题定位")
    print("=" * 60)
    
    print(f"\n默认 cdp_timeout: {Settings.cdp_timeout}")
    
    page = None
    exit_code = 0
    
    try:
        print("\n[1/5] 初始化 ChromiumPage...")
        start = perf_counter()
        page = ChromiumPage()
        print(f"  浏览器启动成功, 耗时: {perf_counter() - start:.2f}s")
        print(f"  初始 tab_id: {page.tab_id}")
        
        print("\n[2/5] 检查 browser._active_tab_id...")
        print(f"  browser._active_tab_id = {page.browser._active_tab_id}")
        
        print("\n[3/5] 检查 _all_drivers...")
        print(f"  _all_drivers keys: {list(page.browser._all_drivers.keys())}")
        
        print("\n[4/5] 创建 tab1...")
        start = perf_counter()
        tab1 = page.new_tab()
        print(f"  tab1 创建成功, tab_id: {tab1.tab_id}, 耗时: {perf_counter() - start:.2f}s")
        print(f"  browser._active_tab_id = {page.browser._active_tab_id}")
        print(f"  _all_drivers keys: {list(page.browser._all_drivers.keys())}")
        
        print("\n[5/5] 测试 activate_tab 到初始 tab...")
        initial_tab_id = page.tab_id
        print(f"  目标 tab_id: {initial_tab_id}")
        
        start = perf_counter()
        try:
            print(f"  调用 activate_tab (带 5 秒超时)...")
            page.activate_tab(initial_tab_id)
            print(f"  activate_tab 成功, 耗时: {perf_counter() - start:.2f}s")
        except Exception as e:
            print(f"  activate_tab 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1
        
        print("\n检查 latest_tab...")
        try:
            start = perf_counter()
            latest = page.latest_tab
            print(f"  latest_tab 获取成功, tab_id: {latest.tab_id}, 耗时: {perf_counter() - start:.2f}s")
        except Exception as e:
            print(f"  获取 latest_tab 失败: {type(e).__name__}: {e}")
            exit_code = 1
        
        print("\n" + "=" * 60)
        print("诊断测试完成")
        print("=" * 60)
        print(f"\n$LASTEXITCODE = {exit_code}")
    
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        exit_code = 2
    
    finally:
        if page:
            try:
                print("\n关闭浏览器...")
                page.quit()
                print("浏览器已关闭")
            except Exception as e:
                print(f"关闭浏览器失败: {e}")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
