# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Copyright: (c) 2024 by g1879, Inc. All Rights Reserved.
@License  : BSD 3-Clause.
"""
from copy import copy
from time import sleep

from .._base.base import BasePage
from .._configs.session_options import SessionOptions
from .._functions.cookies import set_session_cookies, set_tab_cookies
from .._functions.settings import Settings
from .._functions.web import save_page
from .._pages.chromium_base import ChromiumBase
from .._pages.session_page import SessionPage
from .._units.setter import TabSetter, MixTabSetter
from .._units.waiter import TabWaiter


class ChromiumTab(ChromiumBase):
    """实现浏览器标签页的类"""
    _TABS = {}

    def __new__(cls, browser, tab_id):
        if Settings.singleton_tab_obj and tab_id in cls._TABS:
            r = cls._TABS[tab_id]
            while not hasattr(r, '_frame_id'):
                sleep(.1)
            return r
        r = object.__new__(cls)
        cls._TABS[tab_id] = r
        return r

    def __init__(self, browser, tab_id):
        if Settings.singleton_tab_obj and hasattr(self, '_created'):
            return
        self._created = True

        super().__init__(browser, tab_id)
        self._tab = self
        self._type = 'ChromiumTab'

    def _d_set_runtime_settings(self):
        self._timeouts = copy(self.browser.timeouts)
        self.retry_times = self.browser.retry_times
        self.retry_interval = self.browser.retry_interval
        self._load_mode = self.browser._load_mode
        self._download_path = self.browser.download_path

    def close(self, others=False):
        self.browser.close_tabs(self.tab_id, others=others)

    @property
    def set(self):
        if self._set is None:
            self._set = TabSetter(self)
        return self._set

    @property
    def wait(self):
        if self._wait is None:
            self._wait = TabWaiter(self)
        return self._wait

    def save(self, path=None, name=None, as_pdf=False, **kwargs):
        return save_page(self, path, name, as_pdf, kwargs)

    def __repr__(self):
        return f'<ChromiumTab browser_id={self.browser.id} tab_id={self.tab_id}>'

    def _on_disconnect(self):
        ChromiumTab._TABS.pop(self.tab_id, None)


class MixTab(SessionPage, ChromiumTab, BasePage):
    def __init__(self, browser, tab_id):
        if Settings.singleton_tab_obj and hasattr(self, '_created'):
            return

        self._mode = 'd'
        self._has_driver = True
        self._has_session = True
        super().__init__(session_or_options=browser._session_options if browser._session_options else SessionOptions())
        super(SessionPage, self).__init__(browser=browser, tab_id=tab_id)
        self._type = 'MixTab'

    def __call__(self, locator, index=1, timeout=None):
        if self._mode == 'd':
            return super(SessionPage, self).__call__(locator, index=index, timeout=timeout)
        elif self._mode == 's':
            return super().__call__(locator, index=index)

    @property
    def set(self):
        if self._set is None:
            self._set = MixTabSetter(self)
        return self._set

    @property
    def url(self):
        if self._mode == 'd':
            return self._browser_url
        elif self._mode == 's':
            return self._session_url

    @property
    def _browser_url(self):
        return super(SessionPage, self).url if self._driver else None

    @property
    def title(self):
        if self._mode == 's':
            return super().title
        elif self._mode == 'd':
            return super(SessionPage, self).title

    @property
    def raw_data(self):
        if self._mode == 's':
            return super().raw_data
        elif self._mode == 'd':
            return super(SessionPage, self).html if self._has_driver else ''

    @property
    def html(self):
        if self._mode == 's':
            return super().html
        elif self._mode == 'd':
            return super(SessionPage, self).html if self._has_driver else ''

    @property
    def json(self):
        if self._mode == 's':
            return super().json
        elif self._mode == 'd':
            return super(SessionPage, self).json

    @property
    def response(self):
        return self._response

    @property
    def mode(self):
        return self._mode

    @property
    def user_agent(self):
        if self._mode == 's':
            return super().user_agent
        elif self._mode == 'd':
            return super(SessionPage, self).user_agent

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
        return self._timeout if self._mode == 's' else self.timeouts.base

    def get(self, url, show_errmsg=False, retry=None, interval=None, timeout=None, **kwargs):
        if self._mode == 'd':
            if kwargs:
                raise ValueError(f'以下参数在s模式下才会生效：{" ".join(kwargs.keys())}')
            return super(SessionPage, self).get(url, show_errmsg, retry, interval, timeout)
        elif self._mode == 's':
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
        if self._mode == 's':
            return super().ele(locator, index=index)
        elif self._mode == 'd':
            return super(SessionPage, self).ele(locator, index=index, timeout=timeout)

    def eles(self, locator, timeout=None):
        if self._mode == 's':
            return super().eles(locator)
        elif self._mode == 'd':
            return super(SessionPage, self).eles(locator, timeout=timeout)

    def s_ele(self, locator=None, index=1):
        if self._mode == 's':
            return super().s_ele(locator, index=index)
        elif self._mode == 'd':
            return super(SessionPage, self).s_ele(locator, index=index)

    def s_eles(self, locator):
        if self._mode == 's':
            return super().s_eles(locator)
        elif self._mode == 'd':
            return super(SessionPage, self).s_eles(locator)

    def change_mode(self, mode=None, go=True, copy_cookies=True):
        if mode is not None and mode.lower() == self._mode:
            return

        self._mode = 's' if self._mode == 'd' else 'd'

        # s模式转d模式
        if self._mode == 'd':
            if self._driver is None:
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

        # d模式转s模式
        elif self._mode == 's':
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
        if self._mode == 's':
            return super().cookies(all_domains, all_info)
        elif self._mode == 'd':
            return super(SessionPage, self).cookies(all_domains, all_info)

    def close(self, others=False):
        self.browser.close_tabs(self.tab_id, others=others)
        self._session.close()
        if self._response is not None:
            self._response.close()

    def _find_elements(self, locator, timeout=None, index=1, relative=False, raise_err=None):
        if self._mode == 's':
            return super()._find_elements(locator, index=index)
        elif self._mode == 'd':
            return super(SessionPage, self)._find_elements(locator, timeout=timeout, index=index, relative=relative)

    def __repr__(self):
        return f'<MixTab browser_id={self.browser.id} tab_id={self.tab_id}>'
