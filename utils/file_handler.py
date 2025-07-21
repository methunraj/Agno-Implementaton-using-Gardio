from pathlib import Path
from PIL import Image
import PyPDF2
from config.settings import settings
from typing import Dict
import tempfile
import os

class FileHandler:
    def __init__(self):
        self.temp_dir = Path(settings.TEMP_DIR)
        self.max_size_mb = settings.MAX_FILE_SIZE_MB

    def validate_file(self, uploaded_file) -> Dict:
        validation = {"valid": False, "error": None, "file_info": None}
        if not uploaded_file:
            validation["error"] = "No file"
            return validation
        file_size_mb = len(uploaded_file.getbuffer()) / (1024 * 1024)
        if file_size_mb > self.max_size_mb:
            validation["error"] = "File too large"
            return validation
        file_extension = uploaded_file.name.split('.')[-1].lower()
        if file_extension not in settings.SUPPORTED_FILE_TYPES:
            validation["error"] = "Unsupported type"
            return validation
        validation["valid"] = True
        # Extract just filename for display (uploaded_file.name contains full Gradio temp path)
        import os
        filename = os.path.basename(uploaded_file.name)
        validation["file_info"] = {"name": filename, "size_mb": file_size_mb, "type": file_extension}
        return validation

    def save_uploaded_file(self, uploaded_file, session_id: str) -> str:
        # Handle None session_id gracefully
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())[:8]
        
        # Create session directory in temp
        session_dir = self.temp_dir / session_id / "input"
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract just the filename from the full path (uploaded_file.name contains full Gradio temp path)
        import os
        import logging
        logger = logging.getLogger(__name__)
        
        filename = os.path.basename(uploaded_file.name)
        file_path = session_dir / filename
        
        logger.info(f"Moving file from Gradio temp: {uploaded_file.name}")
        logger.info(f"To session directory: {file_path}")
        
        with open(file_path, "wb") as f:
            # Handle different types of file upload objects
            if hasattr(uploaded_file, 'getbuffer'):
                f.write(uploaded_file.getbuffer())
            elif hasattr(uploaded_file, 'read'):
                f.write(uploaded_file.read())
            else:
                # For NamedString or similar objects, read from the file path
                with open(uploaded_file.name, 'rb') as src:  # Use uploaded_file.name (Gradio temp path) to read
                    f.write(src.read())
        return str(file_path)

    def get_file_preview(self, file_path: str, file_type: str) -> str:
        if file_type == 'pdf':
            try:
                with open(file_path, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    if len(reader.pages) > 0:
                        text = reader.pages[0].extract_text()
                        return text[:500] + "..." if len(text) > 500 else text
            except Exception:
                return "PDF preview not available"
        elif file_type == 'txt':
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
                    return text[:500] + "..." if len(text) > 500 else text
            except Exception:
                return "Text preview not available"
        # Similar for image types could be added
        return "Preview not available"

    def cleanup_temp_files(self):
        """Clean up old temporary files."""
        try:
            import time
            current_time = time.time()
            # Clean up sessions older than 24 hours
            for session_dir in self.temp_dir.iterdir():
                if session_dir.is_dir():
                    # Check if directory is older than 24 hours
                    dir_age = current_time - session_dir.stat().st_mtime
                    if dir_age > 24 * 3600:  # 24 hours in seconds
                        import shutil
                        shutil.rmtree(session_dir)
        except Exception:
            pass  # Ignore cleanup errors