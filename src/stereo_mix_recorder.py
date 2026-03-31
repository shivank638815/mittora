"""
Stereo Mix Audio Recorder - Records system audio output using Stereo Mix
"""
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

try:
    from pydub import AudioSegment
    import shutil
    
    # Try to find ffmpeg in system PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        # Set ffmpeg path for pydub
        AudioSegment.converter = ffmpeg_path
        AudioSegment.ffmpeg = ffmpeg_path
        AudioSegment.ffprobe = shutil.which("ffprobe") or ffmpeg_path.replace("ffmpeg", "ffprobe")
        PYDUB_AVAILABLE = True
        print(f"✅ pydub loaded with ffmpeg at: {ffmpeg_path}")
    else:
        print("⚠️  ffmpeg not found in PATH")
        PYDUB_AVAILABLE = False
except ImportError:
    PYDUB_AVAILABLE = False
    print("⚠️  pydub not installed")



class StereoMixRecorder:
    """Records audio from Stereo Mix (system output) to WAV files."""

    def __init__(
        self,
        output_dir: Path | str,
        sample_rate: int = 44100,
        channels: int = 2,
        dtype: str = "float32",
        subtype: str = "PCM_16",
        convert_to_mp3: bool = True,  # Convert to MP3 by default
        mp3_bitrate: str = "192k",    # MP3 bitrate
    ) -> None:
        """
        Initialize Stereo Mix Recorder
        
        Args:
            output_dir: Directory to save audio files
            sample_rate: Audio sample rate (44100 is CD quality)
            channels: Number of audio channels (2 for stereo)
            dtype: Data type for recording
            subtype: WAV file encoding format
            convert_to_mp3: Convert WAV to MP3 after recording
            mp3_bitrate: MP3 encoding bitrate (128k, 192k, 320k)
        """
        self.output_dir = Path(output_dir)
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.subtype = subtype
        self.convert_to_mp3 = convert_to_mp3 and PYDUB_AVAILABLE
        self.mp3_bitrate = mp3_bitrate

        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._stream: Optional[sd.InputStream] = None
        self._writer_thread: Optional[threading.Thread] = None
        self._soundfile: Optional[sf.SoundFile] = None
        self._audio_queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self._recording_active = False
        self._start_timestamp: Optional[float] = None
        self._total_frames_written = 0
        self._recording_path: Optional[Path] = None
        
        # External chunk listeners (e.g., AI pipeline)
        self._chunk_listeners: list = []

        self._device_index = self._find_stereo_mix_device()

    def _find_stereo_mix_device(self) -> Optional[int]:
        """Find Stereo Mix device index"""
        try:
            devices = sd.query_devices()
            
            # Look for Stereo Mix in input devices
            for idx, device in enumerate(devices):
                device_name = device.get('name', '').lower()
                max_input_channels = device.get('max_input_channels', 0)
                
                # Check if device name contains "stereo mix" and has input channels
                if 'stereo mix' in device_name and max_input_channels > 0:
                    print(f"🎧 Found Stereo Mix device: {device['name']} (index {idx})")
                    return idx
            
            print("⚠️  Stereo Mix device not found. Using default input device.")
            print("   Make sure Stereo Mix is enabled in Windows Sound settings.")
            return None
            
        except Exception as error:
            print(f"⚠️  Error querying audio devices: {error}")
            return None

    def _callback(self, indata, frames, time_info, status) -> None:
        """Audio stream callback - called for each audio block"""
        if status:
            print(f"⚠️  Audio stream status: {status}")
        if not self._recording_active:
            return

        # Copy data to avoid issues with buffer reuse
        data = indata.copy()
        
        # Queue the audio data for the writer thread
        self._audio_queue.put(np.asarray(data, dtype=np.float32))

        # Forward to external chunk listeners (e.g., AI pipeline)
        for listener in self._chunk_listeners:
            try:
                listener(data.copy())
            except Exception:
                pass

    def register_chunk_listener(self, callback) -> None:
        """Register a callback to receive copies of audio chunks in real-time."""
        self._chunk_listeners.append(callback)


    def _writer(self) -> None:
        """Writer thread - saves audio data to file"""
        while self._recording_active or not self._audio_queue.empty():
            try:
                data = self._audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self._soundfile is not None:
                self._soundfile.write(data)
                self._total_frames_written += len(data)

    def start(self, meeting_name: str | None = None) -> Optional[Path]:
        """
        Start recording audio
        
        Args:
            meeting_name: Name of the meeting for filename
            
        Returns:
            Path to the recording file, or None if failed
        """
        if self._recording_active:
            return self._recording_path

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = meeting_name or "meeting"
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in safe_name)
        filename = f"{safe_name}_{timestamp}.wav"

        self._recording_path = self.output_dir / filename
        self._audio_queue = queue.Queue()
        self._total_frames_written = 0

        try:
            # Create WAV file
            self._soundfile = sf.SoundFile(
                self._recording_path,
                mode="w",
                samplerate=self.sample_rate,
                channels=self.channels,
                subtype=self.subtype,
            )

            # Configure stream
            stream_kwargs = {
                "samplerate": self.sample_rate,
                "channels": self.channels,
                "dtype": self.dtype,
                "callback": self._callback,
            }

            # Use Stereo Mix device if found, otherwise default
            if self._device_index is not None:
                stream_kwargs["device"] = self._device_index

            self._stream = sd.InputStream(**stream_kwargs)

            # Start writer thread and stream
            self._writer_thread = threading.Thread(target=self._writer, daemon=True)
            self._recording_active = True
            self._start_timestamp = time.time()

            self._stream.start()
            self._writer_thread.start()

            print(f"🎙️  Audio recording started: {self._recording_path}")
            return self._recording_path
            
        except Exception as error:
            print(f"❌ Failed to start audio recording: {error}")
            self._cleanup()
            return None

    def stop(self) -> Optional[Path]:
        """
        Stop recording audio
        
        Returns:
            Path to the saved recording file
        """
        if not self._recording_active:
            return self._recording_path

        self._recording_active = False

        # Stop stream
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as error:
                print(f"⚠️  Error stopping audio stream: {error}")
            finally:
                self._stream = None

        # Wait for writer thread to finish
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=5)
            self._writer_thread = None

        # Close sound file
        if self._soundfile is not None:
            try:
                self._soundfile.flush()
                self._soundfile.close()
            except Exception as error:
                print(f"⚠️  Error closing audio file: {error}")
            finally:
                self._soundfile = None

        duration_seconds = self.duration_seconds
        recording_path = self._recording_path
        self._cleanup(reset_path=False)

        if recording_path is not None:
            wav_path = recording_path
            print(
                f"⏹️  Audio recording stopped: {wav_path} "
                f"({duration_seconds:.1f} seconds saved)"
            )
            
            # Convert to MP3 if enabled
            if self.convert_to_mp3:
                try:
                    mp3_path = self._convert_to_mp3(wav_path)
                    if mp3_path:
                        recording_path = mp3_path  # Return MP3 path instead
                except Exception as error:
                    print(f"⚠️  MP3 conversion failed: {error}")
                    print(f"   WAV file available at: {wav_path}")

        return recording_path

    @property
    def duration_seconds(self) -> float:
        """Get recording duration in seconds"""
        if self._start_timestamp is None:
            return 0.0
        elapsed = time.time() - self._start_timestamp
        if self.sample_rate and self._total_frames_written:
            elapsed = self._total_frames_written / float(self.sample_rate)
        return max(elapsed, 0.0)

    def _convert_to_mp3(self, wav_path: Path) -> Optional[Path]:
        """
        Convert WAV file to MP3
        
        Args:
            wav_path: Path to WAV file
            
        Returns:
            Path to MP3 file, or None if conversion failed
        """
        if not PYDUB_AVAILABLE:
            print("⚠️  pydub not available - cannot convert to MP3")
            print("   Install with: pip install pydub")
            return None
        
        try:
            print(f"🔄 Converting to MP3...")
            
            # Load WAV file
            audio = AudioSegment.from_wav(str(wav_path))
            
            # Create MP3 filename
            mp3_path = wav_path.with_suffix('.mp3')
            
            # Export as MP3
            audio.export(
                str(mp3_path),
                format="mp3",
                bitrate=self.mp3_bitrate,
                parameters=["-q:a", "2"]  # High quality VBR
            )
            
            print(f"✅ Converted to MP3: {mp3_path}")
            print(f"   Bitrate: {self.mp3_bitrate}")
            
            # Delete WAV file to save space
            try:
                wav_path.unlink()
                print(f"🗑️  Deleted WAV file (MP3 version saved)")
            except Exception:
                print(f"⚠️  Could not delete WAV file: {wav_path}")
            
            return mp3_path
            
        except Exception as error:
            print(f"❌ MP3 conversion error: {error}")
            return None


    def _cleanup(self, reset_path: bool = True) -> None:
        """Cleanup resources"""
        self._recording_active = False
        
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            finally:
                self._stream = None

        if self._soundfile is not None:
            try:
                self._soundfile.close()
            except Exception:
                pass
            finally:
                self._soundfile = None

        self._writer_thread = None
        self._audio_queue = queue.Queue()
        self._start_timestamp = None
        self._total_frames_written = 0
        
        if reset_path:
            self._recording_path = None

    def __del__(self) -> None:
        """Cleanup on deletion"""
        try:
            self.stop()
        except Exception:
            pass
