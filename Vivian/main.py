
def main():
    global user_manager
    config = load_config()
    user_manager = UserManager(config)
    memory = MemoryManager(config, event_bus=EventBus())
    voice = VoiceIO(config, event_bus=None)
    agents = start_agents(config, memory, EventBus())

    if server_supported():
        run_server(config, memory, EventBus())

    if gui_supported():
        run_gui()

    while True:
        user_input = input("Vivian > ")
        response = handle_user_input(user_input, config, memory, EventBus())
        print(response)

if __name__ == "__main__":
    main()
