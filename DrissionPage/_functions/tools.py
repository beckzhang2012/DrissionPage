# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Copyright: (c) 2024 by g1879, Inc. All Rights Reserved.
@License  : BSD 3-Clause.
"""
from pathlib import Path
from platform import system
from shutil import rmtree
from tempfile import gettempdir, TemporaryDirectory
from threading import Lock
from time import perf_counter, sleep

from .._configs.options_manage import OptionsManager
from .._elements.none_element import NoneElement
from ..errors import (ContextLostError, ElementLostError, CDPError, PageDisconnectedError, NoRectError,
                      AlertExistsError, WrongURLError, StorageError, CookieFormatError, JavaScriptError)


class PortFinder(object):
    used_port = {}
    lock = Lock()

    def __init__(self, path=None):
        """
        :param path: 临时文件保存路径，为None时使用系统临时文件夹
        """
        tmp = Path(path) if path else Path(gettempdir()) / 'DrissionPage'
        self.tmp_dir = tmp / 'UserTempFolder'
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        if not PortFinder.used_port:
            clean_folder(self.tmp_dir)

    def get_port(self, scope=None):
        """查找一个可用端口
        :param scope: 指定端口范围，不含最后的数字，为None则使用[9600-19600)
        :return: 可以使用的端口和用户文件夹路径组成的元组
        """
        with PortFinder.lock:
            if scope in (True, None):
                scope = (9600, 19600)
            for i in range(scope[0], scope[1]):
                if i in PortFinder.used_port:
                    continue
                elif port_is_using('127.0.0.1', i):
                    PortFinder.used_port[i] = None
                    continue
                path = TemporaryDirectory(dir=self.tmp_dir).name
                PortFinder.used_port[i] = path
                return i, path

            for i in range(scope[0], scope[1]):
                if port_is_using('127.0.0.1', i):
                    continue
                rmtree(PortFinder.used_port[i], ignore_errors=True)
                return i, TemporaryDirectory(dir=self.tmp_dir).name

        raise OSError('未找到可用端口。')


def port_is_using(ip, port):
    """检查端口是否被占用
    :param ip: 浏览器地址
    :param port: 浏览器端口
    :return: bool
    """
    from socket import socket, AF_INET, SOCK_STREAM
    s = socket(AF_INET, SOCK_STREAM)
    s.settimeout(.1)
    result = s.connect_ex((ip, int(port)))
    s.close()
    return result == 0


def clean_folder(folder_path, ignore=None):
    """清空一个文件夹，除了ignore里的文件和文件夹
    :param folder_path: 要清空的文件夹路径
    :param ignore: 忽略列表
    :return: None
    """
    ignore = [] if not ignore else ignore
    p = Path(folder_path)

    for f in p.iterdir():
        if f.name not in ignore:
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                rmtree(f, True)


def show_or_hide_browser(page, hide=True):
    """执行显示或隐藏浏览器窗口
    :param page: ChromePage对象
    :param hide: 是否隐藏
    :return: None
    """
    if not page.address.startswith(('127.0.0.1', 'localhost')):
        return

    if system().lower() != 'windows':
        raise OSError('该方法只能在Windows系统使用。')

    try:
        from win32gui import ShowWindow
        from win32con import SW_HIDE, SW_SHOW
    except ImportError:
        raise ImportError('请先安装：pip install pypiwin32')

    pid = page._page.process_id
    if not pid:
        return None
    hds = get_hwnds_from_pid(pid, page.title)
    sw = SW_HIDE if hide else SW_SHOW
    for hd in hds:
        ShowWindow(hd, sw)


def get_browser_progress_id(progress, address):
    """获取浏览器进程id
    :param progress: 已知的进程对象，没有时传入None
    :param address: 浏览器管理地址，含端口
    :return: 进程id或None
    """
    if progress:
        return progress.pid

    from os import popen
    port = address.split(':')[-1]
    txt = ''
    progresses = popen(f'netstat -nao | findstr :{port}').read().split('\n')
    for progress in progresses:
        if 'LISTENING' in progress:
            txt = progress
            break
    if not txt:
        return None

    return txt.split(' ')[-1]


def get_hwnds_from_pid(pid, title):
    """通过PID查询句柄ID
    :param pid: 进程id
    :param title: 窗口标题
    :return: 进程句柄组成的列表
    """
    try:
        from win32gui import IsWindow, GetWindowText, EnumWindows
        from win32process import GetWindowThreadProcessId
    except ImportError:
        raise ImportError('请先安装win32gui，pip install pypiwin32')

    def callback(hwnd, hds):
        if IsWindow(hwnd) and title in GetWindowText(hwnd):
            _, found_pid = GetWindowThreadProcessId(hwnd)
            if str(found_pid) == str(pid):
                hds.append(hwnd)
            return True

    hwnds = []
    EnumWindows(callback, hwnds)
    return hwnds


def wait_until(function, kwargs=None, timeout=10):
    """等待传入的方法返回值不为假
    :param function: 要执行的方法
    :param kwargs: 方法参数
    :param timeout: 超时时间（秒）
    :return: 执行结果，超时抛出TimeoutError
    """
    if kwargs is None:
        kwargs = {}
    end_time = perf_counter() + timeout
    while perf_counter() < end_time:
        value = function(**kwargs)
        if value:
            return value
        sleep(.01)
    raise TimeoutError


def configs_to_here(save_name=None):
    """把默认ini文件复制到当前目录
    :param save_name: 指定文件名，为None则命名为'dp_configs.ini'
    :return: None
    """
    om = OptionsManager('default')
    save_name = f'{save_name}.ini' if save_name is not None else 'dp_configs.ini'
    om.save(save_name)


def raise_error(result, ignore=None):
    """抛出error对应报错
    :param result: 包含error的dict
    :param ignore: 要忽略的错误
    :return: None
    """
    error = result['error']
    if error in ('Cannot find context with specified id', 'Inspected target navigated or closed',
                 'No frame with given id found'):
        r = ContextLostError()
    elif error in ('Could not find node with given id', 'Could not find object with given id',
                   'No node with given id found', 'Node with given id does not belong to the document',
                   'No node found for given backend id'):
        r = ElementLostError()
    elif error in ('connection disconnected', 'No target with given id found'):
        r = PageDisconnectedError()
    elif error == 'alert exists.':
        r = AlertExistsError()
    elif error in ('Node does not have a layout object', 'Could not compute box model.'):
        r = NoRectError()
    elif error == 'Cannot navigate to invalid URL':
        r = WrongURLError(f'无效的url：{result["args"]["url"]}。也许要加上"http://"？')
    elif error == 'Frame corresponds to an opaque origin and its storage key cannot be serialized':
        r = StorageError()
    elif error == 'Sanitizing cookie failed':
        r = CookieFormatError(f'cookie格式不正确：{result["args"]}')
    elif error == 'Given expression does not evaluate to a function':
        r = JavaScriptError(f'传入的js无法解析成函数：\n{result["args"]["functionDeclaration"]}')
    elif error.endswith("' wasn't found"):
        r = RuntimeError(f'你的浏览器可能太旧。\n方法：{result["method"]}\n参数：{result["args"]}')
    elif result['type'] in ('call_method_error', 'timeout'):
        from DrissionPage import __version__
        txt = f'\n错误：{result["error"]}\n方法：{result["method"]}\n参数：{result["args"]}\n' \
              f'版本：{__version__}\n出现这个错误可能意味着程序有bug，请把错误信息和重现方法' \
              '告知作者，谢谢。\n报告网站：https://gitee.com/g1879/DrissionPage/issues'
        r = TimeoutError(txt) if result['type'] == 'timeout' else CDPError(txt)
    else:
        r = RuntimeError(result)

    if not ignore or not isinstance(r, ignore):
        raise r


class ElementsList(list):

    def displayed(self, get_all=False):
        """返回显示的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_displayed', get_all=get_all)

    def hidden(self, get_all=False):
        """返回不显示的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_displayed', True, get_all=get_all)

    def checked(self, get_all=False):
        """返回被选中的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_checked', get_all=get_all)

    def not_checked(self, get_all=False):
        """返回没被选中的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_checked', True, get_all=get_all)

    def selected(self, get_all=False):
        """返回被选中的列表元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_selected', get_all=get_all)

    def not_selected(self, get_all=False):
        """返回没被选中的列表元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_selected', True, get_all=get_all)

    def enabled(self, get_all=False):
        """返回有效的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_enabled', get_all=get_all)

    def disabled(self, get_all=False):
        """返回无效的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_enabled', True, get_all=get_all)

    def clickable(self, get_all=False):
        """返回可被点击的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_clickable', get_all=get_all)

    def not_clickable(self, get_all=False):
        """返回不可被点击的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('is_clickable', True, get_all=get_all)

    def have_rect(self, get_all=False):
        """返回有大小和位置的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('has_rect', get_all=get_all)

    def no_rect(self, get_all=False):
        """返回没有大小和位置的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        return self._any_state('has_rect', True, get_all=get_all)

    def have_text(self, get_all=False):
        """返回包含文本的元素，默认返回第一个
        :param get_all: 是否返回所有筛选到的元素
        :return: 元素或元素组成的列表
        """
        if get_all:
            r = ElementsList()
            for i in self:
                if i.raw_text:
                    r.append(i)
            return r

        for i in self:
            if i.raw_text:
                return i

        return NoneElement()

    def style(self, name, value, get_all=False):
        """返回拥有某个style值的元素，默认返回第一个
        :param name: 属性名称
        :param value: 属性值
        :param get_all: 是否返回所有筛选到的元素
        :return: 筛选结果
        """
        return self._get_attr(name, value, 'style', get_all)

    def property(self, name, value, get_all=False):
        """返回拥有某个property值的元素，默认返回第一个
        :param name: 属性名称
        :param value: 属性值
        :param get_all: 是否返回所有筛选到的元素
        :return: 筛选结果
        """
        return self._get_attr(name, value, 'property', get_all)

    def attr(self, name, value, get_all=False):
        """返回拥有某个attribute值的元素，默认返回第一个
        :param name: 属性名称
        :param value: 属性值
        :param get_all: 是否返回所有筛选到的元素
        :return: 筛选结果
        """
        return self._get_attr(name, value, 'attr', get_all)

    def filter(self, get_all=False, displayed=None, checked=None, selected=None, enabled=None, clickable=None,
               have_rect=None, have_text=None):
        """与关系筛选元素
        :param get_all: 是否返回所有筛选到的元素
        :param displayed: 是否显示，bool，None为忽略该项
        :param checked: 是否被选中，bool，None为忽略该项
        :param selected: 是否被选择，bool，None为忽略该项
        :param enabled: 是否可用，bool，None为忽略该项
        :param clickable: 是否可点击，bool，None为忽略该项
        :param have_rect: 是否拥有大小和位置，bool，None为忽略该项
        :param have_text: 是否含有文本，bool，None为忽略该项
        :return:
        """
        if get_all:
            r = ElementsList()
            for i in self:
                if ((displayed is not None and (displayed is True and i.states.is_displayed) or (
                        displayed is False and not i.states.is_displayed))
                        and (checked is not None and (checked is True and i.states.is_checked) or (
                                checked is False and not i.states.is_checked))
                        and (selected is not None and (selected is True and i.states.is_selected) or (
                                selected is False and not i.states.is_selected))
                        and (enabled is not None and (enabled is True and i.states.is_enabled) or (
                                enabled is False and not i.states.is_enabled))
                        and (clickable is not None and (clickable is True and i.states.is_clickable) or (
                                clickable is False and not i.states.is_clickable))
                        and (have_rect is not None and (have_rect is True and i.states.has_rect) or (
                                have_rect is False and not i.states.has_rect))
                        and (have_text is not None and (have_text is True and i.raw_text) or (
                                have_text is False and not i.raw_text))):
                    r.append(i)
            return r

        for i in self:
            if ((displayed is not None and (displayed is True and i.states.is_displayed) or (
                    displayed is False and not i.states.is_displayed))
                    and (checked is not None and (checked is True and i.states.is_checked) or (
                            checked is False and not i.states.is_checked))
                    and (selected is not None and (selected is True and i.states.is_selected) or (
                            selected is False and not i.states.is_selected))
                    and (enabled is not None and (enabled is True and i.states.is_enabled) or (
                            enabled is False and not i.states.is_enabled))
                    and (clickable is not None and (clickable is True and i.states.is_clickable) or (
                            clickable is False and not i.states.is_clickable))
                    and (have_rect is not None and (have_rect is True and i.states.has_rect) or (
                            have_rect is False and not i.states.has_rect))
                    and (have_text is not None and (have_text is True and i.raw_text) or (
                            have_text is False and not i.raw_text))):
                return i

        return NoneElement()

    def _get_attr(self, name, value, method, get_all=False):
        """返回通过某个方法可获得某个值的元素，默认返回第一个
        :param name: 属性名称
        :param value: 属性值
        :param method: 方法名称
        :param get_all: 是否返回所有筛选到的元素
        :return: 筛选结果
        """
        if get_all:
            r = ElementsList()
            for i in self:
                if getattr(i, method)(name) == value:
                    r.append(i)
            return r

        for i in self:
            if getattr(i, method)(name) == value:
                return i

        return NoneElement()

    def _any_state(self, name, is_not=False, get_all=False):
        """
        :param name: 状态名称
        :param is_not: 是否选择否定的
        :return: 选中的列表
        """
        if get_all:
            r = ElementsList()
            if is_not:
                for i in self:
                    if not getattr(i.states, name):
                        r.append(i)
            else:
                for i in self:
                    if getattr(i.states, name):
                        r.append(i)
            return r

        if is_not:
            for i in self:
                if not getattr(i.states, name):
                    return i
        else:
            for i in self:
                if getattr(i.states, name):
                    return i

        return NoneElement()


def get_eles(locators, owner, any_one=False, first_ele=True, timeout=10):
    """传入多个定位符，获取多个ele
    :param locators: 定位符组成的列表
    :param owner: 页面或元素对象
    :param any_one: 是否找到任何一个即返回
    :param first_ele: 每个定位符是否只获取第一个元素
    :param timeout: 超时时间（秒）
    :return: 多个定位符组成的dict
    """
    res = {loc: False for loc in locators}
    end_time = perf_counter() + timeout
    while perf_counter() <= end_time:
        for loc in locators:
            if res[loc] is not False:
                continue
            ele = owner.ele(loc, timeout=0) if first_ele else owner.eles(loc, timeout=0)
            if ele:
                res[loc] = ele
                if any_one:
                    return res
        if False not in res.values():
            break

    return res
