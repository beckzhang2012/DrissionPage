# -*- coding: utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
from json import dumps, loads, JSONDecodeError
from queue import Queue, Empty
from threading import Thread, Lock
from time import perf_counter, sleep

from requests import Session
from requests import adapters
from websocket import (WebSocketTimeoutException, WebSocketConnectionClosedException, create_connection,
                       WebSocketException, WebSocketBadStatusException)

from .._functions.settings import Settings as _S
from ..errors import PageDisconnectedError, BrowserConnectError

adapters.DEFAULT_RETRIES = 5


class Driver(object):
    def __init__(self, _id, address, owner=None):
        self.id = _id
        self.address = address
        self.owner = owner
        self.alert_flag = False  # 标记alert出现，跳过一条请求后复原

        self._cur_id = 0
        self._epoch = 0
        self._ws = None
        self._lock = Lock()

        self._recv_th = Thread(target=self._recv_loop)
        self._handle_event_th = Thread(target=self._handle_event_loop)
        self._recv_th.daemon = True
        self._handle_event_th.daemon = True
        self._handle_immediate_event_th = None

        self.is_running = False
        self.session_id = None

        self.event_handlers = {}
        self.immediate_event_handlers = {}
        self.method_results = {}
        self.event_queue = Queue()
        self.immediate_event_queue = Queue()

        self.start()

    def _send(self, message, timeout=None):
        with self._lock:
            self._cur_id += 1
            ws_id = self._cur_id
            current_epoch = self._epoch
            message['id'] = ws_id
            message_json = dumps(message)
            self.method_results[ws_id] = (current_epoch, Queue())

        end_time = perf_counter() + timeout if timeout is not None else None

        try:
            self._ws.send(message_json)
            if timeout == 0:
                with self._lock:
                    self.method_results.pop(ws_id, None)
                return {'id': ws_id, 'result': {}}

        except (OSError, WebSocketConnectionClosedException):
            with self._lock:
                self.method_results.pop(ws_id, None)
            return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}

        while self.is_running:
            with self._lock:
                entry = self.method_results.get(ws_id)
                if entry is None:
                    return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}
                epoch, queue = entry
                if epoch != current_epoch:
                    self.method_results.pop(ws_id, None)
                    return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}

            try:
                result = queue.get(timeout=.2)
                with self._lock:
                    self.method_results.pop(ws_id, None)
                return result

            except Empty:
                if self.alert_flag and message['method'].startswith(('Input.', 'Runtime.')):
                    with self._lock:
                        self.method_results.pop(ws_id, None)
                    return {'error': {'message': 'alert exists.'}, 'type': 'alert_exists'}

                if timeout is not None and perf_counter() > end_time:
                    with self._lock:
                        self.method_results.pop(ws_id, None)
                    return {'error': {'message': 'alert exists.'}, 'type': 'alert_exists'} \
                        if self.alert_flag else {'error': {'message': 'timeout'}, 'type': 'timeout'}

                continue

        return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}

    def _recv_loop(self):
        while self.is_running:
            try:
                # self._ws.settimeout(1)
                msg_json = self._ws.recv()
                msg = loads(msg_json)
            except WebSocketTimeoutException:
                continue
            except (WebSocketException, OSError, WebSocketConnectionClosedException, JSONDecodeError):
                self._stop()
                return

            if 'method' in msg:
                if msg['method'].startswith('Page.javascriptDialog'):
                    self.alert_flag = msg['method'].endswith('Opening')
                function = self.immediate_event_handlers.get(msg['method'])
                if function:
                    self._handle_immediate_event(function, msg['params'])
                else:
                    self.event_queue.put(msg)

            else:
                msg_id = msg.get('id')
                if msg_id is not None:
                    with self._lock:
                        entry = self.method_results.get(msg_id)
                        if entry is not None:
                            epoch, queue = entry
                            if epoch == self._epoch:
                                queue.put(msg)

    def _handle_event_loop(self):
        while self.is_running:
            try:
                event = self.event_queue.get(timeout=1)
            except Empty:
                continue

            function = self.event_handlers.get(event['method'])
            if function:
                function(**event['params'])

            self.event_queue.task_done()

    def _handle_immediate_event_loop(self):
        while not self.immediate_event_queue.empty():
            function, kwargs = self.immediate_event_queue.get(timeout=1)
            try:
                function(**kwargs)
            except PageDisconnectedError:
                pass

    def _handle_immediate_event(self, function, kwargs):
        self.immediate_event_queue.put((function, kwargs))
        if self._handle_immediate_event_th is None or not self._handle_immediate_event_th.is_alive():
            self._handle_immediate_event_th = Thread(target=self._handle_immediate_event_loop)
            self._handle_immediate_event_th.daemon = True
            self._handle_immediate_event_th.start()

    def run(self, _method, **kwargs):
        if not self.is_running:
            return {'error': 'connection disconnected', 'type': 'connection_error'}

        timeout = kwargs.pop('_timeout', _S.cdp_timeout)
        if self.session_id:
            result = self._send({'method': _method, 'params': kwargs, 'sessionId': self.session_id}, timeout=timeout)
        else:
            result = self._send({'method': _method, 'params': kwargs}, timeout=timeout)
        if 'result' not in result and 'error' in result:
            kwargs['_timeout'] = timeout
            return {'error': result['error']['message'], 'type': result.get('type', 'call_method_error'),
                    'method': _method, 'args': kwargs, 'data': result['error'].get('data')}
        else:
            return result['result']

    def start(self):
        with self._lock:
            self._epoch += 1
            self._cur_id = 0
            self.is_running = True
        try:
            self._ws = create_connection(self.address, enable_multithread=True, suppress_origin=True)
        except WebSocketBadStatusException as e:
            if 'Handshake status 403 Forbidden' in str(e):
                raise EnvironmentError(_S._lang.join(_S._lang.UPGRADE_WS))
            else:
                raise
        except ConnectionRefusedError:
            raise BrowserConnectError(_S._lang.BROWSER_NOT_EXIST)
        self._recv_th.start()
        self._handle_event_th.start()
        return True

    def stop(self):
        self._stop()
        while self._handle_event_th.is_alive() or self._recv_th.is_alive():
            sleep(.01)
        return True

    def _stop(self):
        with self._lock:
            if not self.is_running:
                return False

            self.is_running = False
            self._epoch += 1

            for ws_id, entry in list(self.method_results.items()):
                epoch, queue = entry
                queue.put({'error': {'message': 'connection disconnected'}, 'type': 'connection_error'})

            self.method_results.clear()

        if self._ws:
            self._ws.close()
            self._ws = None

        self.event_handlers.clear()
        self.event_queue.queue.clear()

        if hasattr(self.owner, '_on_disconnect'):
            self.owner._on_disconnect()

    def set_callback(self, event, callback, immediate=False):
        handler = self.immediate_event_handlers if immediate else self.event_handlers
        if callback:
            handler[event] = callback
        else:
            handler.pop(event, None)


class BrowserDriver(Driver):
    BROWSERS = {}

    def __new__(cls, _id, address, owner):
        if _id in cls.BROWSERS:
            return cls.BROWSERS[_id]
        return object.__new__(cls)

    def __init__(self, _id, address, owner):
        if hasattr(self, '_created'):
            return
        self._created = True
        BrowserDriver.BROWSERS[_id] = self
        super().__init__(_id, address, owner)

    def __repr__(self):
        return f'<BrowserDriver {self.id}>'

    @staticmethod
    def get(url):
        s = Session()
        s.trust_env = False
        s.keep_alive = False
        r = s.get(url, headers={'Connection': 'close'})
        r.close()
        s.close()
        return r
