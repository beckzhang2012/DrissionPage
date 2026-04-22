# -*- coding:utf-8 -*-
"""
@Author   : g1879
@Contact  : g1879@qq.com
@Website  : https://DrissionPage.cn
@Copyright: (c) 2020 by g1879, Inc. All Rights Reserved.

Tab Lifecycle Statistics for race condition observability
Tracks dropped events, tab state transitions, and context validation.
"""
from collections import defaultdict
from datetime import datetime
from threading import Lock
from typing import Dict, Optional, Set


class TabLifecycleStats:
    _instance: Optional['TabLifecycleStats'] = None
    _lock: Lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._lock = Lock()
        
        self.dropped_events: Dict[str, int] = defaultdict(int)
        self.dropped_events_by_tab: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        self.tab_state_transitions: Dict[str, list] = defaultdict(list)
        self.tab_alive_status: Dict[str, bool] = {}
        
        self.event_hits_by_tab: Dict[str, int] = defaultdict(int)
        self.event_validated_by_tab: Dict[str, int] = defaultdict(int)
        
        self.session_id_mappings: Dict[str, str] = {}
        
        self.exit_code: int = 0
        self.start_time: datetime = datetime.now()

    def record_dropped_event(self, event_method: str, tab_id: Optional[str] = None, 
                               reason: str = 'invalid_context'):
        with self._lock:
            key = f"{event_method}:{reason}"
            self.dropped_events[key] += 1
            if tab_id:
                self.dropped_events_by_tab[tab_id][key] += 1

    def record_tab_state_change(self, tab_id: str, state: str, details: Optional[dict] = None):
        with self._lock:
            transition = {
                'timestamp': datetime.now(),
                'state': state,
                'details': details or {}
            }
            self.tab_state_transitions[tab_id].append(transition)
            
            if state == 'created':
                self.tab_alive_status[tab_id] = True
            elif state in ('closed', 'destroyed', 'disconnected'):
                self.tab_alive_status[tab_id] = False

    def is_tab_alive(self, tab_id: str) -> bool:
        with self._lock:
            return self.tab_alive_status.get(tab_id, False)

    def record_event_hit(self, tab_id: str):
        with self._lock:
            self.event_hits_by_tab[tab_id] += 1

    def record_event_validated(self, tab_id: str):
        with self._lock:
            self.event_validated_by_tab[tab_id] += 1

    def bind_session_to_tab(self, tab_id: str, session_id: str):
        with self._lock:
            self.session_id_mappings[tab_id] = session_id

    def unbind_session_from_tab(self, tab_id: str):
        with self._lock:
            self.session_id_mappings.pop(tab_id, None)

    def get_session_for_tab(self, tab_id: str) -> Optional[str]:
        with self._lock:
            return self.session_id_mappings.get(tab_id)

    def set_exit_code(self, code: int):
        with self._lock:
            self.exit_code = code

    def get_summary(self) -> dict:
        with self._lock:
            total_dropped = sum(self.dropped_events.values())
            total_hits = sum(self.event_hits_by_tab.values())
            total_validated = sum(self.event_validated_by_tab.values())
            
            alive_tabs = {k: v for k, v in self.tab_alive_status.items() if v}
            dead_tabs = {k: v for k, v in self.tab_alive_status.items() if not v}
            
            return {
                'exit_code': self.exit_code,
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
                'events': {
                    'total_hits': total_hits,
                    'total_validated': total_validated,
                    'total_dropped': total_dropped,
                    'dropped_by_type': dict(self.dropped_events),
                    'dropped_by_tab': {k: dict(v) for k, v in self.dropped_events_by_tab.items()},
                    'hits_by_tab': dict(self.event_hits_by_tab),
                    'validated_by_tab': dict(self.event_validated_by_tab),
                },
                'tabs': {
                    'total_tracked': len(self.tab_alive_status),
                    'alive_count': len(alive_tabs),
                    'dead_count': len(dead_tabs),
                    'alive_tabs': list(alive_tabs.keys()),
                    'dead_tabs': list(dead_tabs.keys()),
                },
                'session_mappings': dict(self.session_id_mappings),
            }

    def reset(self):
        with self._lock:
            self.dropped_events.clear()
            self.dropped_events_by_tab.clear()
            self.tab_state_transitions.clear()
            self.tab_alive_status.clear()
            self.event_hits_by_tab.clear()
            self.event_validated_by_tab.clear()
            self.session_id_mappings.clear()
            self.exit_code = 0
            self.start_time = datetime.now()


lifecycle_stats = TabLifecycleStats()
