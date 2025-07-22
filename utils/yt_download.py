import yt_dlp
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class AudioDownloader:
    def __init__(self, max_filesize: int = 100 * 1024 * 1024):  # 100MB default
        self.max_filesize = max_filesize
    
    def download_audio(self, youtube_url: str, output_dir: str) -> str:
        """Download audio from YouTube URL"""
        
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'audio.%(ext)s')
        
        ydl_opts = {
            'format': 'bestaudio[filesize<100M]/best[filesize<100M]',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extractaudio': True,
            'audioformat': 'wav',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'postprocessor_args': [
                '-ac', '2',  # Stereo
                '-ar', '44100',  # 44.1kHz sample rate
            ],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to validate
                info = ydl.extract_info(youtube_url, download=False)
                
                if not info:
                    raise Exception("Could not extract video information")
                
                # Check duration (limit to reasonable length)
                duration = info.get('duration', 0)
                if duration > 1800:  # 30 minutes
                    raise Exception("Video too long (max 30 minutes)")
                
                # Download the audio
                logger.info(f"Downloading: {info.get('title', 'Unknown')}")
                ydl.download([youtube_url])
                
                # Return the path to the downloaded file
                audio_file = os.path.join(output_dir, 'audio.wav')
                
                if not os.path.exists(audio_file):
                    raise Exception("Audio file was not created")
                
                # Check file size
                file_size = os.path.getsize(audio_file)
                if file_size > self.max_filesize:
                    os.remove(audio_file)
                    raise Exception(f"File too large: {file_size/1024/1024:.1f}MB")
                
                logger.info(f"Downloaded audio: {file_size/1024/1024:.1f}MB")
                return audio_file
                
        except yt_dlp.utils.DownloadError as e:
            logger.error(f"Download error: {e}")
            raise Exception(f"Failed to download audio: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

# Global instance
downloader = AudioDownloader()

def download_audio(youtube_url: str, output_dir: str) -> str:
    """Download audio from YouTube URL (wrapper for backward compatibility)"""
    return downloader.download_audio(youtube_url, output_dir)