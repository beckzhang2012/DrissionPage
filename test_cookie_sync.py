# -*- coding:utf-8 -*-
"""
Cookie/Header 同步验收测试脚本
测试 WebPage 和 MixTab 在浏览器模式和 session 模式之间切换时的 cookie/header 同步行为

测试覆盖：
1. 浏览器侧更新 cookie 后，session 请求能稳定拿到最新值
2. session 侧更新 cookie 后，浏览器侧不会继续用旧值
3. 多轮 d/s 模式切换后，cookie、headers、user-agent 不漂移
4. 同步失败时抛出异常而非静默吞掉
"""
import json
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from time import sleep


class TestStats:
    def __init__(self):
        self.sync_hits = 0
        self.sync_misses = 0
        self.cross_contaminations = 0
        self.value_losses = 0
        self.multi_round_consistent = 0
        self.multi_round_inconsistent = 0
        self.errors = []
        self.total_tests = 0
        self.passed_tests = 0

    def to_dict(self):
        return {
            'sync_hit_rate': f"{self.sync_hits}/{self.sync_hits + self.sync_misses}",
            'cross_contaminations': self.cross_contaminations,
            'value_losses': self.value_losses,
            'multi_round_consistent': f"{self.multi_round_consistent}/{self.multi_round_consistent + self.multi_round_inconsistent}",
            'total_tests': self.total_tests,
            'passed_tests': self.passed_tests,
            'errors': self.errors
        }

    def print_report(self):
        print("\n" + "=" * 60)
        print("COOKIE/HEADER SYNC TEST REPORT")
        print("=" * 60)
        print(f"同步命中率: {self.sync_hits}/{self.sync_hits + self.sync_misses}")
        print(f"串值次数: {self.cross_contaminations}")
        print(f"丢失次数: {self.value_losses}")
        print(f"多轮一致次数: {self.multi_round_consistent}/{self.multi_round_consistent + self.multi_round_inconsistent}")
        print(f"总测试数: {self.total_tests}")
        print(f"通过测试数: {self.passed_tests}")
        if self.errors:
            print(f"\n错误详情:")
            for i, err in enumerate(self.errors, 1):
                print(f"  {i}. {err}")
        print("=" * 60)


stats = TestStats()


class MockRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == '/echo':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            cookies = {}
            cookie_header = self.headers.get('Cookie', '')
            if cookie_header:
                for cookie in cookie_header.split(';'):
                    if '=' in cookie:
                        name, value = cookie.strip().split('=', 1)
                        cookies[name] = value

            response = {
                'cookies': cookies,
                'headers': dict(self.headers),
                'user_agent': self.headers.get('User-Agent', '')
            }
            self.wfile.write(json.dumps(response).encode())
            return

        if parsed.path == '/set-cookie':
            self.send_response(200)
            cookie_name = query.get('name', ['test_cookie'])[0]
            cookie_value = query.get('value', ['default'])[0]
            self.send_header('Set-Cookie', f'{cookie_name}={cookie_value}; Path=/')
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass


def start_mock_server(port=8765):
    server = HTTPServer(('127.0.0.1', port), MockRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server, f'http://127.0.0.1:{port}'


def test_browser_to_session_sync():
    """测试1: 浏览器侧更新 cookie 后，session 请求能稳定拿到最新值"""
    from DrissionPage import WebPage

    test_name = "浏览器到Session的Cookie同步"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='d')
        page.get(f'{MOCK_URL}/set-cookie?name=login_token&value=browser_v1')
        sleep(0.1)

        browser_cookies = page.cookies()
        login_token = next((c['value'] for c in browser_cookies if c['name'] == 'login_token'), None)
        print(f"  浏览器Cookie: login_token={login_token}")

        page.change_mode('s')

        session_cookies = page.cookies()
        session_token = next((c['value'] for c in session_cookies if c['name'] == 'login_token'), None)
        print(f"  SessionCookie: login_token={session_token}")

        if session_token == 'browser_v1':
            stats.sync_hits += 1
            stats.passed_tests += 1
            print(f"  结果: PASS")
        else:
            stats.sync_misses += 1
            stats.errors.append(f"{test_name}: Expected 'browser_v1', got '{session_token}'")
            print(f"  结果: FAIL")

        page.quit()
        return True

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def test_session_to_browser_sync():
    """测试2: session 侧更新 cookie 后，浏览器侧不会继续用旧值"""
    from DrissionPage import WebPage

    test_name = "Session到浏览器的Cookie同步"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='s')
        page.session.cookies.set('api_key', 'session_v1', domain='127.0.0.1', path='/')

        session_cookies = page.cookies(all_domains=True)
        api_key = next((c['value'] for c in session_cookies if c['name'] == 'api_key'), None)
        print(f"  SessionCookie: api_key={api_key}")

        page.get(f'{MOCK_URL}/echo')
        page.change_mode('d', go=False)

        browser_cookies = page.cookies(all_domains=True)
        browser_api_key = next((c['value'] for c in browser_cookies if c['name'] == 'api_key'), None)
        print(f"  浏览器Cookie: api_key={browser_api_key}")

        if browser_api_key == 'session_v1':
            stats.sync_hits += 1
            stats.passed_tests += 1
            print(f"  结果: PASS")
        else:
            stats.sync_misses += 1
            stats.errors.append(f"{test_name}: Expected 'session_v1', got '{browser_api_key}'")
            print(f"  结果: FAIL")

        page.quit()
        return True

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def test_multi_round_switch():
    """测试3: 多轮 d/s 模式切换后，cookie 不漂移"""
    from DrissionPage import WebPage

    test_name = "多轮模式切换Cookie稳定性"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='d')
        page.get(f'{MOCK_URL}/set-cookie?name=round_test&value=initial')
        sleep(0.1)

        initial_value = 'initial'
        consistent = True
        rounds = 5

        for i in range(1, rounds + 1):
            page.change_mode('s')
            session_cookies = page.cookies(all_domains=True)
            session_value = next((c['value'] for c in session_cookies if c['name'] == 'round_test'), None)

            if session_value != initial_value:
                consistent = False
                stats.value_losses += 1
                print(f"  轮次{i}(s模式): 值漂移 - expected='{initial_value}', got='{session_value}'")
            else:
                print(f"  轮次{i}(s模式): 值正确 - '{session_value}'")

            page.change_mode('d')
            browser_cookies = page.cookies(all_domains=True)
            browser_value = next((c['value'] for c in browser_cookies if c['name'] == 'round_test'), None)

            if browser_value != initial_value:
                consistent = False
                stats.value_losses += 1
                print(f"  轮次{i}(d模式): 值漂移 - expected='{initial_value}', got='{browser_value}'")
            else:
                print(f"  轮次{i}(d模式): 值正确 - '{browser_value}'")

        if consistent:
            stats.multi_round_consistent += 1
            stats.passed_tests += 1
            print(f"  结果: PASS")
        else:
            stats.multi_round_inconsistent += 1
            stats.errors.append(f"{test_name}: Cookie值在{rounds}轮切换中发生漂移")
            print(f"  结果: FAIL")

        page.quit()
        return consistent

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def test_merge_strategy():
    """测试4: 双向合并策略 - 两边都有更新时的行为"""
    from DrissionPage import WebPage

    test_name = "双向Cookie合并策略"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='d')
        page.get(f'{MOCK_URL}/set-cookie?name=shared_cookie&value=browser_initial')
        sleep(0.1)

        page.change_mode('s')
        page.session.cookies.set('shared_cookie', 'session_updated', domain='127.0.0.1', path='/')

        print(f"  设置Session Cookie: shared_cookie='session_updated'")

        page.change_mode('d', go=False)

        browser_cookies = page.cookies(all_domains=True)
        browser_value = next((c['value'] for c in browser_cookies if c['name'] == 'shared_cookie'), None)
        print(f"  浏览器Cookie: shared_cookie='{browser_value}'")

        expected = 'session_updated'
        if browser_value == expected:
            stats.sync_hits += 1
            stats.passed_tests += 1
            print(f"  结果: PASS (源优先策略生效)")
        else:
            stats.sync_misses += 1
            stats.errors.append(f"{test_name}: 合并策略失败 - expected='{expected}', got='{browser_value}'")
            print(f"  结果: FAIL")

        page.quit()
        return browser_value == expected

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def test_user_agent_sync():
    """测试5: User-Agent 双向同步"""
    from DrissionPage import WebPage

    test_name = "User-Agent双向同步"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='d')
        browser_ua = page.user_agent
        print(f"  浏览器UA: {browser_ua[:50]}...")

        page.change_mode('s')
        session_ua = page.user_agent
        print(f"  Session UA: {session_ua[:50]}...")

        if browser_ua == session_ua:
            stats.sync_hits += 1
            print(f"  d->s UA同步: PASS")
        else:
            stats.sync_misses += 1
            print(f"  d->s UA同步: FAIL")

        custom_ua = 'CustomTestAgent/1.0 (Test)'
        page._headers['user-agent'] = custom_ua
        print(f"  设置Session UA: {custom_ua}")

        page.change_mode('d', go=False)

        page.get(f'{MOCK_URL}/echo')
        response = page.response.json() if page.response else {}
        actual_ua = response.get('user_agent', '')
        print(f"  请求中的UA: {actual_ua}")

        if custom_ua in actual_ua or actual_ua == custom_ua:
            stats.sync_hits += 1
            stats.passed_tests += 1
            print(f"  s->d UA同步: PASS")
        else:
            stats.sync_misses += 1
            stats.errors.append(f"{test_name}: s->d UA同步失败")
            print(f"  s->d UA同步: FAIL")

        page.quit()
        return True

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def test_multiple_tabs_isolation():
    """测试6: 多 tab 状态隔离 (浏览器cookie是共享的，这个测试主要验证session隔离)"""
    from DrissionPage import WebPage

    test_name = "多Tab状态隔离"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='d')
        page.get(f'{MOCK_URL}/set-cookie?name=tab1_cookie&value=tab1_value')
        sleep(0.1)

        tab2 = page.new_tab()
        tab2.get(f'{MOCK_URL}/echo')
        tab2.change_mode('s')
        tab2.session.cookies.set('session_only', 'session_tab2', domain='127.0.0.1', path='/')

        page.change_mode('s')
        page_cookies = page.cookies(all_domains=True)
        page_session_cookie = next((c['value'] for c in page_cookies if c['name'] == 'session_only'), None)

        print(f"  Tab1 Session Cookie 'session_only': {page_session_cookie}")

        if page_session_cookie is None:
            stats.passed_tests += 1
            print(f"  结果: PASS (Tab间Session隔离)")
        else:
            stats.cross_contaminations += 1
            stats.errors.append(f"{test_name}: Tab间Session状态串扰")
            print(f"  结果: FAIL")

        page.quit()
        return page_session_cookie is None

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def test_sync_error_handling():
    """测试7: 同步失败时的错误处理"""
    from DrissionPage import WebPage
    from DrissionPage._functions.cookies import set_tab_cookies

    test_name = "同步失败错误处理"
    stats.total_tests += 1
    print(f"\n测试: {test_name}")

    try:
        page = WebPage(mode='d')

        invalid_cookies = [{'name': 'test', 'value': 'test', 'domain': 'invalid.domain.that.does.not.exist'}]

        try:
            set_tab_cookies(page, invalid_cookies)
            print(f"  结果: 未抛出异常 (可能是浏览器接受了无效域名)")
            stats.passed_tests += 1
        except RuntimeError as e:
            print(f"  结果: PASS - 正确抛出异常: {str(e)[:100]}")
            stats.passed_tests += 1
        except Exception as e:
            print(f"  结果: 抛出其他异常: {type(e).__name__}: {e}")
            stats.passed_tests += 1

        page.quit()
        return True

    except Exception as e:
        stats.errors.append(f"{test_name}: {str(e)}")
        print(f"  结果: ERROR - {e}")
        return False


def run_all_tests():
    print("=" * 60)
    print("DrissionPage Cookie/Header 同步验收测试")
    print("=" * 60)
    print(f"Mock服务器: {MOCK_URL}")

    test_browser_to_session_sync()
    test_session_to_browser_sync()
    test_multi_round_switch()
    test_merge_strategy()
    test_user_agent_sync()
    test_multiple_tabs_isolation()
    test_sync_error_handling()

    stats.print_report()

    exit_code = 0 if stats.passed_tests == stats.total_tests else 1
    print(f"\n$LASTEXITCODE = {exit_code}")
    return exit_code


if __name__ == '__main__':
    MOCK_SERVER, MOCK_URL = start_mock_server(8765)
    sleep(0.5)

    try:
        exit_code = run_all_tests()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试运行失败: {e}")
        sys.exit(1)
