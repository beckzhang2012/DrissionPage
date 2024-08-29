# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Copyright: (c) 2024 by g1879, Inc. All Rights Reserved.
@License  : BSD 3-Clause.
"""

from .chromium_tab import ChromiumTab
from .._base.base import BasePage
from .._configs.session_options import SessionOptions
from .._functions.cookies import set_session_cookies, set_tab_cookies
from .._functions.settings import Settings
from .._pages.session_page import SessionPage
from .._units.setter import MixTabSetter


class MixTab(SessionPage, ChromiumTab, BasePage):
    def __init__(self, browser, tab_id):
        if Settings.singleton_tab_obj and hasattr(self, '_created'):
            return

        self._d_mode = True
        self._has_driver = True
        self._has_session = True
        super().__init__(session_or_options=browser._session_options or SessionOptions(
            read_file=browser._session_options is None))
        super(SessionPage, self).__init__(browser=browser, tab_id=tab_id)
        self._type = 'MixTab'

    def __call__(self, locator, index=1, timeout=None):
        return super(SessionPage, self).__call__(locator, index=index, timeout=timeout) if self._d_mode \
            else super().__call__(locator, index=index)

    @property
    def set(self):
        if self._set is None:
            self._set = MixTabSetter(self)
        return self._set

    @property
    def url(self):
        return self._browser_url if self._d_mode else self._session_url

    @property
    def _browser_url(self):
        return super(SessionPage, self).url if self._driver else None

    @property
    def title(self):
        return super(SessionPage, self).title if self._d_mode else super().title

    @property
    def raw_data(self):
        if self._d_mode:
            return super(SessionPage, self).html if self._has_driver else ''
        return super().raw_data

    @property
    def html(self):
        if self._d_mode:
            return super(SessionPage, self).html if self._has_driver else ''
        return super().html

    @property
    def json(self):
        return super(SessionPage, self).json if self._d_mode else super().json

    @property
    def response(self):
        return self._response

    @property
    def mode(self):
        return 'd' if self._d_mode else 's'

    @property
    def user_agent(self):
        return super(SessionPage, self).user_agent if self._d_mode else super().user_agent

    @property
    def session(self):
        if self._session is None:
            self._create_session()
        return self._session

    @property
    def _session_url(self):
        return self._response.url if self._response else None

    @property
    def timeout(self):
        return self.timeouts.base if self._d_mode else self._timeout

    def get(self, url, show_errmsg=False, retry=None, interval=None, timeout=None, **kwargs):
        if self._d_mode:
            if kwargs:
                raise ValueError(f'以下参数在s模式下才会生效：{" ".join(kwargs.keys())}')
            return super(SessionPage, self).get(url, show_errmsg, retry, interval, timeout)

        if timeout is None:
            timeout = self.timeouts.page_load if self._has_driver else self.timeout
        return super().get(url, show_errmsg, retry, interval, timeout, **kwargs)

    def post(self, url, show_errmsg=False, retry=None, interval=None, **kwargs):
        if self.mode == 'd':
            self.cookies_to_session()
            super().post(url, show_errmsg, retry, interval, **kwargs)
            return self.response
        return super().post(url, show_errmsg, retry, interval, **kwargs)

    def ele(self, locator, index=1, timeout=None):
        return super(SessionPage, self).ele(locator, index=index, timeout=timeout) if self._d_mode \
            else super().ele(locator, index=index)

    def eles(self, locator, timeout=None):
        return super(SessionPage, self).eles(locator, timeout=timeout) if self._d_mode else super().eles(locator)

    def s_ele(self, locator=None, index=1):
        return super(SessionPage, self).s_ele(locator,
                                              index=index) if self._d_mode else super().s_ele(locator, index=index)

    def s_eles(self, locator):
        return super(SessionPage, self).s_eles(locator) if self._d_mode else super().s_eles(locator)

    def change_mode(self, mode=None, go=True, copy_cookies=True):
        if mode:
            mode = mode.lower()
        if mode is not None and ((mode == 'd' and self._d_mode) or (mode == 's' and not self._d_mode)):
            return

        self._d_mode = not self._d_mode

        # s模式转d模式
        if self._d_mode:
            if self._driver is None:  # todo: 优化这里的逻辑
                tabs = self.browser.tab_ids
                tid = self.tab_id if self.tab_id in tabs else tabs[0]
                self._connect_browser(tid)

            self._url = None if not self._has_driver else super(SessionPage, self).url
            self._has_driver = True
            if self._session_url:
                if copy_cookies:
                    self.cookies_to_browser()
                if go:
                    self.get(self._session_url)

            return

        # d模式转s模式
        self._has_session = True
        self._url = self._session_url
        if self._has_driver:
            if copy_cookies:
                self.cookies_to_session()

            if go:
                url = super(SessionPage, self).url
                if url.startswith('http'):
                    self.get(url)

    def cookies_to_session(self, copy_user_agent=True):
        if not self._has_session:
            return

        if copy_user_agent:
            user_agent = self._run_cdp('Runtime.evaluate', expression='navigator.userAgent;')['result']['value']
            self._headers.update({"User-Agent": user_agent})

        set_session_cookies(self.session, super(SessionPage, self).cookies())

    def cookies_to_browser(self):
        if not self._has_driver:
            return
        set_tab_cookies(self, super().cookies())

    def cookies(self, all_domains=False, all_info=False):
        return super(SessionPage, self).cookies(all_domains, all_info) if self._d_mode \
            else super().cookies(all_domains, all_info)

    def close(self, others=False):
        self.browser.close_tabs(self.tab_id, others=others)
        self._session.close()
        if self._response is not None:
            self._response.close()

    def _find_elements(self, locator, timeout=None, index=1, relative=False, raise_err=None):
        return super(SessionPage, self)._find_elements(locator, timeout=timeout, index=index, relative=relative) \
            if self._d_mode else super()._find_elements(locator, index=index)

    def __repr__(self):
        return f'<MixTab browser_id={self.browser.id} tab_id={self.tab_id}>'
