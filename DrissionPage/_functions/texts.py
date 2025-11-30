# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
from typing import Optional, Literal, Any


class Texts(object):
    """文本类，用于多语言支持"""
    def __init__(self, lang_code: Optional[str] = None):
        self.lang_code = lang_code or 'zh_cn'
        # 定义常用的错误消息（中文）
        self.BROWSER_NOT_FOUND = "未找到浏览器可执行文件，请检查浏览器路径是否正确。"
        self.BROWSER_EXE_NOT_FOUND = "未找到浏览器可执行文件，请检查浏览器路径是否正确。"
        self.BROWSER_CONNECT_ERR1_ = "端口 {0} 已被占用，请关闭占用该端口的程序或使用其他端口。"
        self.BROWSER_CONNECT_ERR2 = "无法连接到浏览器，请检查浏览器是否正常运行。"
        self.BROWSER_CONNECT_ERR_INFO = "无法连接到浏览器，请检查浏览器是否正常运行。"
        self.INCORRECT_TYPE_ = "参数类型错误：{CURR_VAL} 的类型不正确，应为 {ALLOW_TYPE}。"
        self.INCORRECT_VAL_ = "参数值错误：{CURR_VAL} 的值不正确，应为 {ALLOW_VAL}。"
        self.UNSUPPORTED_CSS_SYNTAX = "不支持的 CSS 选择器语法。"
        self.GET_OBJ_FAILED = "获取对象失败。"
        self.RUN_BY_ADMIN = "请尝试以管理员身份运行。"
        self.NEED_DOWNLOAD_PATH = "需要设置下载路径。"
        self.SET_DOWNLOAD_PATH = "请使用 set.download_path() 设置下载路径。"
        self.NOT_BLOB = "URL {url} 不是 blob 类型。"
        self.GET_BLOB_FAILED = "获取 blob 数据失败。"
        self.GET_PDF_FAILED = "获取 PDF 失败。"
        self.S_MODE_ONLY = "此方法仅在 s 模式下可用。"
        self.CANNOT_INPUT_FILE = "无法输入文件。"
        self.ELE_OR_LOC = "元素或定位符"
        self.CONNECT_ERR = "连接错误：{INFO}"
        self.TIMEOUT_ = "超时：{0}"
        self.PAGE_CONNECT = "页面连接"
        self.ZERO_PAGE_SIZE = "页面大小为 0。"
        self.STATUS_CODE_ = "HTTP 状态码错误：{0}"
        self.CONTENT_IS_EMPTY = "响应内容为空。"
        self.SET_FAILED_ = "设置失败：{0} = {VALUE}"
        self.GET_WINDOW_SIZE_FAILED = "获取窗口大小失败。"
        self.SET_WINDOW_NORMAL = "请使用 set.window.normal() 设置窗口大小。"
        self.NEED_LIB_ = "需要库：{0}，提示：{TIP}"
        self.INVALID_HEADER_NAME = "无效的请求头名称：{headers}"
        self.METHOD_NOT_FOUND = "方法未找到：浏览器版本 {BROWSER_VER} 不支持方法 {METHOD}"
        self.NO_RESPONSE = "无响应：{INFO}"
        self.UNKNOWN_ERR = "未知错误：{INFO}，提示：{TIP}"
        self.FEEDBACK = "请反馈此问题。"
        self.SELECT_ONLY = "此方法仅适用于单选下拉框。"
        self.MULTI_SELECT_ONLY = "此方法仅适用于多选下拉框。"
        self.OPTION_NOT_FOUND = "未找到选项。"
        self.STR_FOR_SINGLE_SELECT = "单选下拉框应使用字符串。"
        self.NEED_ARG_ = "需要参数：{0}"
        self.ONLY_ENGLISH = "路径只能包含英文字符，当前值：{CURR_VAL}"
        self.NEED_DOMAIN = "需要域名。"
        self.D_MODE_ONLY = "此方法仅在 d 模式下可用。"
        self.NOT_LISTENING = "未在监听。"
        self.WAITING_FAILED_ = "等待失败：{0}，超时时间：{1}"
        self.DATA_PACKET = "数据包"
        self.NO_NEW_TAB = "未找到新标签页。"
        self.NO_SRC_ATTR = "元素没有 src 属性。"
        self.JS_RUNTIME_ERR = "JavaScript 运行时错误。"
        self.RUN_JS = "运行 JavaScript"
        self.JS_RESULT_ERR = "JavaScript 结果错误：{INFO}，JS代码：{JS}，提示：{TIP}"
        self.UNSUPPORTED_ARG_TYPE_ = "不支持的参数类型：{0}，类型：{1}"
        self.INI_NOT_FOUND = "配置文件未找到：{PATH}"
        self.INI_NOT_SET = "配置文件未设置。"
        self.INDEX_FORMAT = "索引格式错误：{CURR_VAL}"
        self.NOT_BLOB = "URL {url} 不是 blob 类型。"
        self.S_MODE_GET_FAILED = "s 模式获取失败。"
        # 等待相关
        self.WAITING_FAILED_ = "等待失败：{0}，超时时间：{1}"
        self.ELE_CLICKABLE = "元素可点击"
        self.ELE_DISPLAYED = "元素显示"
        self.ELE_LOADED = "元素加载"
        self.ELE_DEL = "元素删除"
        self.ELE_HIDDEN = "元素隐藏"
        self.ELE_COVERED = "元素被覆盖"
        self.ELE_NOT_COVERED = "元素未被覆盖"
        self.ELE_AVAILABLE = "元素可用"
        self.ELE_NOT_AVAILABLE = "元素不可用"
        self.ELE_HIDDEN_DEL = "元素隐藏或删除"
        self.ELE_HAS_RECT = "元素有矩形区域"
        self.ELE_STOP_MOVING = "元素停止移动"
        self.ELE_STATE_CHANGED_ = "元素状态改变，超时时间：{0}"
        self.NEW_TAB = "新标签页"
        self.ARG = "参数"
        self.PAGE_LOADED = "页面加载"
        self.DATA_PACKET = "数据包"
        # 其他
        self.ELE_LOC_FORMAT = "元素或定位符格式"
        self.NO_SUCH_KEY_ = "没有这样的键：{0}"
        self.NEED_FILES_OR_TEXT_ARG = "需要 files 或 text 参数"
        self.CHOOSE_RECORD_TARGET = "选择录制目标"
        self.START_RECORD = "开始录制"
        self.STOP_RECORDING = "停止录制"
        self.SAVE_PATH_MUST_BE_FOLDER = "保存路径必须是文件夹"
        self.BROWSER_DISCONNECTED = "浏览器已断开连接"
        self.NEW_ELE_INFO = "新元素信息"
        
    def get(self, key: str) -> str:
        """获取错误消息
        :param key: 错误消息键
        :return: 错误消息文本
        """
        return getattr(self, key, f"[{key}]")
    
    def join(self, template: str, *args, **kwargs) -> str:
        """格式化错误消息
        :param template: 模板字符串
        :param args: 位置参数，用于替换 {0}, {1} 等占位符
        :param kwargs: 关键字参数，用于替换 {KEY} 等占位符
        :return: 格式化后的字符串
        """
        if not template:
            return ""
        
        # 如果有位置参数或关键字参数，进行格式化
        if args or kwargs:
            try:
                # 先处理位置参数：{0}, {1} 等
                result = template
                for i, arg in enumerate(args):
                    # 替换 {i} 格式的占位符
                    result = result.replace(f'{{{i}}}', str(arg))
                
                # 再处理关键字参数：{KEY} 等
                if kwargs:
                    # 使用 format 方法处理关键字参数
                    # 但需要避免与已替换的位置参数冲突
                    for key, value in kwargs.items():
                        result = result.replace(f'{{{key}}}', str(value))
                
                return result
            except (KeyError, ValueError, AttributeError):
                # 如果格式化失败，返回原始模板
                return template
        else:
            return template


def get_txt_class(code: Optional[Literal['zh_cn', 'en']] = None) -> Texts:
    """获取文本类实例
    :param code: 语言代码，'zh_cn' 或 'en'
    :return: Texts 实例
    """
    return Texts(code)

