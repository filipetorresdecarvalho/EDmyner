# tts_handler.py - Text-to-Speech handler using Windows SAPI
import threading
import queue

class TTSHandler:
    """Handle text-to-speech using Windows SAPI."""
    
    def __init__(self):
        self.tts_queue = queue.Queue()
        self.engine = None
        self.tts_thread = None
        self.running = True
        self._init_engine()
    
    def _init_engine(self):
        """Initialize Windows SAPI TTS engine."""
        try:
            import win32com.client
            self.engine = win32com.client.Dispatch("SAPI.SpVoice")
            self.engine.Rate = 1  # Normal speed
            
            # Start background worker
            self.tts_thread = threading.Thread(target=self._worker, daemon=True)
            self.tts_thread.start()
            print("TTS: Windows SAPI initialized successfully")
        except Exception as e:
            print(f"TTS: Failed to initialize - {str(e)}")
            self.engine = None
    
    def _worker(self):
        """Background worker for non-blocking TTS."""
        while self.running:
            try:
                text = self.tts_queue.get(timeout=1)
                if self.engine and text:
                    self.engine.Speak(text)
                self.tts_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS worker error: {str(e)}")
    
    def speak(self, text):
        """Queue text for speech (non-blocking)."""
        try:
            if self.engine:
                self.tts_queue.put(text)
                print(f"TTS: Queued '{text}'")
        except Exception as e:
            print(f"TTS speak error: {str(e)}")
    
    def shutdown(self):
        """Shutdown TTS handler."""
        self.running = False
