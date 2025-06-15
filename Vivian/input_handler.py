def handle_user_input(user_input, memory, config, voice=None, vivian=None):
    user_input = user_input.strip()
    if not user_input:
        return

    if user_input.lower() in ["/help", "help"]:
        print("Commands: /help, /about, /agents, /reloadconfig, or just ask something.")
        return

    if user_input.lower() == "/about":
        print(f"{config.get('name', 'Vivian')} v{config.get('version', '1.0')} — Agentic assistant")
        return

    if vivian:
        reply = vivian.handle(user_input)
        print(f"{config.get('name', 'Vivian')}: {reply}")
        if voice and getattr(voice, "speak_enabled", False):
            voice.say(reply)
    else:
        print("Vivian is running without a brain module. Command not processed.")