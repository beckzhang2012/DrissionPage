# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Copyright: (c) 2024 by g1879, Inc. All Rights Reserved.
@License  : BSD 3-Clause.
"""
from time import perf_counter

from .._elements.none_element import NoneElement


class ElementsList(list):
    def __init__(self, page=None):
        super().__init__()
        self._page = page
        self._filter = None
        self._filter_one = None
        self._getter = None

    @property
    def filter(self):
        if self._filter is None:
            self._filter = Filter(self)
        return self._filter

    @property
    def filter_one(self):
        if self._filter_one is None:
            self._filter_one = FilterOne(self)
        return self._filter_one

    @property
    def get(self):
        if self._getter is None:
            self._getter = Getter(self)
        return self._getter

    def search(self, get_all=False, displayed=None, checked=None, selected=None, enabled=None, clickable=None,
               have_rect=None, have_text=None):
        """或关系筛选元素
        :param get_all: 是否返回所有筛选到的元素
        :param displayed: 是否显示，bool，None为忽略该项
        :param checked: 是否被选中，bool，None为忽略该项
        :param selected: 是否被选择，bool，None为忽略该项
        :param enabled: 是否可用，bool，None为忽略该项
        :param clickable: 是否可点击，bool，None为忽略该项
        :param have_rect: 是否拥有大小和位置，bool，None为忽略该项
        :param have_text: 是否含有文本，bool，None为忽略该项
        :return: 筛选结果
        """
        if get_all:
            r = ElementsList()
            for i in self:
                if ((displayed is not None and (displayed is True and i.states.is_displayed) or (
                        displayed is False and not i.states.is_displayed))
                        or (checked is not None and (checked is True and i.states.is_checked) or (
                                checked is False and not i.states.is_checked))
                        or (selected is not None and (selected is True and i.states.is_selected) or (
                                selected is False and not i.states.is_selected))
                        or (enabled is not None and (enabled is True and i.states.is_enabled) or (
                                enabled is False and not i.states.is_enabled))
                        or (clickable is not None and (clickable is True and i.states.is_clickable) or (
                                clickable is False and not i.states.is_clickable))
                        or (have_rect is not None and (have_rect is True and i.states.has_rect) or (
                                have_rect is False and not i.states.has_rect))
                        or (have_text is not None and (have_text is True and i.raw_text) or (
                                have_text is False and not i.raw_text))):
                    r.append(i)
            return r

        for i in self:
            if ((displayed is not None and (displayed is True and i.states.is_displayed) or (
                    displayed is False and not i.states.is_displayed))
                    or (checked is not None and (checked is True and i.states.is_checked) or (
                            checked is False and not i.states.is_checked))
                    or (selected is not None and (selected is True and i.states.is_selected) or (
                            selected is False and not i.states.is_selected))
                    or (enabled is not None and (enabled is True and i.states.is_enabled) or (
                            enabled is False and not i.states.is_enabled))
                    or (clickable is not None and (clickable is True and i.states.is_clickable) or (
                            clickable is False and not i.states.is_clickable))
                    or (have_rect is not None and (have_rect is True and i.states.has_rect) or (
                            have_rect is False and not i.states.has_rect))
                    or (have_text is not None and (have_text is True and i.raw_text) or (
                            have_text is False and not i.raw_text))):
                return i

        return NoneElement(self._page, method='filter()', args={'get_all': get_all, 'displayed': displayed,
                                                                'checked': checked, 'selected': selected,
                                                                'enabled': enabled, 'clickable': clickable,
                                                                'have_rect': have_rect, 'have_text': have_text})


class BaseFilter(object):
    def __init__(self, _list):
        self._list = _list

    def displayed(self):
        """返回显示的元素"""
        return self._any_state('is_displayed')

    def hidden(self):
        """返回不显示的元素"""
        return self._any_state('is_displayed', True)

    def checked(self):
        """返回被选中的元素"""
        return self._any_state('is_checked')

    def not_checked(self):
        """返回没被选中的元素"""
        return self._any_state('is_checked', True)

    def selected(self):
        """返回被选中的列表元素"""
        return self._any_state('is_selected')

    def not_selected(self):
        """返回没被选中的列表元素"""
        return self._any_state('is_selected', True)

    def enabled(self):
        """返回有效的元素"""
        return self._any_state('is_enabled')

    def disabled(self):
        """返回无效的元素"""
        return self._any_state('is_enabled', True)

    def clickable(self):
        """返回可被点击的元素"""
        return self._any_state('is_clickable')

    def not_clickable(self):
        """返回不可被点击的元素"""
        return self._any_state('is_clickable', True)

    def have_rect(self):
        """返回有大小和位置的元素"""
        return self._any_state('has_rect')

    def no_rect(self):
        """返回没有大小和位置的元素"""
        return self._any_state('has_rect', True)

    def style(self, name, value):
        """返回拥有某个style值的元素
        :param name: 属性名称
        :param value: 属性值
        :return: 筛选结果
        """
        return self._get_attr(name, value, 'style')

    def property(self, name, value):
        """返回拥有某个property值的元素
        :param name: 属性名称
        :param value: 属性值
        :return: 筛选结果
        """
        return self._get_attr(name, value, 'property')

    def attr(self, name, value):
        """返回拥有某个attribute值的元素
        :param name: 属性名称
        :param value: 属性值
        :return: 筛选结果
        """
        return self._get_attr(name, value, 'attr')

    def _get_attr(self, name, value, method):
        pass

    def _any_state(self, name, is_not=False):
        pass


class Filter(BaseFilter):

    def __iter__(self):
        return iter(self._list)

    def __next__(self):
        return next(self._list)

    @property
    def get(self):
        """返回用于获取元素属性的对象"""
        return self._list.get

    def have_text(self):
        """返回包含文本的元素"""
        r = ElementsList()
        for i in self._list:
            if i.raw_text:
                r.append(i)
        self._list = r
        return self

    def _get_attr(self, name, value, method):
        """返回通过某个方法可获得某个值的元素
        :param name: 属性名称
        :param value: 属性值
        :param method: 方法名称
        :return: 筛选结果
        """
        r = ElementsList()
        for i in self._list:
            if getattr(i, method)(name) == value:
                r.append(i)
        self._list = r
        return self

    def _any_state(self, name, is_not=False):
        """
        :param name: 状态名称
        :param is_not: 是否选择否定的
        :return: 选中的列表
        """
        r = ElementsList()
        if is_not:
            for i in self._list:
                if not getattr(i.states, name):
                    r.append(i)
        else:
            for i in self._list:
                if getattr(i.states, name):
                    r.append(i)
        self._list = r
        return self


class FilterOne(BaseFilter):

    def have_text(self):
        """返回包含文本的元素"""
        for i in self._list:
            if i.raw_text:
                return i
        return NoneElement(self._list._page, method='have_text()')

    def _get_attr(self, name, value, method):
        """返回通过某个方法可获得某个值的元素
        :param name: 属性名称
        :param value: 属性值
        :param method: 方法名称
        :return: 筛选结果
        """
        for i in self._list:
            if getattr(i, method)(name) == value:
                return i
        return NoneElement(self._list._page, f'{method}()', args={'name': name, 'value': value})

    def _any_state(self, name, is_not=False):
        """
        :param name: 状态名称
        :param is_not: 是否选择否定的
        :return: 选中的列表
        """
        if is_not:
            for i in self._list:
                if not getattr(i.states, name):
                    return i
        else:
            for i in self._list:
                if getattr(i.states, name):
                    return i

        return NoneElement(self._list._page, f'{name}()', args={'name': name, 'is_not': is_not})


class Getter(object):
    def __init__(self, _list):
        self._list = _list

    def links(self):
        return [e.link for e in self._list]

    def texts(self):
        return [e.text for e in self._list]

    def attrs(self, name):
        return [e.attr(name) for e in self._list]


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
