# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Copyright: (c) 2024 by g1879, Inc. All Rights Reserved.
@License  : BSD 3-Clause.
"""
from ._base.browser import Browser
from ._configs.chromium_options import ChromiumOptions
from ._configs.session_options import SessionOptions
from ._pages.session_page import SessionPage

# 即将废弃
from ._pages.chromium_page import ChromiumPage
from ._pages.web_page import WebPage

__version__ = '4.1.0.0b0'
