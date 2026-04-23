# -*- coding: utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from json import dumps, loads, JSONDecodeError
from queue import Queue, Empty
from threading import Thread, Lock, Condition
from time import perf_counter, sleep
from typing import Any, Callable, Dict, Optional, Tuple

from requests import Session
from requests import adapters
from websocket import (WebSocketTimeoutException, WebSocketConnectionClosedException, create_connection,
                       WebSocketException, WebSocketBadStatusException)

from .._functions.settings import Settings as _S
from ..errors import PageDisconnectedError, BrowserConnectError


adapters.DEFAULT_RETRIES = 5


class EventPriority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class EventWrapper:
    event: Any
    method: str
    priority: EventPriority
    enqueue_time: float = field(default_factory=perf_counter)
    wait_count: int = 0


@dataclass
class MethodStats:
    processed: int = 0
    dropped: int = 0
    total_wait_time: float = 0.0
    max_wait_time: float = 0.0

    def record_process(self, wait_time: float) -> None:
        self.processed += 1
        self.total_wait_time += wait_time
        if wait_time > self.max_wait_time:
            self.max_wait_time = wait_time

    def record_drop(self) -> None:
        self.dropped += 1

    def get_average_wait_time(self) -> float:
        if self.processed == 0:
            return 0.0
        return self.total_wait_time / self.processed


@dataclass
class QueueStats:
    total_enqueued: int = 0
    total_dequeued: int = 0
    total_dropped: int = 0
    dropped_by_priority: Dict[int, int] = field(default_factory=lambda: defaultdict(int))
    dropped_by_method: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    max_wait_time: float = 0.0
    total_wait_time: float = 0.0
    processing_start_time: Optional[float] = None
    method_stats: Dict[str, 'MethodStats'] = field(default_factory=lambda: defaultdict(MethodStats))
    throughput_window: deque = field(default_factory=lambda: deque(maxlen=1000))

    def record_enqueue(self) -> None:
        self.total_enqueued += 1
        if self.processing_start_time is None:
            self.processing_start_time = perf_counter()

    def record_dequeue(self, wait_time: float, method: str) -> None:
        self.total_dequeued += 1
        self.total_wait_time += wait_time
        if wait_time > self.max_wait_time:
            self.max_wait_time = wait_time
        self.method_stats[method].record_process(wait_time)
        self.throughput_window.append(perf_counter())

    def record_drop(self, method: str, priority: int) -> None:
        self.total_dropped += 1
        self.dropped_by_priority[priority] += 1
        self.dropped_by_method[method] += 1
        self.method_stats[method].record_drop()

    def get_throughput(self) -> float:
        if not self.throughput_window:
            return 0.0
        now = perf_counter()
        window_start = self.throughput_window[0]
        elapsed = now - window_start
        if elapsed <= 0:
            return 0.0
        return len(self.throughput_window) / elapsed

    def get_average_wait_time(self) -> float:
        if self.total_dequeued == 0:
            return 0.0
        return self.total_wait_time / self.total_dequeued

    def get_fairness_index(self) -> float:
        if not self.method_stats:
            return 1.0
        process_counts = [stats.processed for stats in self.method_stats.values()]
        if not process_counts:
            return 1.0
        min_count = min(process_counts)
        max_count = max(process_counts)
        if max_count == 0:
            return 1.0
        return min_count / max_count if max_count > 0 else 1.0

    def reset(self) -> None:
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped = 0
        self.dropped_by_priority.clear()
        self.dropped_by_method.clear()
        self.max_wait_time = 0.0
        self.total_wait_time = 0.0
        self.processing_start_time = None
        self.method_stats.clear()
        self.throughput_window.clear()


class PriorityBasedEventMethodMapper:
    _DEFAULT_PRIORITY = EventPriority.NORMAL

    _HIGH_PRIORITY_METHODS = {
        'Page.javascriptDialogOpening',
        'Page.javascriptDialogClosed',
        'Target.attachedToTarget',
        'Target.detachedFromTarget',
        'Inspector.targetCrashed',
    }

    _CRITICAL_PRIORITY_METHODS = {
    }

    _LOW_PRIORITY_METHODS = {
        'Network.requestWillBeSent',
        'Network.responseReceived',
        'Network.dataReceived',
        'Network.loadingFinished',
        'Network.loadingFailed',
    }

    @classmethod
    def get_priority(cls, method: str) -> EventPriority:
        if method in cls._CRITICAL_PRIORITY_METHODS:
            return EventPriority.CRITICAL
        if method in cls._HIGH_PRIORITY_METHODS:
            return EventPriority.HIGH
        if method in cls._LOW_PRIORITY_METHODS:
            return EventPriority.LOW
        return cls._DEFAULT_PRIORITY


class BackPressureEventQueue:
    def __init__(
        self,
        capacity: int = 10000,
        max_wait_time_seconds: float = 30.0,
        drop_strategy: str = 'oldest_low_priority_first',
    ):
        self._capacity = capacity
        self._max_wait_time_seconds = max_wait_time_seconds
        self._drop_strategy = drop_strategy

        self._lock = Lock()
        self._not_empty = Condition(self._lock)

        self._queues: Dict[int, deque] = {
            EventPriority.CRITICAL: deque(),
            EventPriority.HIGH: deque(),
            EventPriority.NORMAL: deque(),
            EventPriority.LOW: deque(),
        }

        self._method_queues: Dict[str, deque] = {}
        self._method_round_robin: deque = deque()
        self._current_method_index = 0

        self._stats = QueueStats()
        self._is_running = True

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def max_wait_time_seconds(self) -> float:
        return self._max_wait_time_seconds

    @property
    def stats(self) -> QueueStats:
        return self._stats

    def qsize(self) -> int:
        with self._lock:
            return sum(len(q) for q in self._queues.values())

    def empty(self) -> bool:
        return self.qsize() == 0

    def full(self) -> bool:
        return self.qsize() >= self._capacity

    def put(self, event: Any, method: str, priority: Optional[EventPriority] = None) -> bool:
        if priority is None:
            priority = PriorityBasedEventMethodMapper.get_priority(method)

        with self._lock:
            if not self._is_running:
                return False

            if self.full():
                dropped = self._apply_back_pressure()
                if not dropped:
                    return False

            wrapper = EventWrapper(
                event=event,
                method=method,
                priority=priority,
            )

            self._queues[priority].append(wrapper)

            if method not in self._method_queues:
                self._method_queues[method] = deque()
                self._method_round_robin.append(method)
            self._method_queues[method].append(wrapper)

            self._stats.record_enqueue()
            self._not_empty.notify()

            return True

    def get(self, timeout: Optional[float] = None) -> Optional[Tuple[Any, str]]:
        with self._lock:
            if not self._is_running and self.empty():
                return None

            wrapper = self._get_next_event_fair(timeout)
            if wrapper is None:
                return None

            wait_time = perf_counter() - wrapper.enqueue_time
            self._stats.record_dequeue(wait_time, wrapper.method)

            return wrapper.event, wrapper.method

    def _get_next_event_fair(self, timeout: Optional[float] = None) -> Optional[EventWrapper]:
        deadline = None
        if timeout is not None:
            deadline = perf_counter() + timeout

        while True:
            if self._method_round_robin:
                num_methods = len(self._method_round_robin)
                for _ in range(num_methods):
                    method = self._method_round_robin[self._current_method_index]
                    self._current_method_index = (self._current_method_index + 1) % num_methods

                    method_queue = self._method_queues.get(method)
                    if method_queue:
                        wrapper = method_queue.popleft()
                        if not method_queue:
                            del self._method_queues[method]
                            self._method_round_robin.remove(method)
                            if self._current_method_index >= len(self._method_round_robin):
                                self._current_method_index = 0

                        priority_queue = self._queues.get(wrapper.priority)
                        if priority_queue and wrapper in priority_queue:
                            priority_queue.remove(wrapper)

                        return wrapper

            if not self._is_running:
                return None

            if deadline is not None:
                remaining = deadline - perf_counter()
                if remaining <= 0:
                    return None
                self._not_empty.wait(remaining)
            else:
                self._not_empty.wait()

    def _apply_back_pressure(self) -> bool:
        if self._drop_strategy == 'oldest_low_priority_first':
            return self._drop_oldest_low_priority()
        elif self._drop_strategy == 'oldest_first':
            return self._drop_oldest_first()
        elif self._drop_strategy == 'low_priority_first':
            return self._drop_low_priority_first()
        else:
            return self._drop_oldest_low_priority()

    def _drop_oldest_low_priority(self) -> bool:
        for priority in [EventPriority.LOW, EventPriority.NORMAL, EventPriority.HIGH]:
            queue = self._queues[priority]
            if queue:
                wrapper = queue.popleft()
                self._remove_from_method_queue(wrapper)
                self._stats.record_drop(wrapper.method, priority)
                return True
        return False

    def _drop_oldest_first(self) -> bool:
        oldest_wrapper = None
        oldest_time = float('inf')

        for priority in [EventPriority.LOW, EventPriority.NORMAL, EventPriority.HIGH, EventPriority.CRITICAL]:
            queue = self._queues[priority]
            if queue:
                wrapper = queue[0]
                if wrapper.enqueue_time < oldest_time:
                    oldest_time = wrapper.enqueue_time
                    oldest_wrapper = wrapper

        if oldest_wrapper is not None:
            self._queues[oldest_wrapper.priority].remove(oldest_wrapper)
            self._remove_from_method_queue(oldest_wrapper)
            self._stats.record_drop(oldest_wrapper.method, oldest_wrapper.priority)
            return True

        return False

    def _drop_low_priority_first(self) -> bool:
        for priority in [EventPriority.LOW, EventPriority.NORMAL, EventPriority.HIGH]:
            queue = self._queues[priority]
            if queue:
                num_to_drop = max(1, len(queue) // 10)
                for _ in range(num_to_drop):
                    if queue:
                        wrapper = queue.popleft()
                        self._remove_from_method_queue(wrapper)
                        self._stats.record_drop(wrapper.method, priority)
                return True
        return False

    def _remove_from_method_queue(self, wrapper: EventWrapper) -> None:
        method_queue = self._method_queues.get(wrapper.method)
        if method_queue and wrapper in method_queue:
            method_queue.remove(wrapper)
            if not method_queue:
                del self._method_queues[wrapper.method]
                if wrapper.method in self._method_round_robin:
                    self._method_round_robin.remove(wrapper.method)
                    if self._current_method_index >= len(self._method_round_robin):
                        self._current_method_index = 0

    def task_done(self) -> None:
        pass

    def clear(self) -> None:
        with self._lock:
            for queue in self._queues.values():
                queue.clear()
            self._method_queues.clear()
            self._method_round_robin.clear()
            self._current_method_index = 0

    def stop(self) -> None:
        with self._lock:
            self._is_running = False
            self._not_empty.notify_all()

    def get_statistics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'capacity': self._capacity,
                'current_size': self.qsize(),
                'is_full': self.full(),
                'total_enqueued': self._stats.total_enqueued,
                'total_dequeued': self._stats.total_dequeued,
                'total_dropped': self._stats.total_dropped,
                'dropped_by_priority': dict(self._stats.dropped_by_priority),
                'dropped_by_method': dict(self._stats.dropped_by_method),
                'max_wait_time_seconds': self._stats.max_wait_time,
                'average_wait_time_seconds': self._stats.get_average_wait_time(),
                'throughput_events_per_second': self._stats.get_throughput(),
                'fairness_index': self._stats.get_fairness_index(),
                'method_statistics': {
                    method: {
                        'processed': stats.processed,
                        'dropped': stats.dropped,
                        'max_wait_time': stats.max_wait_time,
                        'average_wait_time': stats.get_average_wait_time(),
                    }
                    for method, stats in self._stats.method_stats.items()
                },
            }

    def reset_statistics(self) -> None:
        with self._lock:
            self._stats.reset()


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
        self.event_queue = BackPressureEventQueue(
            capacity=_S.event_queue_capacity if hasattr(_S, 'event_queue_capacity') else 10000,
            max_wait_time_seconds=_S.event_max_wait_time if hasattr(_S, 'event_max_wait_time') else 30.0,
            drop_strategy='oldest_low_priority_first'
        )
        self.immediate_event_queue = BackPressureEventQueue(
            capacity=_S.immediate_event_queue_capacity if hasattr(_S, 'immediate_event_queue_capacity') else 1000,
            max_wait_time_seconds=5.0,
            drop_strategy='oldest_first'
        )

        self.start()

    def _send(self, message, timeout=None):
        self._cur_id += 1
        ws_id = self._cur_id
        message['id'] = ws_id
        message_json = dumps(message)

        end_time = perf_counter() + timeout if timeout is not None else None
        self.method_results[ws_id] = Queue()
        try:
            self._ws.send(message_json)
            if timeout == 0:
                self.method_results.pop(ws_id, None)
                return {'id': ws_id, 'result': {}}

        except (OSError, WebSocketConnectionClosedException):
            self.method_results.pop(ws_id, None)
            return {'error': {'message': 'connection disconnected'}, 'type': 'connection_error'}

        while self.is_running:
            try:
                result = self.method_results[ws_id].get(timeout=.2)
                self.method_results.pop(ws_id, None)
                return result

            except Empty:
                if self.alert_flag and message['method'].startswith(('Input.', 'Runtime.')):
                    return {'error': {'message': 'alert exists.'}, 'type': 'alert_exists'}

                if timeout is not None and perf_counter() > end_time:
                    self.method_results.pop(ws_id, None)
                    return {'error': {'message': 'alert exists.'}, 'type': 'alert_exists'} \
                        if self.alert_flag else {'error': {'message': 'timeout'}, 'type': 'timeout'}

                continue

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
                    self.event_queue.put(msg, msg['method'])

            elif msg.get('id') in self.method_results:
                self.method_results[msg['id']].put(msg)

    def _handle_event_loop(self):
        while self.is_running:
            try:
                result = self.event_queue.get(timeout=1)
                if result is None:
                    continue
                event, method = result
            except Empty:
                continue

            function = self.event_handlers.get(event['method'])
            if function:
                function(**event['params'])

            self.event_queue.task_done()

    def _handle_immediate_event_loop(self):
        while not self.immediate_event_queue.empty():
            result = self.immediate_event_queue.get(timeout=1)
            if result is None:
                continue
            event, method = result
            function, kwargs = event
            try:
                function(**kwargs)
            except PageDisconnectedError:
                pass

    def _handle_immediate_event(self, function, kwargs):
        self.immediate_event_queue.put((function, kwargs), '__immediate_event__')
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
        self.method_results.clear()
        self.event_queue.clear()
        self.immediate_event_queue.clear()

        self.event_queue.stop()
        self.immediate_event_queue.stop()

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
