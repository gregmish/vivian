import threading
import datetime
import traceback
import json
import os

class EventBus:
    def __init__(self, audit_fn=None, persistent_log=None, enable_async_loop=False):
        self.listeners = {}   # event_name: set(callables)
        self._wildcard = set() # listeners for '*'
        self.history = []     # [(timestamp, event, data)]
        self.lock = threading.Lock()
        self.audit_fn = audit_fn

        # NEW:
        self.persistent_log = persistent_log
        self.enable_async_loop = enable_async_loop
        if self.persistent_log:
            os.makedirs(os.path.dirname(self.persistent_log), exist_ok=True)

    def subscribe(self, event_name, callback, async_listener=False):
        with self.lock:
            if event_name == "*":
                self._wildcard.add((callback, async_listener))
            else:
                if event_name not in self.listeners:
                    self.listeners[event_name] = set()
                self.listeners[event_name].add((callback, async_listener))

    def unsubscribe(self, event_name, callback):
        with self.lock:
            if event_name == "*":
                self._wildcard = {(cb, a) for (cb, a) in self._wildcard if cb != callback}
            elif event_name in self.listeners:
                self.listeners[event_name] = {(cb, a) for (cb, a) in self.listeners[event_name] if cb != callback}
                if not self.listeners[event_name]:
                    del self.listeners[event_name]

    def publish(self, event_name, data=None, meta=None):
        event = {
            "time": datetime.datetime.utcnow().isoformat(),
            "event": event_name,
            "data": data,
            "meta": meta or {}
        }

        with self.lock:
            self.history.append(event)
            listeners = list(self.listeners.get(event_name, [])) + list(self._wildcard)

        # Save to persistent log if set
        if self.persistent_log:
            try:
                with open(self.persistent_log, "a", encoding="utf-8") as f:
                    json.dump(event, f)
                    f.write("\n")
            except Exception as e:
                print(f"[EventBus] Failed to log event: {e}")

        if self.audit_fn:
            try:
                self.audit_fn("eventbus_publish", event)
            except Exception:
                pass

        for callback, run_async in listeners:
            try:
                if run_async:
                    threading.Thread(target=callback, args=(event_name, data, meta), daemon=True).start()
                else:
                    callback(event_name, data, meta)
            except Exception:
                err_event = {
                    "event": "eventbus_listener_error",
                    "listener": str(callback),
                    "event_name": event_name,
                    "traceback": traceback.format_exc()
                }
                with self.lock:
                    self.history.append(err_event)

    def publish_async(self, event_name, data=None, meta=None):
        threading.Thread(target=self.publish, args=(event_name, data, meta), daemon=True).start()

    def get_history(self, limit=50, event_name=None, since=None, filter_fn=None):
        with self.lock:
            events = self.history[-limit*2:] if limit else list(self.history)
        if event_name:
            events = [e for e in events if e.get("event") == event_name]
        if since:
            events = [e for e in events if e.get("time") and e["time"] > since]
        if filter_fn:
            events = [e for e in events if filter_fn(e)]
        return events[-limit:] if limit else events

    def replay(self, event_name, callback, limit=50):
        for event in self.get_history(limit=limit, event_name=event_name):
            try:
                callback(event["event"], event.get("data"), event.get("meta"))
            except Exception:
                pass

    def clear_history(self):
        with self.lock:
            self.history.clear()

    def forward_to_remote(self, event_name, data=None, meta=None):
        pass

    def validate_event(self, event_name, data):
        return True
