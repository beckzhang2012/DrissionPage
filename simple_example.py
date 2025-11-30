#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DrissionPage 简单使用示例
"""
import sys
import os

# 将当前目录添加到Python路径（如果项目未安装）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from DrissionPage import ChromiumPage

def main():
    """简单的浏览器控制示例"""
    print("🚀 启动浏览器...")
    
    # 创建页面对象
    page = ChromiumPage()
    
    # 访问百度首页
    print("📄 访问百度...")
    page.get('https://www.baidu.com')
    
    # 获取页面标题
    print(f"📋 页面标题: {page.title}")
    
    # 查找搜索框并输入内容
    print("⌨️  输入搜索关键词...")
    try:
        search_box = page.ele('#kw', timeout=5)
        if search_box:
            search_box.input('DrissionPage')
            print("✅ 输入成功")
        else:
            print("❌ 未找到搜索框")
            return
    except Exception as e:
        print(f"❌ 输入失败: {e}")
        return
    
    # 查找搜索按钮并点击
    print("🖱️  点击搜索按钮...")
    try:
        search_btn = page.ele('#su', timeout=5)
        if search_btn:
            # 等待按钮可点击
            search_btn.wait.clickable(timeout=3)
            search_btn.click()
            print("✅ 点击成功")
            
            # 等待页面加载
            page.wait(2)
            print(f"📋 搜索结果页面标题: {page.title}")
        else:
            print("❌ 未找到搜索按钮")
    except Exception as e:
        print(f"❌ 点击失败: {e}")
        print("💡 提示：这可能是由于页面加载速度或元素不可见导致的")
    
    print("\n✨ 示例运行完成！")
    print("💡 提示：浏览器窗口将保持打开，您可以手动关闭或按 Ctrl+C 退出程序")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

