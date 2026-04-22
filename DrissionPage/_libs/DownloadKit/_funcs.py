# -*- coding:utf-8 -*-
"""
@Author  :   g1879
@Contact :   g1879@qq.com
"""
import hashlib
from copy import copy
from os import path as os_PATH
from pathlib import Path
from random import randint
from re import search, sub
from threading import Lock
from time import time
from typing import Optional, Tuple
from urllib.parse import unquote

from DataRecorder.tools import get_usable_path, make_valid_name
from requests import Session

FILE_EXISTS_MODE = {'rename': 'rename', 'overwrite': 'overwrite', 'skip': 'skip', 'add': 'add', 'r': 'rename',
                    'o': 'overwrite', 's': 'skip', 'a': 'add'}

INTEGRITY_ALGORITHMS = {'md5', 'sha256', None}


def copy_session(session):
    """复制输入Session对象，返回一个新的
    :param session: 被复制的Session对象
    :return: 新Session对象
    """
    new = Session()
    new.headers = session.headers.copy()
    new.cookies = session.cookies.copy()
    new.stream = True
    new.auth = session.auth
    new.proxies = dict(session.proxies).copy()
    new.params = copy(session.params)
    new.cert = session.cert
    new.max_redirects = session.max_redirects
    new.trust_env = session.trust_env
    new.verify = session.verify

    return new


class BlockSizeSetter(object):
    def __set__(self, block_size, val):
        if isinstance(val, int) and val > 0:
            size = val
        elif isinstance(val, str):
            units = {'b': 1, 'k': 1024, 'm': 1048576, 'g': 21474836480}
            num = int(val[:-1])
            unit = units.get(val[-1].lower(), None)
            if unit and num > 0:
                size = num * unit
            else:
                raise ValueError('单位只支持B、K、M、G，数字必须为大于0的整数。')
        else:
            raise TypeError('split_size只能传入int或str，数字必须为大于0的整数。')

        block_size._block_size = size

    def __get__(self, block_size, objtype=None) -> int:
        return block_size._block_size


class PathSetter(object):
    def __set__(self, save_path, val):
        if val is not None and not isinstance(val, (str, Path)):
            raise TypeError('路径只能是str或Path类型。')
        save_path._save_path = str(val) if isinstance(val, Path) else val

    def __get__(self, save_path, objtype=None):
        return save_path._save_path


class FileExistsSetter(object):
    def __set__(self, file_exists, mode):
        file_exists._file_exists = get_file_exists_mode(mode)

    def __get__(self, file_exists, objtype=None):
        return file_exists._file_exists


def get_file_exists_mode(mode):
    """获取文件重名时处理策略名称
    :param mode: 输入
    :return: 标准字符串
    """
    mode = FILE_EXISTS_MODE.get(mode, mode)
    if mode not in FILE_EXISTS_MODE:
        raise ValueError(f'''mode参数只能是 '{"', '".join(FILE_EXISTS_MODE.keys())}' 之一，现在是：{mode}''')
    return mode


def set_charset(response, encoding):
    """设置Response对象的编码
    :param response: Response对象
    :param encoding: 指定的编码格式
    :return: 设置编码后的Response对象
    """
    if encoding:
        response.encoding = encoding
        return response

    content_type = response.headers.get('content-type', '').lower()
    if not content_type.endswith(';'):
        content_type += ';'
    charset = search(r'charset[=: ]*(.*)?;?', content_type)

    if charset:
        response.encoding = charset.group(1)

    elif content_type.replace(' ', '').startswith('text/html'):
        re_result = search(b'<meta.*?charset=[ \\\'"]*([^"\\\' />]+).*?>', response.content)

        if re_result:
            charset = re_result.group(1).decode()
        else:
            charset = response.apparent_encoding

        response.encoding = charset

    return response


def parse_content_range(content_range: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """解析 Content-Range 响应头
    格式: bytes 0-499/1234 或 bytes */1234
    :param content_range: Content-Range 头值
    :return: (start, end, total)，解析失败返回 (None, None, None)
    """
    if not content_range:
        return None, None, None

    match = search(r'bytes\s+(\d+)-(\d+)/(\d+|\*)', content_range)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        total = None if match.group(3) == '*' else int(match.group(3))
        return start, end, total

    match = search(r'bytes\s+\*/(\d+)', content_range)
    if match:
        return None, None, int(match.group(1))

    return None, None, None


def verify_range_match(requested_start: int, requested_end: int, 
                        content_range: str) -> Tuple[bool, str]:
    """验证请求的 Range 与返回的 Content-Range 是否匹配
    :param requested_start: 请求的起始字节
    :param requested_end: 请求的结束字节（空字符串表示到文件末尾）
    :param content_range: 响应的 Content-Range 头
    :return: (是否匹配, 不匹配原因)
    """
    resp_start, resp_end, resp_total = parse_content_range(content_range)
    
    if resp_start is None or resp_end is None:
        return False, f"无法解析 Content-Range: {content_range}"
    
    if resp_start != requested_start:
        return False, f"Range 不匹配：请求起始 {requested_start}，响应起始 {resp_start}"
    
    if requested_end != '' and resp_end != requested_end:
        return False, f"Range 不匹配：请求结束 {requested_end}，响应结束 {resp_end}"
    
    return True, "Range 匹配"


def calculate_file_hash(file_path: str, algorithm: str = 'sha256', 
                        block_size: int = 65536) -> str:
    """计算文件的哈希值
    :param file_path: 文件路径
    :param algorithm: 哈希算法 ('md5' 或 'sha256')
    :param block_size: 读取块大小
    :return: 十六进制哈希字符串
    """
    if algorithm not in INTEGRITY_ALGORITHMS:
        raise ValueError(f"不支持的哈希算法: {algorithm}，支持: {INTEGRITY_ALGORITHMS}")
    
    if algorithm is None:
        return ''
    
    hasher = hashlib.md5() if algorithm.lower() == 'md5' else hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            hasher.update(block)
    
    return hasher.hexdigest()


def verify_file_integrity(file_path: str, expected_hash: str, 
                          algorithm: str = 'sha256') -> Tuple[bool, str]:
    """验证文件完整性
    :param file_path: 文件路径
    :param expected_hash: 期望的哈希值
    :param algorithm: 哈希算法 ('md5' 或 'sha256')
    :return: (是否通过, 实际哈希值或错误信息)
    """
    try:
        actual_hash = calculate_file_hash(file_path, algorithm)
        if actual_hash.lower() == expected_hash.lower():
            return True, actual_hash
        else:
            return False, actual_hash
    except FileNotFoundError:
        return False, f"文件不存在: {file_path}"
    except Exception as e:
        return False, f"校验失败: {str(e)}"


def get_part_file_path(final_path: Path) -> Path:
    """获取临时文件路径（.part 文件）
    :param final_path: 最终文件路径
    :return: 临时文件路径
    """
    return final_path.with_suffix(final_path.suffix + '.part')


def safe_move(src: Path, dst: Path, max_retries: int = 10, 
              retry_interval: float = 0.5) -> Tuple[bool, str]:
    """安全移动文件，带有重试机制
    :param src: 源文件路径
    :param dst: 目标文件路径
    :param max_retries: 最大重试次数
    :param retry_interval: 重试间隔（秒）
    :return: (是否成功, 错误信息)
    """
    from shutil import move, copy
    
    for _ in range(max_retries):
        try:
            move(str(src), str(dst))
            return True, "成功"
        except PermissionError:
            sleep(retry_interval)
        except Exception as e:
            try:
                copy(str(src), str(dst))
                src.unlink()
                return True, "成功（使用复制替代移动）"
            except Exception as e2:
                return False, f"移动文件失败: {str(e2)}"
    
    try:
        copy(str(src), str(dst))
        src.unlink()
        return True, "成功（使用复制替代移动）"
    except Exception as e:
        return False, f"移动文件失败: {str(e)}"


def get_file_info(response, save_path=None, rename=None, suffix=None, 
                  file_exists=None, encoding=None, lock=None):
    """获取文件信息，大小单位为byte
    包括：size、path、skip
    :param response: Response对象
    :param save_path: 目标文件夹
    :param rename: 重命名
    :param suffix: 重命名后缀名
    :param file_exists: 存在重名文件时的处理方式
    :param encoding: 编码格式
    :param lock: 线程锁
    :return: 文件大小、完整路径、是否跳过、是否覆盖
    """
    file_size = response.headers.get('Content-Length', None)
    file_size = None if file_size is None else int(file_size)

    file_name = _get_file_name(response, encoding)

    goal_Path = Path(save_path)
    g = save_path[len(goal_Path.anchor):] if save_path.lower().startswith(goal_Path.anchor.lower()) else save_path
    save_path = goal_Path.anchor + sub(r'[*:|<>?"]', '', g).strip()
    goal_Path = Path(save_path).absolute()
    goal_Path.mkdir(parents=True, exist_ok=True)

    if rename:
        if suffix is not None:
            full_name = f'{rename}.{suffix}' if suffix else rename

        else:
            tmp = file_name.rsplit('.', 1)
            ext_name = f'.{tmp[-1]}' if len(tmp) > 1 else ''
            tmp = rename.rsplit('.', 1)
            ext_rename = f'.{tmp[-1]}' if len(tmp) > 1 else ''
            full_name = rename if ext_rename == ext_name else f'{rename}{ext_name}'

    elif suffix is not None:
        full_name = file_name.rsplit(".", 1)[0]
        if suffix:
            full_name = f'{full_name}.{suffix}'

    else:
        full_name = file_name

    full_name = make_valid_name(full_name)

    skip = False
    overwrite = False
    create = True
    full_path = goal_Path / full_name

    with lock:
        if full_path.exists():
            if file_exists == 'rename':
                full_path = get_usable_path(full_path)

            elif file_exists == 'skip':
                skip = True
                create = False

            elif file_exists == 'overwrite':
                overwrite = True
                full_path.unlink()

            elif file_exists == 'add':
                create = False

        if create:
            with open(full_path, 'wb'):
                pass

    return {'size': file_size,
            'path': full_path,
            'skip': skip,
            'overwrite': overwrite}


def _get_file_name(response, encoding) -> str:
    """从headers或url中获取文件名，如果获取不到，生成一个随机文件名
    :param response: 返回的response
    :param encoding: 在headers获取时指定编码格式
    :return: 下载文件的文件名
    """
    file_name = ''
    charset = ''
    content_disposition = response.headers.get('content-disposition', '').replace(' ', '')

    if content_disposition:
        txt = search(r'filename\*="?([^";]+)', content_disposition)
        if txt:
            txt = txt.group(1).split("''", 1)
            if len(txt) == 2:
                charset, file_name = txt
            else:
                file_name = txt[0]

        else:
            txt = search(r'filename="?([^";]+)', content_disposition)
            if txt:
                file_name = txt.group(1)

                charset = encoding or response.encoding

        file_name = file_name.strip("'")

    if not file_name and os_PATH.basename(response.url):
        file_name = os_PATH.basename(response.url).split("?")[0]

    if not file_name:
        file_name = f'untitled_{time()}_{randint(0, 100)}'

    charset = charset or 'utf-8'
    return unquote(file_name, charset)


def set_session_cookies(session, cookies):
    """设置Session对象的cookies
    :param session: Session对象
    :param cookies: cookies信息
    :return: None
    """
    for cookie in cookies:
        if cookie['value'] is None:
            cookie['value'] = ''

        kwargs = {x: cookie[x] for x in cookie
                  if x.lower() in ('version', 'port', 'domain', 'path', 'secure',
                                   'expires', 'discard', 'comment', 'comment_url', 'rest')}

        if 'expiry' in cookie:
            kwargs['expires'] = cookie['expiry']

        session.cookies.set(cookie['name'], cookie['value'], **kwargs)


from time import sleep
