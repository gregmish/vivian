import os
import logging
import tempfile
import time
import threading
from typing import Optional, Callable, List, Dict, Any

try:
    import pyttsx3  # Text-to-speech
except ImportError:
    pyttsx3 = None

try:
    import speech_recognition as sr  # Speech-to-text
except ImportError:
    sr = None

class VoiceIO:
    """
    Vivian’s advanced voice interface.
    Features:
    - TTS with pyttsx3 (offline, customizable)
    - STT with speech_recognition (Google/other engines)
    - Configurable voice, rate, volume, language, and audio device
    - Async/background speech and listening
    - Audio file output and playback
    - EventBus integration for all actions and errors
    - Callback hooks for spoken and heard text
    - Wake word/activation phrase support
    - History/log of utterances and recognitions
    - Extensible for new TTS/STT engines or cloud APIs
    """
    def __init__(self, config: Dict[str, Any], event_bus=None):
        self.config = config
        self.event_bus = event_bus
        self.voice_enabled = config.get("voice_enabled", False)
        self.listen_enabled = config.get("speech_to_text_enabled", False)
        self.lang = config.get("voice_language", "en")
        self.voice_id = config.get("voice_id", None)
        self.wake_word = config.get("wake_word", None)
        self.engine = None
        self.sr_recognizer = sr.Recognizer() if self.listen_enabled and sr else None
        self.device_index = config.get("microphone_index", None)
        self.voice_callbacks: List[Callable[[str], None]] = []
        self.listen_callbacks: List[Callable[[str], None]] = []
        self.history: List[Dict[str, Any]] = []
        self._init_tts()
        self._init_stt()

    # --- Initialization ---
    def _init_tts(self):
        if self.voice_enabled and pyttsx3:
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", self.config.get("voice_rate", 180))
            self.engine.setProperty("volume", self.config.get("voice_volume", 1.0))
            if self.voice_id:
                try:
                    self.engine.setProperty("voice", self.voice_id)
                except Exception as e:
                    logging.warning(f"[VoiceIO] Could not set voice_id: {e}")
        elif self.voice_enabled:
            logging.warning("[VoiceIO] pyttsx3 not installed. Voice disabled.")

    def _init_stt(self):
        if self.listen_enabled and not sr:
            logging.warning("[VoiceIO] speech_recognition not installed. Listen disabled.")

    # --- TTS SPEAK ---

    def speak(self, text, background=False, save_to_file: Optional[str] = None, lang: Optional[str] = None, play_file: bool = False):
        """
        Speak text aloud using TTS.
        - Can run in background
        - Can save to audio file (wav)
        - Can auto-play audio file after saving
        - Publishes events for all actions/results/errors
        """
        if not self.voice_enabled or not pyttsx3 or not self.engine:
            logging.debug("[VoiceIO] Voice disabled or pyttsx3 missing.")
            return

        def do_speak():
            try:
                if save_to_file:
                    self.engine.save_to_file(text, save_to_file)
                    self.engine.runAndWait()
                    logging.info(f"[VoiceIO] TTS output saved to {save_to_file}")
                    self._publish_event("voice_spoken", {"text": text, "file": save_to_file})
                    self._add_history("tts", text, file=save_to_file)
                    if play_file:
                        self._play_audio_file(save_to_file)
                else:
                    self.engine.say(text)
                    self.engine.runAndWait()
                    self._publish_event("voice_spoken", {"text": text})
                    self._add_history("tts", text)
                for cb in self.voice_callbacks:
                    try:
                        cb(text)
                    except Exception as e:
                        logging.error(f"[VoiceIO] Voice callback error: {e}")
            except Exception as e:
                logging.error(f"[VoiceIO] TTS error: {e}")
                self._publish_event("voice_error", {"error": str(e), "text": text})

        if background:
            threading.Thread(target=do_speak, daemon=True).start()
        else:
            do_speak()

    # --- STT LISTEN ---

    def listen(self, timeout=5, phrase_time_limit=None, background=False, lang: Optional[str] = None, result_callback: Optional[Callable[[str], None]] = None, listen_for_wake_word: bool = False) -> Optional[str]:
        """
        Listen for speech and return text.
        - Optionally runs in a background thread (non-blocking)
        - If result_callback is provided, calls it with the result
        - If listen_for_wake_word is True, only returns when wake word is detected
        """
        if not self.listen_enabled or not sr:
            logging.debug("[VoiceIO] Listen disabled or speech_recognition missing.")
            return None

        def do_listen():
            result = ""
            try:
                with sr.Microphone(device_index=self.device_index) as source:
                    if listen_for_wake_word and self.wake_word:
                        print("🎤 Listening for wake word...")
                        while True:
                            try:
                                audio = self.sr_recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                                text = self.sr_recognizer.recognize_google(audio, language=lang or self.lang)
                                logging.debug(f"[VoiceIO] Heard: {text}")
                                if self.wake_word.lower() in text.lower():
                                    self._publish_event("wake_word_detected", {"wake_word": self.wake_word, "text": text})
                                    self._add_history("wake", text)
                                    break
                            except sr.WaitTimeoutError:
                                continue
                            except Exception as e:
                                logging.error(f"[VoiceIO] Wake word listen error: {e}")
                                continue
                    print("🎤 Listening...")
                    audio = self.sr_recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
                    chosen_lang = lang or self.lang
                    try:
                        result = self.sr_recognizer.recognize_google(audio, language=chosen_lang)
                    except sr.UnknownValueError:
                        logging.warning("[VoiceIO] Could not understand audio.")
                        self._publish_event("voice_error", {"error": "UnknownValueError"})
                    except sr.RequestError as e:
                        logging.error(f"[VoiceIO] STT API error: {e}")
                        self._publish_event("voice_error", {"error": str(e)})
                    except Exception as e:
                        logging.error(f"[VoiceIO] STT error: {e}")
                        self._publish_event("voice_error", {"error": str(e)})
                    if result:
                        self._publish_event("voice_recognized", {"text": result})
                        self._add_history("stt", result)
                        for cb in self.listen_callbacks:
                            try:
                                cb(result)
                            except Exception as e:
                                logging.error(f"[VoiceIO] Listen callback error: {e}")
                        if result_callback:
                            result_callback(result)
            except sr.WaitTimeoutError:
                logging.warning("[VoiceIO] Listen timeout.")
                self._publish_event("voice_error", {"error": "WaitTimeoutError"})
            except Exception as e:
                logging.error(f"[VoiceIO] STT error: {e}")
                self._publish_event("voice_error", {"error": str(e)})
            return result

        if background or result_callback:
            t = threading.Thread(target=do_listen, daemon=True)
            t.start()
            return None
        else:
            return do_listen()

    # --- Utility: Wake word, audio file, voice selection ---

    def get_available_voices(self):
        """List available TTS voices (id, name, language)."""
        if not self.engine:
            return []
        voices = self.engine.getProperty("voices")
        return [{"id": v.id, "name": v.name, "lang": getattr(v, "languages", ["unknown"])} for v in voices]

    def set_voice(self, voice_id: str):
        """Set the TTS voice by ID."""
        if self.engine:
            try:
                self.engine.setProperty("voice", voice_id)
                self.voice_id = voice_id
                logging.info(f"[VoiceIO] Voice set to ID: {voice_id}")
            except Exception as e:
                logging.error(f"[VoiceIO] Could not set voice: {e}")

    def set_microphone(self, mic_index: int):
        """Set the microphone device index."""
        self.device_index = mic_index

    def add_voice_callback(self, cb: Callable[[str], None]):
        """Register a callback for when text is spoken."""
        self.voice_callbacks.append(cb)

    def add_listen_callback(self, cb: Callable[[str], None]):
        """Register a callback for when speech is recognized."""
        self.listen_callbacks.append(cb)

    def _publish_event(self, event_type: str, data: Any):
        if self.event_bus:
            self.event_bus.publish(event_type, data=data, context={"module": "VoiceIO"})

    def _add_history(self, typ: str, text: str, file: Optional[str] = None):
        entry = {
            "type": typ,
            "text": text,
            "file": file,
            "timestamp": time.time()
        }
        self.history.append(entry)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def get_history(self, typ: Optional[str] = None, limit: int = 20):
        entries = self.history if typ is None else [e for e in self.history if e["type"] == typ]
        return entries[-limit:]

    def shutdown(self):
        """Cleanup on exit."""
        if self.engine:
            try:
                self.engine.stop()
            except Exception:
                pass

    def _play_audio_file(self, file_path: str):
        """Play an audio file using the system's default player."""
        try:
            import platform
            if platform.system() == "Darwin":
                os.system(f"afplay '{file_path}'")
            elif platform.system() == "Windows":
                os.system(f'start /min wmplayer "{file_path}"')
            else:  # Assume Linux/Unix
                os.system(f"aplay '{file_path}'")
        except Exception as e:
            logging.warning(f"[VoiceIO] Could not play audio file: {e}")

    # --- Interactive CLI/GUI examples ---

    def interactive_speak_listen(self):
        """Simple REPL for testing speak and listen."""
        while True:
            txt = input("Text to speak (blank to quit): ")
            if not txt:
                break
            self.speak(txt)
            resp = self.listen()
            print("Heard:", resp)

    # --- Extensibility for other TTS/STT engines ---
    # (These are placeholders for you to add custom engines, e.g. ElevenLabs, Azure, etc.)
    def register_custom_tts(self, tts_func: Callable[[str], None]):
        """Register a custom TTS function (overrides pyttsx3)."""
        self.engine = None
        self.custom_tts_func = tts_func

    def speak_custom(self, text: str):
        if hasattr(self, "custom_tts_func") and self.custom_tts_func:
            try:
                self.custom_tts_func(text)
                self._publish_event("voice_spoken", {"text": text, "engine": "custom"})
                self._add_history("tts", text)
            except Exception as e:
                logging.error(f"[VoiceIO] Custom TTS error: {e}")
                self._publish_event("voice_error", {"error": str(e), "text": text})

    def list_microphones(self) -> List[str]:
        """List available microphone device names (if supported)."""
        if not sr:
            return []
        try:
            return sr.Microphone.list_microphone_names()
        except Exception as e:
            logging.error(f"[VoiceIO] Could not list microphones: {e}")
            return []

    def test_microphone(self):
        """Test listening on all available microphones."""
        if not sr:
            print("speech_recognition not available.")
            return
        names = self.list_microphones()
        if not names:
            print("No microphones detected.")
            return
        print("Available microphones:")
        for i, n in enumerate(names):
            print(f"{i}: {n}")
        try:
            idx = int(input("Enter device index to test (or blank to quit): "))
            self.set_microphone(idx)
            print("Testing microphone...")
            result = self.listen()
            print("Heard:", result)
        except Exception as e:
            print(f"Error: {e}")

    # --- Wake Word Configuration ---

    def set_wake_word(self, word: str):
        """Set the wake word for activation."""
        self.wake_word = word

    def get_wake_word(self) -> Optional[str]:
        return self.wake_word