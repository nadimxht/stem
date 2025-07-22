import subprocess
import os
import logging
from typing import Optional
import ffmpeg
import shutil

logger = logging.getLogger(__name__)

class StemSeparator:
    def __init__(self):
        self.models = {
            'htdemucs': 'htdemucs',  # High quality, slower
            'htdemucs_ft': 'htdemucs_ft',  # Fine-tuned version
            'mdx_extra': 'mdx_extra',  # Alternative model
        }
        self.default_model = 'htdemucs'
    
    def convert_to_wav(self, input_file: str, output_file: str) -> None:
        """Convert audio file to WAV format using ffmpeg"""
        try:
            (
                ffmpeg
                .input(input_file)
                .output(
                    output_file,
                    acodec='pcm_s16le',  # 16-bit PCM
                    ac=2,  # Stereo
                    ar=44100  # 44.1kHz sample rate
                )
                .run(overwrite_output=True, quiet=True)
            )
            logger.info(f"Converted {input_file} to WAV format")
        except Exception as e:
            logger.error(f"Failed to convert {input_file}: {e}")
            raise
    
    def separate_stems(self, audio_path: str, output_dir: str, 
                      model: str = None, device: str = None) -> str:
        """Separate audio into stems using Demucs"""
        
        if not os.path.exists(audio_path):
            raise Exception(f"Audio file not found: {audio_path}")
        
        model = model or self.default_model
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Build demucs command
        cmd = [
            "python", "-m", "demucs",
            "-n", model,
            "--mp3",  # Output as MP3 first (faster), convert later
            "-o", output_dir,
            audio_path
        ]
        
        # Add device specification if provided
        if device:
            cmd.extend(["-d", device])
        
        logger.info(f"Starting stem separation with model: {model}")
        logger.info(f"Command: {' '.join(cmd)}")
        
        try:
            # Run demucs with timeout
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            logger.info("Demucs separation completed")
            
            # Find the output directory
            audio_name = os.path.splitext(os.path.basename(audio_path))[0]
            stems_dir = os.path.join(output_dir, model, audio_name)
            
            if not os.path.exists(stems_dir):
                raise Exception(f"Stems directory not found: {stems_dir}")
            
            # Convert MP3 stems to WAV
            converted_files = []
            for fname in os.listdir(stems_dir):
                if fname.endswith(".mp3"):
                    mp3_path = os.path.join(stems_dir, fname)
                    wav_name = os.path.splitext(fname)[0] + ".wav"
                    wav_path = os.path.join(stems_dir, wav_name)
                    
                    try:
                        self.convert_to_wav(mp3_path, wav_path)
                        converted_files.append(wav_name[:-4])  # Remove .wav extension
                        
                        # Remove original MP3 file to save space
                        os.remove(mp3_path)
                        
                    except Exception as e:
                        logger.error(f"Failed to convert {fname}: {e}")
                        continue
            
            if not converted_files:
                raise Exception("No stems were successfully converted")
            
            logger.info(f"Successfully separated {len(converted_files)} stems: {converted_files}")
            return stems_dir
            
        except subprocess.TimeoutExpired:
            logger.error("Demucs process timed out")
            raise Exception("Stem separation timed out")
        except subprocess.CalledProcessError as e:
            logger.error(f"Demucs failed with return code {e.returncode}")
            logger.error(f"Error output: {e.stderr}")
            raise Exception(f"Stem separation failed: {e.stderr}")
        except Exception as e:
            logger.error(f"Unexpected error in stem separation: {e}")
            raise
    
    def cleanup_temp_files(self, output_dir: str, audio_path: str) -> None:
        """Clean up temporary files"""
        try:
            # Remove original audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            # Remove any temporary demucs files
            temp_dirs = [d for d in os.listdir(output_dir) 
                        if d.startswith('.') and 'demucs' in d]
            for temp_dir in temp_dirs:
                temp_path = os.path.join(output_dir, temp_dir)
                if os.path.isdir(temp_path):
                    shutil.rmtree(temp_path)
                    
        except Exception as e:
            logger.warning(f"Failed to cleanup temp files: {e}")

# Global instance
separator = StemSeparator()

def separate_stems(audio_path: str, output_dir: str, 
                  model: str = None, device: str = None) -> str:
    """Separate stems (wrapper for backward compatibility)"""
    return separator.separate_stems(audio_path, output_dir, model, device)