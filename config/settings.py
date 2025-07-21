import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")
    MAX_FILE_SIZE_MB = 50
    SUPPORTED_FILE_TYPES = [
        "pdf",
        "txt",
        "png",
        "jpg",
        "jpeg",
        "docx",
        "xlsx",
        "csv",
        "md",
        "json",
        "xml",
        "html",
        "py",
        "js",
        "ts",
        "doc",
        "xls",
        "ppt",
        "pptx",
    ]
    # Use /tmp for temporary files on Hugging Face Spaces (or override with TEMP_DIR env var)
    TEMP_DIR = Path(os.getenv("TEMP_DIR", "/tmp/data_extractor_temp"))
    DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "python:3.12-slim")
    COORDINATOR_MODEL = "gemini-2.5-pro"
    PROMPT_ENGINEER_MODEL = "gemini-2.5-pro"
    DATA_EXTRACTOR_MODEL = "gemini-2.5-pro"
    DATA_ARRANGER_MODEL = "gemini-2.5-pro"
    CODE_GENERATOR_MODEL = "gemini-2.5-flash"

    COORDINATOR_MODEL_THINKING_BUDGET=2048
    PROMPT_ENGINEER_MODEL_THINKING_BUDGET=2048
    DATA_EXTRACTOR_MODEL_THINKING_BUDGET=2048
    DATA_ARRANGER_MODEL_THINKING_BUDGET=2048
    CODE_GENERATOR_MODEL_THINKING_BUDGET=-1

    @classmethod
    def validate_config(cls):
        if not cls.GOOGLE_AI_API_KEY:
            raise ValueError("GOOGLE_AI_API_KEY required")
        cls.TEMP_DIR.mkdir(exist_ok=True)


settings = Settings()
