# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
import sys
from pathlib import Path
from platform import python_version

from click import option, group, pass_context

from .._functions.tools import configs_to_here as ch
from .._configs.chromium_options import ChromiumOptions
from .._pages.chromium_page import ChromiumPage
from .._configs.options_manage import OptionsManager
from .._functions.browser import get_chrome_path
from ..version import __version__


PASS = 'PASS'
FAIL = 'FAIL'
WARN = 'WARN'


@group(invoke_without_command=True)
@option("-p", "--set-browser-path", help="设置浏览器路径")
@option("-u", "--set-user-path", help="设置用户数据路径")
@option("-c", "--configs-to-here", is_flag=True, help="复制默认配置文件到当前路径")
@option("-l", "--launch-browser", default=-1, help="启动浏览器，传入端口号，0表示用配置文件中的值")
@option("-v", "--version", is_flag=True, help="显示版本号")
@pass_context
def main(ctx, set_browser_path, set_user_path, configs_to_here, launch_browser, version):
    if version:
        print(f'DrissionPage {__version__}')
        return

    if ctx.invoked_subcommand is not None:
        return

    if set_browser_path:
        set_paths(browser_path=set_browser_path)

    if set_user_path:
        set_paths(user_data_path=set_user_path)

    if configs_to_here:
        ch()

    if launch_browser >= 0:
        port = f'127.0.0.1:{launch_browser}' if launch_browser else None
        ChromiumPage(port)


def set_paths(browser_path=None, user_data_path=None):
    """快捷的路径设置函数
    :param browser_path: 浏览器可执行文件路径
    :param user_data_path: 用户数据路径
    :return: None
    """
    co = ChromiumOptions()

    if browser_path is not None:
        co.set_browser_path(browser_path)

    if user_data_path is not None:
        co.set_user_data_path(user_data_path)

    co.save()


@main.command(help='环境诊断命令：检查 Python 版本、依赖、配置、浏览器路径')
def doctor():
    results = []

    print('=' * 50)
    print(f'DrissionPage {__version__} 环境诊断报告')
    print('=' * 50)

    results.extend(check_python_version())
    results.extend(check_dependencies())
    results.extend(check_configs())
    results.extend(check_browser_path())

    for category, status, message in results:
        status_str = f'[{status}]'
        print(f'{status_str:8} {category}: {message}')

    print('=' * 50)

    fail_count = sum(1 for _, status, _ in results if status == FAIL)
    warn_count = sum(1 for _, status, _ in results if status == WARN)
    pass_count = sum(1 for _, status, _ in results if status == PASS)

    print(f'汇总: {PASS}: {pass_count}, {WARN}: {warn_count}, {FAIL}: {fail_count}')
    print('=' * 50)

    sys.exit(1 if fail_count > 0 else 0)


def check_python_version():
    required = (3, 6)
    current = sys.version_info[:2]
    version_str = python_version()

    if current >= required:
        return [('Python版本', PASS, f'当前版本: {version_str}')]
    else:
        return [('Python版本', FAIL, f'当前版本: {version_str}, 要求: >= 3.6')]


def check_dependencies():
    deps = [
        ('lxml', 'lxml', 'XML/HTML解析库'),
        ('requests', 'requests', 'HTTP请求库'),
        ('cssselect', 'cssselect', 'CSS选择器'),
        ('DownloadKit', 'DownloadKit', '下载工具'),
        ('websocket', 'websocket', 'WebSocket通信'),
        ('click', 'click', '命令行工具'),
        ('tldextract', 'tldextract', '域名解析'),
        ('psutil', 'psutil', '进程管理'),
    ]

    results = []
    for import_name, pkg_name, description in deps:
        try:
            __import__(import_name)
            results.append(('依赖检查', PASS, f'{pkg_name} ({description})'))
        except (ImportError, ModuleNotFoundError) as e:
            results.append(('依赖检查', FAIL, f'{pkg_name} ({description}) - 未安装: {e}'))
        except Exception as e:
            results.append(('依赖检查', WARN, f'{pkg_name} ({description}) - 导入警告: {e}'))

    return results


def check_configs():
    results = []

    default_ini = Path(__file__).parent.parent / '_configs' / 'configs.ini'
    local_ini = Path('dp_configs.ini')

    if default_ini.exists() and default_ini.is_file():
        try:
            with open(default_ini, 'r', encoding='utf-8'):
                pass
            results.append(('配置检查', PASS, f'默认配置文件: {default_ini}'))
        except (PermissionError, IOError) as e:
            results.append(('配置检查', FAIL, f'默认配置文件无法读取: {default_ini}, 错误: {e}'))
    else:
        results.append(('配置检查', FAIL, f'默认配置文件不存在: {default_ini}'))

    if local_ini.exists():
        if local_ini.is_file():
            try:
                with open(local_ini, 'r', encoding='utf-8'):
                    pass
                try:
                    om = OptionsManager(str(local_ini))
                    if om.file_exists:
                        results.append(('配置检查', PASS, f'本地配置文件: {local_ini.absolute()}'))
                    else:
                        results.append(('配置检查', WARN, f'本地配置文件存在但无法读取'))
                except Exception as e:
                    results.append(('配置检查', FAIL, f'本地配置文件解析失败: {e}'))
            except (PermissionError, IOError) as e:
                results.append(('配置检查', FAIL, f'本地配置文件无法读取: {local_ini.absolute()}, 错误: {e}'))
        else:
            results.append(('配置检查', WARN, f'"dp_configs.ini" 不是文件'))
    else:
        results.append(('配置检查', WARN, f'未找到本地配置文件，将使用默认配置'))

    try:
        om = OptionsManager()
        _ = om.chromium_options
        _ = om.timeouts
        results.append(('配置检查', PASS, '配置解析正常'))
    except Exception as e:
        results.append(('配置检查', FAIL, f'配置解析失败: {e}'))

    return results


def check_browser_path():
    results = []
    from os import access, X_OK

    try:
        co = ChromiumOptions()
        configured_path = co.browser_path

        if configured_path and configured_path.strip() and configured_path != 'chrome':
            configured_path = configured_path.strip()
            p = Path(configured_path)
            try:
                if p.exists():
                    if p.is_file():
                        if access(str(p), X_OK):
                            results.append(('浏览器路径', PASS, f'配置路径: {configured_path}'))
                        else:
                            results.append(('浏览器路径', WARN, f'配置路径存在但无执行权限: {configured_path}'))
                    elif p.is_dir():
                        results.append(('浏览器路径', WARN, f'配置路径是目录，需要指定到具体可执行文件: {configured_path}'))
                    else:
                        results.append(('浏览器路径', WARN, f'配置路径不是常规文件: {configured_path}'))
                else:
                    results.append(('浏览器路径', WARN, f'配置路径不存在: {configured_path}'))
            except (PermissionError, OSError) as e:
                results.append(('浏览器路径', WARN, f'无法访问配置路径: {configured_path}, 错误: {e}'))
        else:
            results.append(('浏览器路径', WARN, f'未配置具体路径，将使用系统默认查找'))

    except Exception as e:
        results.append(('浏览器路径', FAIL, f'读取浏览器配置失败: {e}'))

    try:
        found_path = get_chrome_path(None)
        if found_path:
            found_path = found_path.strip()
            p = Path(found_path)
            try:
                if p.exists():
                    if p.is_file():
                        if access(str(p), X_OK):
                            results.append(('浏览器路径', PASS, f'找到浏览器: {found_path}'))
                        else:
                            results.append(('浏览器路径', WARN, f'找到的浏览器无执行权限: {found_path}'))
                    else:
                        results.append(('浏览器路径', WARN, f'找到的路径不是文件: {found_path}'))
                else:
                    results.append(('浏览器路径', WARN, f'找到的路径不存在: {found_path}'))
            except (PermissionError, OSError) as e:
                results.append(('浏览器路径', WARN, f'无法访问找到的浏览器路径: {found_path}, 错误: {e}'))
        else:
            results.append(('浏览器路径', FAIL, '未找到 Chrome/Chromium 浏览器'))

    except Exception as e:
        results.append(('浏览器路径', FAIL, f'查找浏览器失败: {e}'))

    return results


if __name__ == '__main__':
    main()
