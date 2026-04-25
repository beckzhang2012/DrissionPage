# -*- coding:utf-8 -*-
"""
诊断测试：定位 latest_tab 卡住的问题
"""
import sys
from time import perf_counter, sleep

from DrissionPage import ChromiumPage
from DrissionPage._functions.settings import Settings
from DrissionPage._base.chromium import ChromiumTab


def main():
    print("=" * 60)
    print("诊断测试：定位 latest_tab 卡住的问题")
    print("=" * 60)
    
    print(f"\n默认 cdp_timeout: {Settings.cdp_timeout}")
    print(f"singleton_tab_obj: {Settings.singleton_tab_obj}")
    
    page = None
    exit_code = 0
    
    try:
        print("\n[1/6] 初始化 ChromiumPage...")
        start = perf_counter()
        page = ChromiumPage()
        print(f"  浏览器启动成功, 耗时: {perf_counter() - start:.2f}s")
        print(f"  初始 tab_id: {page.tab_id}")
        
        print("\n[2/6] 检查 browser 属性...")
        print(f"  browser._active_tab_id = {page.browser._active_tab_id}")
        print(f"  browser._all_drivers keys = {list(page.browser._all_drivers.keys())}")
        
        print("\n[3/6] 测试直接访问 latest_tab...")
        try:
            start = perf_counter()
            print(f"  调用 page.latest_tab (带 10 秒超时)...")
            latest = page.latest_tab
            print(f"  latest_tab 获取成功, tab_id: {latest.tab_id}, 耗时: {perf_counter() - start:.2f}s")
        except Exception as e:
            print(f"  获取 latest_tab 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1
        
        print("\n[4/6] 创建 tab1...")
        start = perf_counter()
        tab1 = page.new_tab()
        print(f"  tab1 创建成功, tab_id: {tab1.tab_id}, 耗时: {perf_counter() - start:.2f}s")
        print(f"  browser._active_tab_id = {page.browser._active_tab_id}")
        print(f"  browser._all_drivers keys = {list(page.browser._all_drivers.keys())}")
        
        print("\n[5/6] 测试 activate_tab 到初始 tab...")
        initial_tab_id = page.tab_id
        print(f"  初始 tab_id: {initial_tab_id}")
        print(f"  目标 tab_id: {initial_tab_id}")
        
        print(f"  检查目标 tab_id 是否在 _all_drivers 中: {initial_tab_id in page.browser._all_drivers}")
        
        try:
            start = perf_counter()
            print(f"  调用 activate_tab (带 5 秒超时)...")
            page.activate_tab(initial_tab_id)
            print(f"  activate_tab 成功, 耗时: {perf_counter() - start:.2f}s")
            print(f"  browser._active_tab_id = {page.browser._active_tab_id}")
        except Exception as e:
            print(f"  activate_tab 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1
        
        print("\n[6/6] 测试 latest_tab 详细路径...")
        print(f"  browser._active_tab_id = {page.browser._active_tab_id}")
        print(f"  browser._active_tab_id in _all_drivers = {page.browser._active_tab_id in page.browser._all_drivers}")
        
        try:
            print(f"  直接调用 browser._get_tab (as_id=True)...")
            start = perf_counter()
            tab_id = page.browser._get_tab(id_or_num=page.browser._active_tab_id, as_id=True)
            print(f"  _get_tab (as_id=True) 成功, tab_id: {tab_id}, 耗时: {perf_counter() - start:.2f}s")
        except Exception as e:
            print(f"  _get_tab (as_id=True) 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1
        
        try:
            print(f"  直接调用 browser._get_tab (as_id=False, mix=True)...")
            start = perf_counter()
            tab_obj = page.browser._get_tab(id_or_num=page.browser._active_tab_id, as_id=False, mix=True)
            print(f"  _get_tab (as_id=False) 成功, tab_id: {tab_obj.tab_id}, 耗时: {perf_counter() - start:.2f}s")
        except Exception as e:
            print(f"  _get_tab (as_id=False) 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1
        
        try:
            print(f"  调用 page.latest_tab (最后测试)...")
            start = perf_counter()
            latest = page.latest_tab
            print(f"  latest_tab 获取成功, tab_id: {latest.tab_id}, 耗时: {perf_counter() - start:.2f}s")
        except Exception as e:
            print(f"  获取 latest_tab 失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            exit_code = 1
        
        print("\n" + "=" * 60)
        print("诊断测试完成")
        print("=" * 60)
        print(f"\n$LASTEXITCODE = {exit_code}")
    
    except Exception as e:
        print(f"\n测试失败: {e}")
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
