import pytest
import tempfile
import os
from unittest.mock import Mock, patch
from worker_tasks import process_job
from database import Job
import uuid

class TestWorkerTasks:
    
    @patch('worker_tasks.download_audio')
    @patch('worker_tasks.separate_stems')
    @patch('worker_tasks.SessionLocal')
    def test_process_job_success(self, mock_session, mock_separate, mock_download):
        """Test successful job processing"""
        
        # Setup mocks
        job_id = str(uuid.uuid4())
        mock_db = Mock()
        mock_session.return_value = mock_db
        
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "audio.wav")
            stems_dir = os.path.join(temp_dir, "stems")
            
            # Create mock files
            open(audio_path, 'a').close()
            os.makedirs(stems_dir, exist_ok=True)
            open(os.path.join(stems_dir, "vocals.wav"), 'a').close()
            open(os.path.join(stems_dir, "drums.wav"), 'a').close()
            
            mock_download.return_value = audio_path
            mock_separate.return_value = stems_dir
            
            # Run the job
            process_job("https://youtube.com/watch?v=test", job_id)
            
            # Verify calls were made
            mock_download.assert_called_once()
            mock_separate.assert_called_once()
    
    @patch('worker_tasks.download_audio')
    @patch('worker_tasks.SessionLocal')
    def test_process_job_download_failure(self, mock_session, mock_download):
        """Test job processing with download failure"""
        
        job_id = str(uuid.uuid4())
        mock_db = Mock()
        mock_session.return_value = mock_db
        
        # Make download fail
        mock_download.side_effect = Exception("Download failed")
        
        # Should raise exception
        with pytest.raises(Exception):
            process_job("https://youtube.com/watch?v=test", job_id)
    
    @patch('worker_tasks.download_audio')
    @patch('worker_tasks.separate_stems')
    @patch('worker_tasks.SessionLocal')
    def test_process_job_separation_failure(self, mock_session, mock_separate, mock_download):
        """Test job processing with separation failure"""
        
        job_id = str(uuid.uuid4())
        mock_db = Mock()
        mock_session.return_value = mock_db
        
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, "audio.wav")
            open(audio_path, 'a').close()
            
            mock_download.return_value = audio_path
            mock_separate.side_effect = Exception("Separation failed")
            
            # Should raise exception
            with pytest.raises(Exception):
                process_job("https://youtube.com/watch?v=test", job_id)