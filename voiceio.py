import pyttsx3

# Optionals for upgrades
try:
    import speech_recognition as sr
except ImportError:
    sr = None

import threading
import tempfile
import os

class VoiceIO:
    """
    Ultimate VoiceIO:
    - Speech synthesis (TTS) with dynamic voice, language, persona, rate, volume
    - Speech recognition (voice-to-text)
    - Multi-language, multi-voice, emotion, and expressivity (if engine supports)
    - Feedback, rating, and auto-adaptation
    - Streaming/interruption support
    - Audio recording/export
    - Voice command shortcuts
    - GUI hooks, accessibility, and compliance stubs
    - Security: auto-mute on sensitive content
    """
    def __init__(
        self,
        rate=160,
        volume=1.0,
        voice_name=None,
        speak_enabled=True,
        language=None,
        emotion=None,
        on_speech_start=None,
        on_speech_end=None,
        feedback_callback=None,
        enable_recognition=True,
        privacy_filter=None,
        accessibility_callback=None,
        gui_callback=None,
    ):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", volume)
        self.speak_enabled = speak_enabled
        self.current_voice = None
        self.language = language
        self.emotion = emotion
        self.feedback_callback = feedback_callback
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end
        self.privacy_filter = privacy_filter
        self.accessibility_callback = accessibility_callback
        self.gui_callback = gui_callback
        self.recognizer = sr.Recognizer() if (sr and enable_recognition) else None
        self.mic = sr.Microphone() if (sr and enable_recognition) else None
        self.audio_recordings = []
        self.is_speaking = False
        self.interrupt_flag = False

        # Set initial voice by name if provided
        if voice_name:
            self.set_voice(voice_name)
        elif language:
            self.set_voice_by_language(language)

    # --- TTS Core ---
    def set_voice(self, voice_name):
        for voice in self.engine.getProperty("voices"):
            if voice_name.lower() in (voice.name or "").lower():
                self.engine.setProperty("voice", voice.id)
                self.current_voice = voice
                return True
        return False

    def set_voice_by_language(self, language_code):
        for voice in self.engine.getProperty("voices"):
            if hasattr(voice, "languages") and language_code in str(voice.languages):
                self.engine.setProperty("voice", voice.id)
                self.current_voice = voice
                return True
            if language_code in (voice.name or ""):
                self.engine.setProperty("voice", voice.id)
                self.current_voice = voice
                return True
        return False

    def set_emotion(self, emotion):
        # Only supported on certain TTS engines (stub)
        self.emotion = emotion

    def set_rate(self, rate):
        self.engine.setProperty("rate", rate)

    def set_volume(self, volume):
        self.engine.setProperty("volume", volume)

    def enable(self):
        self.speak_enabled = True

    def disable(self):
        self.speak_enabled = False

    def voices(self):
        return [voice.name for voice in self.engine.getProperty("voices")]

    def speak(self, text, wait=True, record=False):
        if not text or not self.speak_enabled:
            return
        # Security/privacy filter: block sensitive
        if self.privacy_filter and not self.privacy_filter(text):
            print("[VoiceIO] Output blocked for privacy.")
            return
        # Accessibility: captions, visual feedback
        if self.accessibility_callback:
            self.accessibility_callback(text)
        # GUI: visualize TTS (mouth, waveform, etc.)
        if self.gui_callback:
            self.gui_callback("speak", text)
        # Event
        if self.on_speech_start:
            self.on_speech_start(text)
        self.is_speaking = True
        self.interrupt_flag = False
        if record:
            # Save to temp wav file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tf:
                self.engine.save_to_file(text, tf.name)
                self.engine.runAndWait()
                self.audio_recordings.append(tf.name)
        else:
            def run():
                self.engine.say(text)
                self.engine.runAndWait()
                self.is_speaking = False
                if self.on_speech_end:
                    self.on_speech_end(text)
            if wait:
                run()
            else:
                t = threading.Thread(target=run)
                t.start()

    def stop(self):
        self.interrupt_flag = True
        self.engine.stop()
        self.is_speaking = False

    def repeat(self, last_text, **kwargs):
        self.speak(last_text, **kwargs)

    # --- Speech Recognition (Voice-to-Text) ---
    def listen(self, timeout=5, phrase_time_limit=None, language=None, on_result=None):
        if not self.recognizer or not self.mic:
            print("Speech recognition not installed or enabled.")
            return None
        with self.mic as source:
            self.recognizer.adjust_for_ambient_noise(source)
            print("Listening...")
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except Exception as e:
                print(f"[VoiceIO] Listen error: {e}")
                return None
        try:
            # Language detection/switching
            recog_lang = language or self.language or "en-US"
            text = self.recognizer.recognize_google(audio, language=recog_lang)
            if on_result:
                on_result(text)
            return text
        except sr.UnknownValueError:
            print("Could not understand audio.")
        except sr.RequestError as e:
            print(f"Recognition error: {e}")
        return None

    def listen_command(self, *args, **kwargs):
        # Recognize voice commands like "stop", "repeat", etc.
        text = self.listen(*args, **kwargs)
        if not text:
            return None
        cmd = text.lower().strip()
        # Shortcuts
        if cmd in ["stop", "cancel"]:
            self.stop()
            print("[VoiceIO] Speech stopped by command.")
            return "stop"
        if cmd in ["repeat", "say again"]:
            print("[VoiceIO] Repeat command triggered.")
            return "repeat"
        if cmd.startswith("rate "):
            try:
                rate = int(cmd.split(" ")[1])
                self.set_rate(rate)
                print(f"[VoiceIO] Rate set to {rate}")
            except Exception:
                pass
            return "set_rate"
        if cmd.startswith("volume "):
            try:
                vol = float(cmd.split(" ")[1])
                self.set_volume(vol)
                print(f"[VoiceIO] Volume set to {vol}")
            except Exception:
                pass
            return "set_volume"
        return cmd

    # --- Audio Recording/Export ---
    def export_audio(self, index=-1, path=None):
        # Export last or all recordings
        if not self.audio_recordings:
            print("No recordings available.")
            return None
        files = self.audio_recordings if index == "all" else [self.audio_recordings[index]]
        exported = []
        for f in files:
            target = path or f"exported_{os.path.basename(f)}"
            os.rename(f, target)
            exported.append(target)
        return exported

    # --- Feedback/Rating ---
    def feedback(self, text, rating=None):
        if self.feedback_callback:
            self.feedback_callback(text, rating)
        # Could store or send to analytics, adapt rate/volume/voice in future

    # --- Accessibility/Compliance Enhancements ---
    def describe_image(self, image_path):
        # Stub: describe image for vision impaired
        print(f"[VoiceIO] (Stub) Describing image: {image_path}")

    def auto_describe(self, content):
        # Stub: auto-describe files, diagrams, etc.
        print(f"[VoiceIO] (Stub) Describing content: {content}")

    # --- Security/Privacy ---
    def set_privacy_filter(self, func):
        self.privacy_filter = func

    # --- GUI/Visualization Hooks ---
    def set_gui_callback(self, func):
        self.gui_callback = func

    # --- Emotion/Expressivity ---
    def set_emotion(self, emotion):
        # Only supported on some engines (stub)
        self.emotion = emotion

    # --- Multi-speaker/Agentic ---
    def set_agent_voice(self, agent_name):
        # Map agent names to different voices if desired (stub)
        pass

    # --- Utility ---
    def status(self):
        return {
            "enabled": self.speak_enabled,
            "current_voice": self.current_voice.name if self.current_voice else None,
            "language": self.language,
            "emotion": self.emotion,
            "is_speaking": self.is_speaking,
            "recordings": len(self.audio_recordings),
        }