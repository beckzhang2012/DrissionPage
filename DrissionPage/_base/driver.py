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


_STATE_PENDING = 'pending'
_STATE_COMPLETED = 'completed'
_STATE_CANCELLED = 'cancelled'
_STATE_TIMEOUT = 'timeout'


class _DriverMetrics:
    cross_session_mismatch = 0
    late_response_isolated = 0
    duplicate_execution_blocked = 0
    final_state_consistent = 0
    final_state_total = 0

    @classmethod
    def reset(cls):
        cls.cross_session_mismatch = 0
        cls.late_response_isolated = 0
        cls.duplicate_execution_blocked = 0
        cls.final_state_consistent = 0
        cls.final_state_total = 0

    @classmethod
    def record_final_state(cls, consistent: bool):
        cls.final_state_total += 1
        if consistent:
            cls.final_state_consistent += 1

    @classmethod
    def get_consistency_rate(cls) -> float:
        if cls.final_state_total == 0:
            return 1.0
        return cls.final_state_consistent / cls.final_state_total


class Driver(object):
    def __init__(self, _id, address, owner=None):
        self.id = _id
        self.address = address
        self.owner = owner
        self.alert_flag = False

        self._cur_id = 0
        self._ws = None

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
        self._request_states = {}
        self._request_versions = {}
        self.event_queue = Queue()
        self.immediate_event_queue = Queue()

        self._id_lock = Lock()
        self._results_lock = Lock()
        self._session_version = 0

        self.start()

    def _get_next_id(self) -> int:
        with self._id_lock:
            self._cur_id += 1
            return self._cur_id

    def _register_request(self, ws_id: int, version: int):
        with self._results_lock:
            self._request_states[ws_id] = _STATE_PENDING
            self._request_versions[ws_id] = version

    def _set_request_state(self, ws_id: int, state: str) -> bool:
        with self._results_lock:
            if ws_id not in self._request_states:
                return False
            current_state = self._request_states[ws_id]
            if current_state in (_STATE_COMPLETED, _STATE_CANCELLED, _STATE_TIMEOUT):
                return False
            self._request_states[ws_id] = state
            return True

    def _get_request_state(self, ws_id: int):
        with self._results_lock:
            return self._request_states.get(ws_id)

    def _get_request_version(self, ws_id: int):
        with self._results_lock:
            return self._request_versions.get(ws_id)

    def _unregister_request(self, ws_id: int):
        with self._results_lock:
            self._request_states.pop(ws_id, None)
            self._request_versions.pop(ws_id, None)

    def _send(self, message, timeout=None):
        ws_id = self._get_next_id()
        message['id'] = ws_id
        message_json = dumps(message)

        current_version = self._session_version
        self._register_request(ws_id, current_version)

        end_time = perf_counter() + timeout if timeout is not None else None
        result_queue = Queue()
        with self._results_lock:
            self.method_results[ws_id] = result_queue

        try:
            self._ws.send(message_json)
            if timeout == 0:
                with self._results_lock:
                    self.method_results.pop(ws_id, None)
                self._set_request_state(ws_id, _STATE_COMPLETED)
                self._unregister_request(ws_id)
                _DriverMetrics.record_final_state(True)
                return {'id': ws_id, 'result': {}}

        except (OSError, WebSocketConnectionClosedException):
            with self._results_lock:
                self.method_results.pop(ws_id, None)
            self._set_request_state(ws_id, _STATE_CANCELLED)
            self._unregister_request(ws_id)
            _DriverMetrics.record_final_state(True)
            return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}

        result = None
        while self.is_running:
            try:
                result = result_queue.get(timeout=.2)
                with self._results_lock:
                    self.method_results.pop(ws_id, None)
                self._set_request_state(ws_id, _STATE_COMPLETED)
                _DriverMetrics.record_final_state(True)
                return result

            except Empty:
                if self.alert_flag and message['method'].startswith(('Input.', 'Runtime.')):
                    with self._results_lock:
                        self.method_results.pop(ws_id, None)
                    self._set_request_state(ws_id, _STATE_CANCELLED)
                    _DriverMetrics.record_final_state(True)
                    return {'error': {'message': 'alert exists.'}, 'type': 'alert_exists'}

                if timeout is not None and perf_counter() > end_time:
                    with self._results_lock:
                        self.method_results.pop(ws_id, None)
                    self._set_request_state(ws_id, _STATE_TIMEOUT)
                    _DriverMetrics.record_final_state(True)
                    return {'error': {'message': 'alert exists.'}, 'type': 'alert_exists'} \
                        if self.alert_flag else {'error': {'message': 'timeout'}, 'type': 'timeout'}

                continue

        with self._results_lock:
            self.method_results.pop(ws_id, None)
        self._set_request_state(ws_id, _STATE_CANCELLED)
        _DriverMetrics.record_final_state(True)
        return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}

    def _recv_loop(self):
        while self.is_running:
            try:
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

            elif 'id' in msg:
                msg_id = msg['id']
                current_version = self._session_version

                with self._results_lock:
                    if msg_id not in self.method_results:
                        req_state = self._get_request_state(msg_id)
                        if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
                            _DriverMetrics.late_response_isolated += 1
                            self._unregister_request(msg_id)
                        elif req_state == _STATE_COMPLETED:
                            _DriverMetrics.duplicate_execution_blocked += 1
                            self._unregister_request(msg_id)
                        continue

                    req_version = self._get_request_version(msg_id)
                    if req_version is not None and req_version != current_version:
                        _DriverMetrics.cross_session_mismatch += 1
                        self._unregister_request(msg_id)
                        continue

                    req_state = self._get_request_state(msg_id)
                    if req_state != _STATE_PENDING:
                        if req_state in (_STATE_TIMEOUT, _STATE_CANCELLED):
                            _DriverMetrics.late_response_isolated += 1
                        elif req_state == _STATE_COMPLETED:
                            _DriverMetrics.duplicate_execution_blocked += 1
                        self._unregister_request(msg_id)
                        continue

                    self.method_results[msg_id].put(msg)

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
        self.is_running = True
        with self._id_lock:
            self._session_version += 1
            self._cur_id = 0
        with self._results_lock:
            self.method_results.clear()
            self._request_states.clear()
            self._request_versions.clear()
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
        if not self.is_running:
            return False

        self.is_running = False
        if self._ws:
            self._ws.close()
            self._ws = None

        self.event_handlers.clear()
        with self._results_lock:
            self.method_results.clear()
            self._request_states.clear()
            self._request_versions.clear()
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
