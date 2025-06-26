import logging
import threading
import queue
import re
from typing import Callable, Dict, List, Any, Optional, Set, Union, Pattern

class Event:
    """Represents an event with type, data, and optional context."""
    def __init__(
        self,
        event_type: str,
        data: Any = None,
        context: Optional[dict] = None,
        source: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        timestamp: Optional[float] = None,
    ):
        import time as _time
        self.type = event_type
        self.data = data
        self.context = context or {}
        self.source = source
        self.tags = tags or set()
        self.timestamp = timestamp or _time.time()

    def __repr__(self):
        return (
            f"<Event type={self.type} source={self.source} "
            f"tags={self.tags} timestamp={self.timestamp}>"
        )

class EventBus:
    """
    Advanced publish-subscribe event system for Vivian 2.0+.
    - Thread-safe subscription and publishing
    - Wildcard/pattern (regex) event subscriptions
    - Async (threaded) and sync delivery
    - Event filtering (by tag, source, etc.)
    - Once-only/one-shot subscriptions
    - Unsubscribe support
    - Persistent/event log (optional)
    - Plugin/auto-discovery support
    - Event queue/drain for deferred or batched events
    - Broadcast, bubbling, and context-passing
    - Distributed/event bus stub (future)
    - Introspection (list events, handlers, docs)
    - Plugin decorator for easy event handler registration
    """

    def __init__(self, persistent_log: Optional[str] = None, enable_async_loop: bool = False):
        self.subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self.once_subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self.global_subscribers: List[Callable[[Event], None]] = []
        self.pattern_subscribers: List[Tuple[Pattern, Callable[[Event], None]]] = []
        self.lock = threading.RLock()
        self.event_queue = queue.Queue()
        self.persistent_log = persistent_log
        self.event_log: List[Event] = []
        self.running = False
        self.enable_async_loop = enable_async_loop
        self._async_thread = None
        if enable_async_loop:
            self.start_async_loop()

    # --- Subscription methods ---

    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        """Subscribe a handler to an event type (exact match)."""
        with self.lock:
            if event_type not in self.subscribers:
                self.subscribers[event_type] = []
            self.subscribers[event_type].append(handler)
            logging.debug(f"[EventBus] Handler subscribed to event: {event_type}")

    def subscribe_pattern(self, pattern: Union[str, Pattern], handler: Callable[[Event], None]):
        """Subscribe to events matching a regex pattern."""
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        with self.lock:
            self.pattern_subscribers.append((pattern, handler))
            logging.debug(f"[EventBus] Handler subscribed to pattern: {pattern.pattern}")

    def subscribe_once(self, event_type: str, handler: Callable[[Event], None]):
        """Subscribe a handler to an event type (fires only once)."""
        with self.lock:
            if event_type not in self.once_subscribers:
                self.once_subscribers[event_type] = []
            self.once_subscribers[event_type].append(handler)
            logging.debug(f"[EventBus] One-shot handler subscribed to event: {event_type}")

    def subscribe_global(self, handler: Callable[[Event], None]):
        """Subscribe a handler to all events."""
        with self.lock:
            self.global_subscribers.append(handler)
            logging.debug(f"[EventBus] Global handler subscribed.")

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]):
        """Unsubscribe a handler from an event type."""
        with self.lock:
            if event_type in self.subscribers and handler in self.subscribers[event_type]:
                self.subscribers[event_type].remove(handler)
                logging.debug(f"[EventBus] Handler unsubscribed from event: {event_type}")
            if event_type in self.once_subscribers and handler in self.once_subscribers[event_type]:
                self.once_subscribers[event_type].remove(handler)

    def unsubscribe_pattern(self, pattern: Union[str, Pattern], handler: Callable[[Event], None]):
        """Unsubscribe handler from a regex pattern."""
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        with self.lock:
            self.pattern_subscribers = [
                (p, h) for (p, h) in self.pattern_subscribers
                if not (p.pattern == pattern.pattern and h == handler)
            ]

    def unsubscribe_global(self, handler: Callable[[Event], None]):
        """Unsubscribe a global handler."""
        with self.lock:
            if handler in self.global_subscribers:
                self.global_subscribers.remove(handler)

    def clear(self):
        """Remove all subscribers."""
        with self.lock:
            self.subscribers.clear()
            self.once_subscribers.clear()
            self.global_subscribers.clear()
            self.pattern_subscribers.clear()

    # --- Publishing methods ---

    def publish(
        self,
        event_type: str,
        data: Any = None,
        context: Optional[dict] = None,
        async_: bool = False,
        source: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ):
        """
        Publish an event to all subscribed handlers.
        If async_ is True, handlers are called in new threads.
        All global handlers receive all events.
        Also matches pattern and wildcard subscribers.
        """
        event = Event(event_type, data, context, source, tags)
        self._record_event(event)
        handlers = []
        global_handlers = []
        pattern_handlers = []

        with self.lock:
            handlers = list(self.subscribers.get(event_type, []))
            once_handlers = list(self.once_subscribers.get(event_type, []))
            global_handlers = list(self.global_subscribers)
            for pattern, handler in self.pattern_subscribers:
                if pattern.match(event_type):
                    pattern_handlers.append(handler)

        # Fire regular handlers
        for handler in handlers:
            self._dispatch(handler, event, async_=async_)

        # Fire once-only handlers then remove them
        for handler in once_handlers:
            self._dispatch(handler, event, async_=async_)
            self.unsubscribe(event_type, handler)

        # Fire global handlers
        for handler in global_handlers:
            self._dispatch(handler, event, async_=async_)

        # Fire pattern (wildcard/regex) handlers
        for handler in pattern_handlers:
            self._dispatch(handler, event, async_=async_)

        # Emit compliance/audit hooks for GDPR, etc.
        if event_type in {"gdpr_export", "gdpr_delete"}:
            self._compliance_audit_hook(event)

    def _dispatch(self, handler: Callable[[Event], None], event: Event, async_: bool = False):
        try:
            if async_:
                t = threading.Thread(target=handler, args=(event,))
                t.daemon = True
                t.start()
            else:
                handler(event)
        except Exception as e:
            logging.error(f"[EventBus] Error in handler for '{event.type}': {e}")

    # --- Event queue/drain for deferred/batched events ---

    def queue_event(
        self,
        event_type: str,
        data: Any = None,
        context: Optional[dict] = None,
        source: Optional[str] = None,
        tags: Optional[Set[str]] = None,
    ):
        """Queue an event for later draining."""
        event = Event(event_type, data, context, source, tags)
        self.event_queue.put(event)
        self._record_event(event)

    def drain(self, async_: bool = False):
        """Drain the event queue, publishing all queued events."""
        while not self.event_queue.empty():
            event = self.event_queue.get()
            self.publish(
                event.type,
                event.data,
                event.context,
                async_=async_,
                source=event.source,
                tags=event.tags,
            )

    # --- Async event loop (background processing for high-throughput/deferred events) ---

    def start_async_loop(self):
        """Start background thread to process queued events."""
        if not self.running:
            self.running = True
            self._async_thread = threading.Thread(target=self._async_loop, daemon=True)
            self._async_thread.start()
            logging.info("[EventBus] Async event processing loop started.")

    def stop_async_loop(self):
        """Stop the background event processing thread."""
        self.running = False
        if self._async_thread:
            self._async_thread.join(timeout=2)
            logging.info("[EventBus] Async event processing loop stopped.")

    def _async_loop(self):
        while self.running:
            try:
                event = self.event_queue.get(timeout=0.5)
                self.publish(
                    event.type,
                    event.data,
                    event.context,
                    async_=True,
                    source=event.source,
                    tags=event.tags,
                )
            except queue.Empty:
                continue

    # --- Persistent log support ---

    def _record_event(self, event: Event):
        """Optionally record events to memory and persistent log."""
        self.event_log.append(event)
        if self.persistent_log:
            try:
                with open(self.persistent_log, "a", encoding="utf-8") as f:
                    line = {
                        "type": event.type,
                        "data": event.data,
                        "context": event.context,
                        "source": event.source,
                        "tags": list(event.tags) if event.tags else [],
                        "timestamp": event.timestamp,
                    }
                    import json
                    f.write(json.dumps(line) + "\n")
            except Exception as e:
                logging.error(f"[EventBus] Failed to write event log: {e}")

    # --- Introspection/utility ---

    def list_event_types(self) -> List[str]:
        with self.lock:
            return sorted(list(set(self.subscribers) | set(self.once_subscribers)))

    def list_subscribers(self, event_type: Optional[str] = None) -> List[Callable]:
        with self.lock:
            if event_type:
                return list(self.subscribers.get(event_type, [])) + list(self.once_subscribers.get(event_type, []))
            else:
                all_handlers = []
                for handlers in list(self.subscribers.values()) + list(self.once_subscribers.values()):
                    all_handlers.extend(handlers)
                all_handlers.extend(self.global_subscribers)
                all_handlers.extend(handler for _, handler in self.pattern_subscribers)
                return all_handlers

    def list_event_log(self, limit: int = 50) -> List[Event]:
        return self.event_log[-limit:]

    def list_pattern_subscriptions(self) -> List[str]:
        with self.lock:
            return [p.pattern for p, _ in self.pattern_subscribers]

    def list_all_handlers(self) -> Dict[str, List[str]]:
        with self.lock:
            result = {}
            for event_type, handlers in self.subscribers.items():
                result[event_type] = [repr(h) for h in handlers]
            result["global"] = [repr(h) for h in self.global_subscribers]
            result["pattern"] = [p.pattern for p, _ in self.pattern_subscribers]
            return result

    # --- Plugin/event auto-discovery support ---

    def auto_discover_plugins(self, plugin_loader: Optional[Callable] = None):
        """
        Optionally call a plugin loader to auto-register event handlers.
        """
        if plugin_loader:
            plugin_loader(self)

    # --- Broadcast/event bubbling (for future expansion) ---

    def broadcast(self, event_type: str, data: Any = None, context: Optional[dict] = None):
        """
        Send an event to all handlers, regardless of event type.
        """
        event = Event(event_type, data, context)
        with self.lock:
            for handler in self.global_subscribers:
                self._dispatch(handler, event, async_=False)
            for handlers in self.subscribers.values():
                for handler in handlers:
                    self._dispatch(handler, event, async_=False)
            for handlers in self.once_subscribers.values():
                for handler in handlers:
                    self._dispatch(handler, event, async_=False)
            for _, handler in self.pattern_subscribers:
                self._dispatch(handler, event, async_=False)

    # --- Distributed/event bus API stub (future) ---

    def enable_distributed(self, backend: str = "redis", **kwargs):
        """Stub: Enable distributed event bus (future - Redis, Kafka, Websockets, etc.)"""
        logging.warning("[EventBus] Distributed mode is not implemented yet (stub).")
        # Future: Initialize connection to backend, publish/subscribe, etc.
        pass

    # --- Graceful shutdown (for async events) ---

    def shutdown(self):
        self.running = False
        if self.enable_async_loop:
            self.stop_async_loop()

    # --- Compliance/audit hooks ---

    def _compliance_audit_hook(self, event: Event):
        # Example: log, notify, or trigger compliance workflows for GDPR events
        logging.info(f"[EventBus][Compliance] Compliance event: {event.type} {event.data}")

    # --- Plugin decorator for event handlers ---

    @staticmethod
    def event_handler(event_type: Union[str, Pattern, List[Union[str, Pattern]]], pattern: bool = False):
        """Decorator to easily register plugin event handlers."""
        def decorator(func):
            func._event_handler_info = (event_type, pattern)
            return func
        return decorator

    # --- Automatic event documentation ---

    def document_events(self) -> str:
        """Return Markdown listing of all event types, patterns, and handlers."""
        with self.lock:
            lines = ["# EventBus Registered Events & Handlers\n"]
            if self.subscribers:
                lines.append("## Exact Event Types:")
                for et, hs in self.subscribers.items():
                    lines.append(f"- `{et}`: {len(hs)} handler(s)")
            if self.pattern_subscribers:
                lines.append("## Pattern Subscriptions:")
                for p, h in self.pattern_subscribers:
                    lines.append(f"- `{p.pattern}`: {repr(h)}")
            if self.global_subscribers:
                lines.append("## Global Subscribers:")
                for h in self.global_subscribers:
                    lines.append(f"- {repr(h)}")
            return "\n".join(lines)

# --- Integration helpers for Vivian Core Components ---

def integrate_eventbus_with_vivian(user_manager, command_module, memory=None, logger=None, plugin_loader=None, enable_async_loop=False):
    """
    Connects the EventBus to major Vivian subsystems, with plugin/event auto-discovery.
    Returns the EventBus instance.
    """
    bus = EventBus(persistent_log="logs/event_log.jsonl", enable_async_loop=enable_async_loop)

    # User Events
    def on_user_registered(event: Event):
        if logger:
            logger.info(f"[Vivian] User registered: {event.data}")
        bus.publish(
            "system_message",
            data={"msg": f"Welcome new user: {event.data.get('username', event.data)}"},
            context={"user": event.data.get("username")},
        )

    def on_user_login(event: Event):
        if logger:
            logger.info(f"[Vivian] User logged in: {event.data}")

    bus.subscribe("user_registered", on_user_registered)
    bus.subscribe("user_login", on_user_login)

    # Command Events
    def on_command_executed(event: Event):
        cmd_entry = {
            "user": event.context.get("user", "unknown"),
            "command": event.data.get("command"),
            "args": event.data.get("args"),
            "result": event.data.get("result"),
            "success": event.data.get("success"),
            "timestamp": event.data.get("timestamp"),
        }
        if logger:
            logger.info(f"[Vivian] Command executed: {cmd_entry}")

    bus.subscribe("command_executed", on_command_executed)

    # Memory Events (if applicable)
    if memory:
        def on_memory_updated(event: Event):
            if logger:
                logger.info(f"[Vivian] Memory updated: {event.data}")

        bus.subscribe("memory_updated", on_memory_updated)
        # Wildcard subscription example:
        bus.subscribe_pattern(r"^memory_", lambda event: logger and logger.info(f"[Vivian] Memory event: {event.type} {event.data}"))

    # System/Shutdown Events
    def on_shutdown(event: Event):
        if logger:
            logger.info("[Vivian] Shutting down. Draining event queue.")
        bus.drain(async_=False)
    bus.subscribe("system_shutdown", on_shutdown)

    # Plugin/event auto-discovery
    if plugin_loader:
        bus.auto_discover_plugins(plugin_loader)

    return bus

# --- Example Usage/Integration (for reference; remove/comment for production) ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    bus = EventBus(persistent_log="logs/event_log.jsonl", enable_async_loop=True)

    def demo_handler(event: Event):
        print(f"Demo handler received: {event}")

    # Subscribe handlers
    bus.subscribe("demo_event", demo_handler)
    bus.subscribe_once("demo_event", lambda e: print(f"One-shot: {e}"))
    bus.subscribe_global(lambda e: print(f"Global handler: {e.type}"))
    bus.subscribe_pattern(r"^demo_", lambda e: print(f"Pattern handler: {e.type}"))

    # Publish events
    bus.publish("demo_event", data={"foo": "bar"}, context={"user": "test"}, async_=False)
    bus.publish("demo_event", data={"foo": "baz"}, async_=True)
    bus.publish("demo_special", data={"baz": 123})

    # Queue and drain events
    bus.queue_event("queued_event", data="Deferred hello")
    bus.drain()

    # List introspection
    print("Event types:", bus.list_event_types())
    print("Recent event log:", bus.list_event_log())
    print(bus.document_events())