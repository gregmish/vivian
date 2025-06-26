import time
import logging

PLUGIN_API_VERSION = "1.0"
state = {"count": 0, "last_used": None}

def register(register_plugin, memory_manager=None, event_bus=None, user_manager=None, permissions=None, tags=None):
    def echo(*args, user=None, async_mode=False):
        state["count"] += 1
        state["last_used"] = time.time()
        msg = " ".join(args)
        if event_bus:
            event_bus.publish("plugin_echo_used", {
                "user": user,
                "args": args,
                "timestamp": state["last_used"]
            })
        logging.info(f"[EchoPlugin] Used by {user}: {msg}")
        if async_mode:
            import asyncio
            async def async_echo():
                await asyncio.sleep(0.01)
                return msg
            return async_echo()
        return msg

    # ✅ Set plugin name for GUI display
    echo.name = "Echo"

    # ✅ Register plugin and metadata
    register_plugin("echo", echo,
        name="Echo",
        description="Echoes back whatever you say with logging and async support.",
        usage="!echo [your text]",
        permissions=permissions or ["use"],
        tags=tags or ["test", "utility"],
        author="Vivian AI",
        version=PLUGIN_API_VERSION
    )

    # ✅ Optional persistent state (if system supports it)
    if "register_plugin_state_handler" in globals():
        def get_state(): return state.copy()
        def set_state(new_state): state.update(new_state)
        register_plugin_state_handler("echo", get_state, set_state)

    # ✅ Log when events are triggered
    if event_bus:
        def echo_event_logger(event, data):
            if event == "plugin_echo_used":
                logging.info(f"[EchoPlugin][EventBus] Echo used event: {data}")
        event_bus.subscribe("plugin_echo_used", echo_event_logger)

    # ✅ Optional teardown method
    def teardown():
        logging.info("[EchoPlugin] Teardown called.")
    globals()["teardown"] = teardown