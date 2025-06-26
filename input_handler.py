import datetime

def handle_user_input(
    user_input,
    memory,
    config,
    voice=None,
    vivian=None,
    multimodal=None,
    user_profile=None,
    session_manager=None,
    agent_registry=None,
    plugin_registry=None,
    skill_store=None,
    feedback_db=None,
    audit_log=None,
    cost_tracker=None,
    gui=None,
):
    user_input = user_input.strip()
    if not user_input:
        return

    lower = user_input.lower()

    # 1. Help and About
    if lower in ["/help", "help", "what can you do", "list commands"]:
        print(
            "Commands: /help, /about, /agents, /reloadconfig, /trace, /feedback, /session, /plugins, /skills, /cost, /voice, /persona, /history, /memory, /audit, /export, /summarize, /reset, /marketplace, /upgrade, or just ask something."
        )
        return

    if lower == "/about":
        print(f"{config.get('name', 'Vivian')} v{config.get('version', '1.0')} — Agentic assistant")
        return

    # 2. Agent/Skill/Plugin/Marketplace Management
    if lower in ["/agents", "list agents"]:
        if agent_registry:
            print("Available agents:", ", ".join(agent_registry.keys()))
        else:
            print("No agent registry loaded.")
        return

    if lower in ["/skills", "list skills"]:
        if skill_store:
            print("Available skills:", ", ".join(skill_store.keys()))
        else:
            print("No skill store loaded.")
        return

    if lower in ["/plugins", "list plugins"]:
        if plugin_registry:
            print("Plugins:", ", ".join(plugin_registry.keys()))
        else:
            print("No plugin registry loaded.")
        return

    if lower.startswith("/marketplace"):
        print("Skill/plugin marketplace: coming soon! (Download and manage new skills/plugins here.)")
        return

    # 3. Config/Upgrade Management
    if lower.startswith("/reloadconfig"):
        config.load()
        print("Config reloaded.")
        return

    if lower.startswith("/upgrade"):
        print("Vivian will auto-update from the latest agent, skill, and plugin sources (not implemented in this stub).")
        return

    # 4. Session/Context/Persona Management
    if lower.startswith("/session"):
        if session_manager:
            cmd = user_input.split(maxsplit=1)[-1] if " " in user_input else ""
            session_manager.handle_command(cmd)
            return
        print("Session manager is not enabled.")
        return

    if lower.startswith("/persona"):
        persona = user_input[len("/persona"):].strip()
        if vivian:
            vivian.persona_profile = persona or vivian.persona_profile
            print(f"Persona set to: {vivian.persona_profile}")
        else:
            print("No brain loaded.")
        return

    # 5. Memory/History/Trace/Audit/Export
    if lower.startswith("/history"):
        print("Conversation History:")
        for h in (vivian.get_history() if vivian else memory):
            print(f"{h['role']}: {h['content']}")
        return

    if lower.startswith("/memory"):
        print("Memory:")
        mem = vivian.get_memory() if vivian else memory
        for m in mem:
            print(m)
        return

    if lower.startswith("/trace"):
        if vivian:
            trace = vivian.get_trace()
            print("Trace:", trace)
        else:
            print("No brain loaded.")
        return

    if lower.startswith("/audit"):
        if audit_log:
            print("Audit Log:")
            for a in audit_log:
                print(a)
        else:
            print("No audit log.")
        return

    if lower.startswith("/export"):
        if vivian:
            print("Exporting session (copy/paste):")
            print(vivian.get_history())
        else:
            print("No brain loaded.")
        return

    if lower.startswith("/summarize"):
        if vivian and hasattr(vivian, "summarize"):
            summary = vivian.summarize()
            print("Session Summary:", summary)
        else:
            print("Summary not available.")
        return

    # 6. Feedback/Cost/Voice
    if lower.startswith("/feedback"):
        feedback = user_input[len("/feedback"):].strip()
        if vivian:
            vivian.get_feedback().append({"feedback": feedback, "timestamp": str(datetime.datetime.utcnow())})
            print("Feedback recorded.")
        else:
            print("No brain loaded.")
        return

    if lower.startswith("/cost"):
        if cost_tracker:
            print("Usage/cost so far:", cost_tracker.get_report())
        else:
            print("No cost tracker loaded.")
        return

    if lower.startswith("/voice"):
        if voice:
            if "off" in lower:
                voice.speak_enabled = False
                print("Voice disabled.")
            elif "on" in lower:
                voice.speak_enabled = True
                print("Voice enabled.")
            else:
                print("Voice status:", "On" if getattr(voice, "speak_enabled", False) else "Off")
        else:
            print("No voice module loaded.")
        return

    # 7. Reset/Session/Topic Switching
    if lower.startswith("/reset"):
        if vivian:
            vivian.reset()
            print("Session reset.")
        else:
            print("No brain loaded.")
        return

    if lower.startswith("/topic"):
        topic = user_input[len("/topic"):].strip()
        if session_manager:
            session_manager.switch_topic(topic)
            print(f"Switched topic to {topic}")
        else:
            print("No session manager loaded.")
        return

    # 8. Multimodal Input
    if multimodal and multimodal.detect(user_input):
        multimodal.handle(user_input)
        return

    # 9. Agent/Skill/Plugin Dispatch
    if lower.startswith("agent:"):
        agent_name, _, msg = user_input.partition(":")[2].partition(" ")
        if agent_registry and agent_name in agent_registry:
            reply = agent_registry[agent_name].ask(msg)
            print(f"{agent_name}: {reply}")
            return

    if lower.startswith("plugin:"):
        plugin_name, _, msg = user_input.partition(":")[2].partition(" ")
        if plugin_registry and plugin_name in plugin_registry:
            output = plugin_registry[plugin_name](msg)
            print(f"{plugin_name}: {output}")
            return

    if lower.startswith("skill:"):
        skill_name, _, msg = user_input.partition(":")[2].partition(" ")
        if skill_store and skill_name in skill_store:
            output = skill_store[skill_name](msg)
            print(f"{skill_name}: {output}")
            return

    # 10. Feedback Loop/Correction
    if lower.startswith("that was wrong") or lower.startswith("correct:"):
        correction = user_input.partition(":")[2].strip() or user_input
        if feedback_db is not None:
            feedback_db.append({"correction": correction, "timestamp": str(datetime.datetime.utcnow())})
            print("Correction recorded.")
        return

    # 11. GUI/WebSocket/Collaboration (stub)
    if lower.startswith("/gui"):
        if gui:
            gui.open()
            print("GUI opened.")
        else:
            print("No GUI available.")
        return

    # 12. Main AI/brain invocation (all orchestration enabled)
    if vivian:
        reply = vivian.ask(
            user_input,
            user_profile=user_profile,
            multimodal_input=multimodal.current_input if multimodal else None,
            agents=agent_registry,
            plugin_tools=plugin_registry,
            skill_store=skill_store,
            feedback_db=feedback_db,
            session_manager=session_manager,
            audit_log=audit_log,
            cost_tracker=cost_tracker,
            gui=gui,
        )
        answer = reply["answer"] if isinstance(reply, dict) and "answer" in reply else reply
        print(f"{config.get('name', 'Vivian')}: {answer}")
        if voice and getattr(voice, "speak_enabled", False):
            voice.say(answer)
    else:
        print("Vivian is running without a brain module. Command not processed.")