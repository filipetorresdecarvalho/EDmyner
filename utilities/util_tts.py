# tts_handler.py
import logging
from threading import Thread
from typing import List, Dict, Any
from core.core_database import load_config



logger = logging.getLogger(__name__)

class TTSHandler:
    """Handle text-to-speech functionality."""

    def __init__(self):
        """Initialize TTS engine."""
        self.engine = None
        self.enabled = True
        self.current_voice_id = None
        self.available_voices = []
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 1.0)
            self.available_voices = self.engine.getProperty('voices')
            if self.available_voices:
                self.current_voice_id = self.available_voices[0].id
                logger.info(f"TTS engine initialized with {len(self.available_voices)} voices")
            else:
                logger.warning("TTS engine initialized but no voices found")
        except Exception as e:
            logger.error(f"TTS initialization error: {e}")
            self.enabled = False

    def get_available_voices(self) -> List[Dict[str, str]]:
        voices = []
        if self.engine and self.available_voices:
            for voice in self.available_voices:
                name = voice.name
                if "Microsoft" in name:
                    name = name.replace("Microsoft ", "").split(" - ")[0]
                voices.append({
                    'id': voice.id,
                    'name': name,
                    'full_name': voice.name
                })
        return voices

    def set_voice(self, voice_id: str) -> None:
        if self.engine and self.enabled:
            try:
                self.engine.setProperty('voice', voice_id)
                self.current_voice_id = voice_id
                logger.info(f"TTS voice changed to: {voice_id}")
            except Exception as e:
                logger.error(f"Error setting TTS voice: {e}")

    def set_speed(self, speed: int) -> None:
        if self.engine and self.enabled:
            try:
                speed = max(50, min(300, speed))
                self.engine.setProperty('rate', speed)
                logger.debug(f"TTS speed set to: {speed}")
            except Exception as e:
                logger.error(f"Error setting TTS speed: {e}")

    def speak(self, text: str) -> None:
        """Speak text in a background thread."""
        if not self.engine or not self.enabled:
            logger.info(f"TTS (disabled): {text}")
            return

        def speak_thread():
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', self.engine.getProperty('rate'))
                engine.setProperty('volume', self.engine.getProperty('volume'))
                if self.current_voice_id:
                    try:
                        engine.setProperty('voice', self.current_voice_id)
                    except Exception:
                        pass
                engine.say(text)
                engine.runAndWait()
                engine.stop()
                logger.debug(f"TTS spoke: {text}")
            except Exception as e:
                logger.error(f"TTS thread error: {e}")

        Thread(target=speak_thread, daemon=True).start()

    def close(self):
        """Cleanup TTS engine."""
        try:
            if hasattr(self, 'engine') and self.engine:
                self.engine.stop()
        except Exception as e:
            logger.error(f"TTS close error: {e}")
