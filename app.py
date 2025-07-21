import gradio as gr
import asyncio
import json
import time
import os
# Silence Matplotlib cache warnings on read-only filesystems
os.environ.setdefault("MPLCONFIGDIR", "/tmp/mpl_cache")
import logging
from pathlib import Path
import uuid
from workflow.financial_workflow import FinancialDataExtractionWorkflow
from utils.file_handler import FileHandler
from config.settings import settings
import threading
from queue import Queue
import signal
import sys
import atexit
from datetime import datetime, timedelta

# Configure logging - Only INFO level and above, no httpcore/debug details
# Use /tmp for file logging on Hugging Face Spaces or disable file logging if not writable
import tempfile
import os

try:
    # Try to create log file in /tmp directory (works on Hugging Face Spaces)
    log_dir = "/tmp"
    log_file = os.path.join(log_dir, "app.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )
except (PermissionError, OSError):
    # Fallback to console-only logging if file logging fails
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )

# Disable httpcore and other verbose loggers
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("google.auth").setLevel(logging.WARNING)
logging.getLogger("google.api_core").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Auto-shutdown configuration
INACTIVITY_TIMEOUT_MINUTES = 30  # Shutdown after 30 minutes of inactivity
CHECK_INTERVAL_SECONDS = 60      # Check every minute

class AutoShutdownManager:
    """Manages automatic shutdown of the Gradio application."""
    
    def __init__(self, timeout_minutes=INACTIVITY_TIMEOUT_MINUTES):
        self.timeout_minutes = timeout_minutes
        self.last_activity = datetime.now()
        self.shutdown_timer = None
        self.app_instance = None
        self.is_shutting_down = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Register cleanup function
        atexit.register(self._cleanup)
        
        logger.info(f"AutoShutdownManager initialized with {timeout_minutes} minute timeout")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_server()
        sys.exit(0)
    
    def _cleanup(self):
        """Cleanup function called on exit."""
        if not self.is_shutting_down:
            logger.info("Application cleanup initiated")
            self._shutdown_server()
    
    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
        logger.debug(f"Activity updated: {self.last_activity}")
    
    def start_monitoring(self, app_instance):
        """Start monitoring for inactivity."""
        self.app_instance = app_instance
        self._start_inactivity_timer()
        logger.info("Inactivity monitoring started")
    
    def _start_inactivity_timer(self):
        """Start or restart the inactivity timer."""
        if self.shutdown_timer:
            self.shutdown_timer.cancel()
        
        def check_inactivity():
            if self.is_shutting_down:
                return
                
            time_since_activity = datetime.now() - self.last_activity
            if time_since_activity > timedelta(minutes=self.timeout_minutes):
                logger.info(f"No activity for {self.timeout_minutes} minutes, shutting down...")
                self._shutdown_server()
            else:
                # Schedule next check
                self._start_inactivity_timer()
        
        self.shutdown_timer = threading.Timer(CHECK_INTERVAL_SECONDS, check_inactivity)
        self.shutdown_timer.start()
    
    def _shutdown_server(self):
        """Shutdown the Gradio server gracefully."""
        if self.is_shutting_down:
            return
            
        self.is_shutting_down = True
        logger.info("Initiating server shutdown...")
        
        try:
            if self.shutdown_timer:
                self.shutdown_timer.cancel()
            
            if self.app_instance:
                # Gradio doesn't have a direct shutdown method, so we'll use os._exit
                logger.info("Shutting down Gradio application")
                import os
                os._exit(0)
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            import os
            os._exit(1)

# Global shutdown manager instance
shutdown_manager = AutoShutdownManager()

# Prompt Gallery Loader
class PromptGallery:
    """Manages loading and accessing prompt gallery from JSON configuration."""
    
    def __init__(self):
        self.prompts = {}
        self.load_prompts()
    
    def load_prompts(self):
        """Load prompts from JSON configuration file."""
        try:
            prompt_file = Path(settings.TEMP_DIR).parent / "config" / "prompt_gallery.json"
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    self.prompts = json.load(f)
                logger.info(f"Loaded prompt gallery with {len(self.prompts.get('categories', {}))} categories")
            else:
                logger.warning(f"Prompt gallery file not found: {prompt_file}")
                self.prompts = {"categories": {}}
        except Exception as e:
            logger.error(f"Error loading prompt gallery: {e}")
            self.prompts = {"categories": {}}
    
    def get_categories(self):
        """Get all available prompt categories."""
        return self.prompts.get('categories', {})
    
    def get_prompts_for_category(self, category_id):
        """Get all prompts for a specific category."""
        return self.prompts.get('categories', {}).get(category_id, {}).get('prompts', [])
    
    def get_prompt_by_id(self, category_id, prompt_id):
        """Get a specific prompt by category and prompt ID."""
        prompts = self.get_prompts_for_category(category_id)
        for prompt in prompts:
            if prompt.get('id') == prompt_id:
                return prompt
        return None

# Global prompt gallery instance
prompt_gallery = PromptGallery()

# Custom CSS for beautiful multi-agent streaming interface
custom_css = """
/* Main container styling */
.main-container {
    max-width: 1400px;
    margin: 0 auto;
}

/* Dynamic Single-Panel Workflow Layout */
.workflow-progress-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 16px;
    margin: 16px 0;
    gap: 8px;
}

.progress-nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 12px 16px;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.3s ease;
    flex: 1;
    text-align: center;
    position: relative;
}

.progress-nav-item.pending {
    background: rgba(107, 114, 128, 0.1);
    color: var(--body-text-color-subdued);
}

.progress-nav-item.active {
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
    border: 2px solid #3b82f6;
}

.progress-nav-item.current {
    background: rgba(102, 126, 234, 0.2);
    color: #667eea;
    border: 2px solid #667eea;
    transform: scale(1.05);
}

.progress-nav-item.completed {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
    border: 2px solid #10b981;
}

.progress-nav-item.clickable:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.nav-icon {
    font-size: 24px;
    margin-bottom: 8px;
}

.nav-label {
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 4px;
}

.nav-status {
    font-size: 10px;
    opacity: 0.7;
}

.active-agent-panel {
    background: var(--background-fill-secondary);
    border: 2px solid var(--border-color-primary);
    border-radius: 16px;
    margin: 16px 0;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
    transition: all 0.3s ease;
}

.agent-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    background: linear-gradient(135deg, var(--background-fill-primary) 0%, var(--background-fill-secondary) 100%);
    border-bottom: 1px solid var(--border-color-primary);
}

.agent-info {
    display: flex;
    align-items: center;
    gap: 16px;
}

.agent-icon-large {
    font-size: 32px;
    padding: 12px;
    background: var(--background-fill-primary);
    border-radius: 12px;
    border: 2px solid var(--border-color-accent);
}

.agent-details h3.agent-title {
    margin: 0 0 4px 0;
    font-size: 20px;
    font-weight: 700;
    color: var(--body-text-color);
}

.agent-details p.agent-description {
    margin: 0;
    font-size: 14px;
    color: var(--body-text-color-subdued);
}

.agent-status-badge {
    padding: 8px 16px;
    border-radius: 20px;
    color: white;
    font-weight: 600;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.agent-content-area {
    padding: 24px;
    min-height: 200px;
    max-height: 400px;
    overflow-y: auto;
    scroll-behavior: smooth;
}

.agent-content {
    font-family: var(--font-mono);
    font-size: 14px;
    line-height: 1.6;
    color: var(--body-text-color);
    white-space: pre-wrap;
    word-wrap: break-word;
}

.agent-content.streaming {
    border-left: 3px solid #3b82f6;
    padding-left: 12px;
    background: rgba(59, 130, 246, 0.02);
}

.agent-waiting,
.agent-starting,
.agent-empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 120px;
    color: var(--body-text-color-subdued);
    font-style: italic;
    font-size: 16px;
}

.typing-cursor {
    animation: blink 1s infinite;
    color: #3b82f6;
    font-weight: bold;
}

/* Legacy Multi-Agent Workflow Layout (kept for compatibility) */
.workflow-container {
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
    margin: 16px 0;
}

.agent-panel {
    background: var(--background-fill-secondary);
    border: 2px solid var(--border-color-primary);
    border-radius: 12px;
    padding: 16px;
    margin: 8px 0;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}

.agent-panel.active {
    border-color: var(--color-accent);
    box-shadow: 0 4px 20px rgba(102, 126, 234, 0.2);
    transform: translateY(-2px);
}

.agent-panel.completed {
    border-color: var(--color-success);
    background: rgba(17, 153, 142, 0.05);
}

.agent-panel.streaming {
    border-color: var(--color-accent);
    background: rgba(102, 126, 234, 0.05);
}

.agent-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-color-primary);
}

.agent-info {
    display: flex;
    align-items: center;
    gap: 12px;
}

.agent-icon {
    font-size: 24px;
    animation: pulse 2s infinite;
}

.agent-icon.active {
    animation: bounce 1s infinite;
}

.agent-name {
    font-size: 18px;
    font-weight: 600;
    color: var(--body-text-color);
}

.agent-description {
    font-size: 14px;
    color: var(--body-text-color-subdued);
    margin-top: 4px;
}

.agent-status {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    font-weight: 500;
}

.status-indicator {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    animation: pulse 2s infinite;
}

.status-indicator.pending {
    background: var(--color-neutral);
}

.status-indicator.starting {
    background: var(--color-warning);
    animation: flash 1s infinite;
}

.status-indicator.streaming {
    background: var(--color-accent);
    animation: pulse 1s infinite;
}

.status-indicator.completed {
    background: var(--color-success);
    animation: none;
}

.agent-thinking {
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    padding: 12px;
    min-height: 120px;
    max-height: 300px;
    overflow-y: auto;
    font-family: var(--font-mono);
    font-size: 13px;
    line-height: 1.5;
    color: var(--body-text-color);
    white-space: pre-wrap;
    word-wrap: break-word;
}

.agent-thinking.streaming {
    border-color: var(--color-accent);
    background: rgba(102, 126, 234, 0.02);
}

.agent-thinking.empty {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--body-text-color-subdued);
    font-style: italic;
}

.thinking-cursor {
    display: inline-block;
    width: 2px;
    height: 16px;
    background: var(--color-accent);
    margin-left: 2px;
    animation: blink 1s infinite;
}

/* Workflow Progress Overview */
.workflow-progress {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
}

.progress-step-mini {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    flex: 1;
    position: relative;
}

.progress-step-mini::after {
    content: '';
    position: absolute;
    top: 12px;
    right: -50%;
    width: 100%;
    height: 2px;
    background: var(--border-color-primary);
    z-index: 1;
}

.progress-step-mini:last-child::after {
    display: none;
}

.mini-icon {
    font-size: 20px;
    padding: 8px;
    border-radius: 50%;
    background: var(--background-fill-primary);
    border: 2px solid var(--border-color-primary);
    z-index: 2;
    position: relative;
}

.mini-icon.active {
    border-color: var(--color-accent);
    background: var(--color-accent);
    color: white;
    animation: pulse 1s infinite;
}

.mini-icon.completed {
    border-color: var(--color-success);
    background: var(--color-success);
    color: white;
}

.mini-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--body-text-color);
    text-align: center;
}

/* Animations */
@keyframes bounce {
    0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
    40% { transform: translateY(-10px); }
    60% { transform: translateY(-5px); }
}

@keyframes flash {
    0%, 50%, 100% { opacity: 1; }
    25%, 75% { opacity: 0.5; }
}

@keyframes blink {
    0%, 50% { opacity: 1; }
    51%, 100% { opacity: 0; }
}

@keyframes typewriter {
    from { width: 0; }
    to { width: 100%; }
}

/* Single step container styling */
.single-step-container {
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    font-family: var(--font-mono);
}

.steps-overview {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border-color-primary);
}

.step-overview-item {
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-primary);
}

.step-overview-item.current-step {
    background: var(--color-accent);
    color: white;
    border-color: var(--color-accent);
}

.step-overview-item.completed-step {
    background: var(--color-success);
    color: white;
    border-color: var(--color-success);
    cursor: pointer;
    transition: all 0.2s ease;
}

.step-overview-item.completed-step:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.step-overview-item.clickable {
    cursor: pointer;
    user-select: none;
}

.step-overview-item.other-step {
    opacity: 0.7;
}

/* Content formatting styles */
.code-content, .json-content, .text-content {
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-primary);
    border-radius: 4px;
    margin: 8px 0;
}

.code-header, .content-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--background-fill-secondary);
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color-primary);
    font-size: 12px;
    font-weight: 600;
}

.code-label, .content-label {
    color: var(--body-text-color);
}

.code-language, .content-type {
    background: var(--color-accent);
    color: white;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 10px;
}

.code-block, .json-block, .text-block {
    margin: 0;
    padding: 12px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.4;
    overflow-x: auto;
    background: var(--background-fill-primary);
    color: var(--body-text-color);
}

.empty-content {
    padding: 20px;
    text-align: center;
    color: var(--body-text-color-subdued);
    font-style: italic;
}

/* New step content wrapper styles */
.step-content-wrapper {
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    margin: 12px 0;
    overflow: hidden;
}

.step-content-header {
    background: var(--background-fill-secondary);
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color-primary);
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    font-size: 14px;
}

.step-icon {
    font-size: 18px;
}

.step-label {
    color: var(--body-text-color);
}

.step-content-body {
    padding: 16px;
    line-height: 1.6;
}

.markdown-content {
    font-family: var(--font-sans);
    color: var(--body-text-color);
}

.markdown-content h1, .markdown-content h2, .markdown-content h3, 
.markdown-content h4, .markdown-content h5, .markdown-content h6 {
    margin: 16px 0 8px 0;
    font-weight: 600;
    color: var(--body-text-color);
}

.markdown-content h1 { font-size: 24px; }
.markdown-content h2 { font-size: 20px; }
.markdown-content h3 { font-size: 18px; }
.markdown-content h4 { font-size: 16px; }
.markdown-content h5 { font-size: 14px; }
.markdown-content h6 { font-size: 12px; }

.markdown-content p {
    margin: 8px 0;
    color: var(--body-text-color);
}

.markdown-content li {
    margin: 4px 0;
    padding-left: 8px;
    list-style-type: disc;
    color: var(--body-text-color);
}

.markdown-content ul {
    margin: 8px 0;
    padding-left: 20px;
}

.markdown-content ol {
    margin: 8px 0;
    padding-left: 20px;
}

.markdown-content strong {
    font-weight: 600;
    color: var(--body-text-color);
}

.markdown-content em {
    font-style: italic;
    color: var(--body-text-color-subdued);
}

.markdown-content code {
    background: var(--background-fill-secondary);
    padding: 2px 4px;
    border-radius: 3px;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--body-text-color);
}

.formatted-content {
    font-family: var(--font-sans);
    line-height: 1.6;
    color: var(--body-text-color);
}

.error-content {
    background: #fee;
    border: 1px solid #fcc;
    border-radius: 4px;
    padding: 12px;
    color: #c33;
    font-family: var(--font-mono);
    font-size: 12px;
}

/* Step type specific styling */
.code-step .step-content-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
}

.data-step .step-content-header {
    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
    color: white;
}

.prompts-step .step-content-header {
    background: linear-gradient(135deg, #ff6b6b 0%, #feca57 100%);
    color: white;
}

.default-step .step-content-header {
    background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
    color: white;
}

.current-step-details {
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-primary);
    border-radius: 4px;
    padding: 12px;
}

.step-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border-color-primary);
}

.step-title {
    font-weight: 600;
    font-size: 14px;
    color: var(--body-text-color);
}

.step-progress {
    font-size: 12px;
    font-weight: 500;
    color: var(--body-text-color-subdued);
}

.step-description {
    font-size: 12px;
    color: var(--body-text-color-subdued);
    margin-bottom: 8px;
    font-style: italic;
}

.step-content {
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
    border-radius: 4px;
    padding: 12px;
    margin-top: 8px;
    max-height: 200px;
    overflow-y: auto;
}

.step-content pre {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.4;
    color: var(--body-text-color);
    white-space: pre-wrap;
    word-wrap: break-word;
}

/* Progress bar styling */
.progress-container {
    margin: 20px 0;
}

.progress-step {
    display: flex;
    align-items: center;
    margin: 10px 0;
    padding: 10px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.05);
    transition: all 0.3s ease;
}

.progress-step.active {
    background: rgba(102, 126, 234, 0.2);
    transform: scale(1.02);
}

.progress-step.completed {
    background: rgba(17, 153, 142, 0.2);
}

.step-icon {
    font-size: 24px;
    margin-right: 15px;
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.1); }
    100% { transform: scale(1); }
}

/* Fade in animation */
.fade-in {
    animation: fadeIn 0.5s ease-in;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Typing indicator */
.typing-indicator {
    display: inline-block;
    width: 20px;
    height: 10px;
}

.typing-indicator span {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #667eea;
    margin: 0 2px;
    animation: typing 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes typing {
    0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
    40% { transform: scale(1); opacity: 1; }
}

/* Header styling */
.header-title {
    font-size: 1.2rem;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0;
    text-align: left;
    padding: 0.5rem 0;
}

/* Status indicators */
.status-success {
    color: #38ef7d;
    font-weight: bold;
}

.status-error {
    color: #ff6b6b;
    font-weight: bold;
}

.status-processing {
    color: #667eea;
    font-weight: bold;
}

/* JSON Formatting and Auto-scroll Styles */
.json-container {
    position: relative;
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    margin: 8px 0;
    overflow: hidden;
}

.json-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--background-fill-secondary);
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color-primary);
    font-size: 12px;
    font-weight: 600;
}

.json-controls {
    display: flex;
    gap: 8px;
    align-items: center;
}

.json-toggle-btn, .json-copy-btn {
    background: var(--color-accent);
    color: white;
    border: none;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 10px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.json-toggle-btn:hover, .json-copy-btn:hover {
    background: var(--color-accent-dark);
    transform: translateY(-1px);
}

.json-content {
    max-height: 300px;
    overflow: auto;
    scroll-behavior: smooth;
}

.json-formatted {
    padding: 12px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.4;
    color: var(--body-text-color);
    white-space: pre-wrap;
    word-wrap: break-word;
}

.json-key {
    color: #0066cc;
    font-weight: 600;
}

.json-string {
    color: #22863a;
}

.json-number {
    color: #005cc5;
}

.json-boolean {
    color: #d73a49;
    font-weight: 600;
}

.json-null {
    color: #6f42c1;
    font-style: italic;
}

.json-punctuation {
    color: #586069;
}

.json-collapsed {
    display: none;
}

.json-expand-btn {
    background: none;
    border: none;
    color: var(--color-accent);
    cursor: pointer;
    font-family: monospace;
    font-size: 12px;
    padding: 0 4px;
    margin: 0 4px;
}

.json-expand-btn:hover {
    background: rgba(102, 126, 234, 0.1);
    border-radius: 2px;
}

/* Auto-scroll indicator */
.auto-scroll-indicator {
    position: absolute;
    top: 8px;
    right: 40px;
    background: rgba(102, 126, 234, 0.8);
    color: white;
    padding: 2px 6px;
    border-radius: 12px;
    font-size: 10px;
    z-index: 10;
    opacity: 0;
    transition: opacity 0.3s ease;
}

.auto-scroll-indicator.active {
    opacity: 1;
}

/* Download button styling */
.download-section {
    text-align: center;
    margin: 20px 0;
}

.download-btn {
    background: linear-gradient(135deg, #38ef7d, #11998e);
    color: white;
    border: none;
    padding: 12px 24px;
    border-radius: 8px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 12px rgba(56, 239, 125, 0.3);
}

.download-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(56, 239, 125, 0.4);
}

.download-btn:active {
    transform: translateY(2px);
    box-shadow: 0 2px 6px rgba(56, 239, 125, 0.2);
}

/* Prompt Gallery Styling */
.prompt-gallery {
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
}

.prompt-card {
    background: var(--background-fill-primary);
    border: 1px solid var(--border-color-accent);
    border-radius: 6px;
    padding: 12px;
    margin: 8px 0;
    cursor: pointer;
    transition: all 0.3s ease;
}

.prompt-card:hover {
    background: var(--background-fill-secondary);
    border-color: var(--color-accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.prompt-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}

.prompt-card-title {
    font-weight: 600;
    color: var(--body-text-color);
    margin: 0;
}

.prompt-card-description {
    color: var(--body-text-color-subdued);
    font-size: 0.9em;
    margin: 0;
}

.prompt-preview {
    background: var(--background-fill-secondary);
    border: 1px solid var(--border-color-primary);
    border-radius: 4px;
    padding: 8px;
    margin-top: 8px;
    font-size: 0.85em;
    color: var(--body-text-color-subdued);
    max-height: 100px;
    overflow-y: auto;
}

.gallery-category {
    margin-bottom: 16px;
}

.category-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--border-color-accent);
}

.category-title {
    font-size: 1.1em;
    font-weight: 600;
    color: var(--body-text-color);
    margin: 0;
}

.use-prompt-btn {
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 0.85em;
    cursor: pointer;
    transition: all 0.3s ease;
    margin-top: 8px;
}

.use-prompt-btn:hover {
    background: linear-gradient(135deg, #764ba2, #667eea);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}
"""


class WorkflowUI:
    def __init__(self):
        self.file_handler = FileHandler()
        self.session_id = str(uuid.uuid4())[:8]  # Generate our own session ID
        
        # Create the new Workflows 2.0 instance
        self.workflow = FinancialDataExtractionWorkflow(session_id=self.session_id)
        
        self.current_step = 0
        self.step_contents = {}
        self.step_statuses = {}
        self.processing_started = False
        self.total_steps = 0
        self.selected_prompt = None

        self.steps_config = {
            "data_extraction": {
                "name": "Financial Data Extraction",
                "description": "Extracting financial data points from document", 
                "icon": "🔍",
                "agent": "Data Extractor Agent"
            },
            "data_arrangement": {
                "name": "Data Analysis & Organization",
                "description": "Organizing and analyzing extracted financial data",
                "icon": "📊", 
                "agent": "Data Arranger Agent"
            },
            "excel_generation": {
                "name": "Excel Report Generation",
                "description": "Generating comprehensive Excel reports with 12 worksheets",
                "icon": "📊",
                "agent": "Coding Agent"
            }
        }
        self.step_statuses = {}
        self.step_contents = {}  # Store content for each step for navigation
        self.total_steps = len(self.steps_config)
        
    def _map_agent_to_step(self, agent_name: str) -> str:
        """Map agent name to UI step key for proper streaming display."""
        logger.debug(f"Mapping agent '{agent_name}' to step")
        
        # Exact matches first
        agent_mapping = {
            "coordinator-agent": "planning",
            "prompt-engineer-agent": "prompt_engineering", 
            "data-extractor-agent": "data_extraction",
            "data-arranger-agent": "data_arrangement",
            "code-generator-agent": "excel_generation"
        }
        
        # Try exact match first
        if agent_name in agent_mapping:
            return agent_mapping[agent_name]
        
        # Try partial matches for flexibility
        agent_name_lower = agent_name.lower()
        if "coordinator" in agent_name_lower or "planning" in agent_name_lower:
            return "planning"
        elif "prompt" in agent_name_lower and "engineer" in agent_name_lower:
            return "prompt_engineering"
        elif "data" in agent_name_lower and "extractor" in agent_name_lower:
            return "data_extraction"
        elif "data" in agent_name_lower and "arranger" in agent_name_lower:
            return "data_arrangement"
        elif "code" in agent_name_lower and "generator" in agent_name_lower:
            return "excel_generation"
        
        logger.warning(f"Could not map agent '{agent_name}' to step, defaulting to 'data_extraction'")
        return "data_extraction"

    def validate_file(self, file_path):
        """Validate uploaded file."""
        logger.info(f"Validating file: {file_path}")

        if not file_path:
            logger.warning("No file uploaded")
            return {"valid": False, "error": "No file uploaded"}

        path = Path(file_path)
        if not path.exists():
            logger.error(f"File does not exist: {file_path}")
            return {"valid": False, "error": "File does not exist"}

        file_extension = path.suffix.lower().lstrip(".")

        if file_extension not in settings.SUPPORTED_FILE_TYPES:
            logger.error(f"Unsupported file type: {file_extension}")
            return {
                "valid": False,
                "error": f"Unsupported file type. Supported: {', '.join(settings.SUPPORTED_FILE_TYPES)}",
            }

        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > 50:  # 50MB limit
            logger.error(f"File too large: {file_size_mb}MB")
            return {"valid": False, "error": "File too large (max 50MB)"}

        logger.info(
            f"File validation successful: {path.name} ({file_extension}, {file_size_mb}MB)"
        )
        return {
            "valid": True,
            "file_info": {
                "name": path.name,
                "type": file_extension,
                "size_mb": round(file_size_mb, 2),
            },
        }

        file_size_mb = path.stat().st_size / (1024 * 1024)
        if file_size_mb > 50:  # 50MB limit
            return {"valid": False, "error": "File too large (max 50MB)"}

        return {
            "valid": True,
            "file_info": {
                "name": path.name,
                "type": file_extension,
                "size_mb": round(file_size_mb, 2),
            },
        }

    def get_file_preview(self, file_path):
        """Get file preview."""
        try:
            path = Path(file_path)
            if path.suffix.lower() in [".txt", ".md", ".py", ".json"]:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    return content[:1000] + "..." if len(content) > 1000 else content
            else:
                return f"Binary file: {path.name} ({path.suffix})"
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def render_multi_agent_workflow(self) -> str:
        """Render the dynamic single-panel workflow interface."""
        
        # Find current active step
        current_step = None
        for step_key, status in self.step_statuses.items():
            if status in ["starting", "streaming"]:
                current_step = step_key
                break
        
        # If no active step, find the first pending step
        if not current_step:
            for step_key in self.steps_config.keys():
                if self.step_statuses.get(step_key, "pending") == "pending":
                    current_step = step_key
                    break
        
        # If still no current step, show the last completed step
        if not current_step:
            for step_key in reversed(list(self.steps_config.keys())):
                if self.step_statuses.get(step_key, "pending") == "completed":
                    current_step = step_key
                    break
        
        # Fallback to first step
        if not current_step:
            current_step = list(self.steps_config.keys())[0]
        
        # Create workflow progress navigation
        progress_html = '<div class="workflow-progress-nav">'
        for step_key, step_config in self.steps_config.items():
            status = self.step_statuses.get(step_key, "pending")
            is_current = step_key == current_step
            is_clickable = status == "completed" or step_key in self.step_contents
            
            nav_class = "progress-nav-item"
            if is_current:
                nav_class += " current"
            elif status == "completed":
                nav_class += " completed"
            elif status in ["starting", "streaming"]:
                nav_class += " active"
            else:
                nav_class += " pending"
                
            if is_clickable:
                nav_class += " clickable"
            
            onclick = f"showAgentStep('{step_key}')" if is_clickable else ""
            
            progress_html += f'''
            <div class="{nav_class}" onclick="{onclick}" data-step="{step_key}">
                <div class="nav-icon">{step_config["icon"]}</div>
                <div class="nav-label">{step_config["name"]}</div>
                <div class="nav-status"></div>
            </div>
            '''
        progress_html += '</div>'
        
        # Create single active agent panel
        if current_step:
            # Handle unknown step keys gracefully
            step_config = self.steps_config.get(current_step, {
                "name": current_step.replace('_', ' ').title(),
                "description": f"Processing {current_step}",
                "icon": "⚙️",
                "agent": "Processing Agent"
            })
            content = self.step_contents.get(current_step, "")
            status = self.step_statuses.get(current_step, "pending")
            
            # Status text and icon
            status_info = {
                "pending": {"text": "Waiting to start", "color": "#6b7280"},
                "starting": {"text": "Starting...", "color": "#f59e0b"},
                "streaming": {"text": "Thinking...", "color": "#3b82f6"},
                "completed": {"text": "Completed", "color": "#10b981"},
                "failed": {"text": "Failed", "color": "#ef4444"}
            }
            
            status_data = status_info.get(status, status_info["pending"])
            
            # Content display with JSON formatting and auto-scroll
            if not content or content.strip() == "":
                if status == "pending":
                    content_display = '<div class="agent-waiting">🤖 Agent is waiting to start...</div>'
                elif status == "starting":
                    content_display = '<div class="agent-starting">🔄 Agent is starting up...</div>'
                else:
                    content_display = '<div class="agent-empty">No content available</div>'
            else:
                # Check if content contains JSON and format accordingly
                formatted_content = self._format_content_with_json_support(content)
                if status == "streaming":
                    content_display = f'<div class="agent-content streaming" id="streaming-content-{current_step}">{formatted_content}<span class="typing-cursor">|</span></div>'
                else:
                    content_display = f'<div class="agent-content" id="content-{current_step}">{formatted_content}</div>'
            
            # Single panel HTML
            agents_html = f'''
            <div class="active-agent-panel" id="current-agent-panel" data-current-step="{current_step}">
                <div class="agent-panel-header">
                    <div class="agent-info">
                        <div class="agent-icon-large">{step_config["icon"]}</div>
                        <div class="agent-details">
                            <h3 class="agent-title">{step_config["name"]}</h3>
                            <p class="agent-description">{step_config["description"]}</p>
                        </div>
                    </div>
                    <div class="agent-status-badge" style="background-color: {status_data['color']}">
                        <span class="status-text">{status_data['text']}</span>
                    </div>
                </div>
                <div class="agent-content-area">
                    {content_display}
                </div>
            </div>
            '''
        else:
            agents_html = '<div class="no-agent">No agent selected</div>'
        
        # Add JavaScript for navigation, auto-scroll, and JSON formatting
        js_script = '''
        <script>
        // Auto-scroll functionality
        let autoScrollEnabled = true;
        let scrollTimeouts = {};
        
        function enableAutoScroll() {
            autoScrollEnabled = true;
            document.querySelectorAll('.auto-scroll-indicator').forEach(indicator => {
                indicator.classList.add('active');
            });
        }
        
        function disableAutoScroll() {
            autoScrollEnabled = false;
            document.querySelectorAll('.auto-scroll-indicator').forEach(indicator => {
                indicator.classList.remove('active');
            });
        }
        
        function autoScrollToBottom(containerId) {
            if (!autoScrollEnabled) return;
            
            const container = document.querySelector('.agent-content-area');
            if (container) {
                // Clear any existing timeout for this container
                if (scrollTimeouts[containerId]) {
                    clearTimeout(scrollTimeouts[containerId]);
                }
                
                // Set timeout to smooth scroll to bottom
                scrollTimeouts[containerId] = setTimeout(() => {
                    container.scrollTop = container.scrollHeight;
                    
                    // Show auto-scroll indicator briefly
                    const indicator = document.getElementById(`auto-scroll-${containerId}`);
                    if (indicator) {
                        indicator.classList.add('active');
                        setTimeout(() => {
                            indicator.classList.remove('active');
                        }, 1000);
                    }
                }, 100);
            }
        }
        
        // JSON formatting functions
        function toggleJsonView(containerId) {
            const container = document.getElementById(containerId);
            const button = container.querySelector('.json-toggle-btn');
            const content = container.querySelector('.json-formatted');
            
            if (button.textContent === 'Format') {
                // Switch to raw view
                const jsonData = content.textContent;
                content.innerHTML = `<pre>${jsonData}</pre>`;
                button.textContent = 'Pretty';
            } else {
                // Switch back to formatted view
                const rawData = content.textContent;
                try {
                    const parsed = JSON.parse(rawData);
                    const formatted = JSON.stringify(parsed, null, 2);
                    content.innerHTML = highlightJson(formatted);
                } catch (e) {
                    // If parsing fails, keep raw
                }
                button.textContent = 'Format';
            }
        }
        
        function copyJsonToClipboard(containerId) {
            const container = document.getElementById(containerId);
            const content = container.querySelector('.json-formatted');
            const text = content.textContent;
            
            navigator.clipboard.writeText(text).then(() => {
                const button = container.querySelector('.json-copy-btn');
                const originalText = button.textContent;
                button.textContent = 'Copied!';
                button.style.background = '#10b981';
                
                setTimeout(() => {
                    button.textContent = originalText;
                    button.style.background = '';
                }, 1500);
            }).catch(err => {
                console.error('Failed to copy to clipboard:', err);
            });
        }
        
        function highlightJson(jsonText) {
            // Apply syntax highlighting to JSON text
            let highlighted = jsonText
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            
            // Highlight keys
            highlighted = highlighted.replace(/"([^"]+)":/g, '<span class="json-key">"$1"</span>:');
            
            // Highlight string values
            highlighted = highlighted.replace(/: "([^"]*)"/g, ': <span class="json-string">"$1"</span>');
            
            // Highlight numbers
            highlighted = highlighted.replace(/: (-?\\d+\\.?\\d*)/g, ': <span class="json-number">$1</span>');
            
            // Highlight booleans
            highlighted = highlighted.replace(/: (true|false)/g, ': <span class="json-boolean">$1</span>');
            
            // Highlight null
            highlighted = highlighted.replace(/: (null)/g, ': <span class="json-null">$1</span>');
            
            return highlighted;
        }
        
        function showAgentStep(stepKey) {
            // Update current step in UI
            const currentPanel = document.getElementById('current-agent-panel');
            if (currentPanel) {
                currentPanel.setAttribute('data-current-step', stepKey);
            }
            
            // Update navigation highlighting
            document.querySelectorAll('.progress-nav-item').forEach(item => {
                item.classList.remove('current');
                if (item.getAttribute('data-step') === stepKey) {
                    item.classList.add('current');
                }
            });
            
            console.log('Switched to step:', stepKey);
        }
        
        // Auto-scroll detection for user interaction
        document.addEventListener('DOMContentLoaded', function() {
            const contentArea = document.querySelector('.agent-content-area');
            if (contentArea) {
                let userScrolled = false;
                
                contentArea.addEventListener('scroll', function() {
                    const isAtBottom = contentArea.scrollHeight - contentArea.clientHeight <= contentArea.scrollTop + 5;
                    
                    if (!isAtBottom && !userScrolled) {
                        userScrolled = true;
                        disableAutoScroll();
                    } else if (isAtBottom && userScrolled) {
                        userScrolled = false;
                        enableAutoScroll();
                    }
                });
            }
        });
        
        // Trigger auto-scroll when content updates during streaming
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'childList' || mutation.type === 'characterData') {
                    const streamingContent = document.querySelector('.streaming');
                    if (streamingContent && autoScrollEnabled) {
                        autoScrollToBottom('streaming');
                    }
                }
            });
        });
        
        // Start observing when DOM is ready
        document.addEventListener('DOMContentLoaded', function() {
            const agentContentArea = document.querySelector('.agent-content-area');
            if (agentContentArea) {
                observer.observe(agentContentArea, {
                    childList: true,
                    subtree: true,
                    characterData: true
                });
            }
        });
        </script>
        '''
        
        # Combine progress, active panel, and script
        return progress_html + agents_html + js_script
    
    def _format_content_with_json_support(self, content: str) -> str:
        """Format content with JSON syntax highlighting and collapsible sections."""
        import re
        import json
        import html
        
        try:
            # First, escape HTML in the content
            escaped_content = html.escape(content)
            
            # Try to detect and format JSON blocks
            json_pattern = r'```json\s*([\s\S]*?)\s*```'
            
            def format_json_block(match):
                json_text = match.group(1)
                try:
                    # Parse and reformat JSON
                    parsed = json.loads(json_text)
                    formatted_json = json.dumps(parsed, indent=2)
                    
                    # Apply syntax highlighting
                    highlighted = self._highlight_json(formatted_json)
                    
                    # Create collapsible JSON container
                    container_id = f"json-container-{abs(hash(json_text[:50]))}"
                    return f'''
                    <div class="json-container" id="{container_id}">
                        <div class="auto-scroll-indicator" id="auto-scroll-{container_id}">Auto-scrolling</div>
                        <div class="json-header">
                            <span>📄 JSON Data</span>
                            <div class="json-controls">
                                <button class="json-toggle-btn" onclick="toggleJsonView('{container_id}')">Format</button>
                                <button class="json-copy-btn" onclick="copyJsonToClipboard('{container_id}')">Copy</button>
                            </div>
                        </div>
                        <div class="json-content" id="{container_id}-content">
                            <div class="json-formatted">{highlighted}</div>
                        </div>
                    </div>
                    '''
                except json.JSONDecodeError:
                    # If not valid JSON, return as code block
                    return f'<pre class="code-block"><code>{html.escape(json_text)}</code></pre>'
            
            # Replace JSON blocks
            formatted_content = re.sub(json_pattern, format_json_block, escaped_content)
            
            # Also check for JSON-like patterns without code block markers
            json_like_pattern = r'(\{[\s\S]*?\})'
            
            def try_format_json_like(match):
                potential_json = match.group(1)
                try:
                    # Try to parse as JSON
                    parsed = json.loads(potential_json)
                    formatted_json = json.dumps(parsed, indent=2)
                    highlighted = self._highlight_json(formatted_json)
                    
                    container_id = f"json-container-{abs(hash(potential_json[:50]))}"
                    return f'''
                    <div class="json-container" id="{container_id}">
                        <div class="auto-scroll-indicator" id="auto-scroll-{container_id}">Auto-scrolling</div>
                        <div class="json-header">
                            <span>📄 JSON Data</span>
                            <div class="json-controls">
                                <button class="json-toggle-btn" onclick="toggleJsonView('{container_id}')">Raw</button>
                                <button class="json-copy-btn" onclick="copyJsonToClipboard('{container_id}')">Copy</button>
                            </div>
                        </div>
                        <div class="json-content" id="{container_id}-content">
                            <div class="json-formatted">{highlighted}</div>
                        </div>
                    </div>
                    '''
                except (json.JSONDecodeError, TypeError):
                    # Not valid JSON, return as-is
                    return potential_json
            
            # Try to format standalone JSON objects (only if they look substantial)
            if '{' in formatted_content and len(formatted_content.strip()) > 100:
                # Look for JSON-like patterns that are likely to be actual JSON
                formatted_content = re.sub(r'(\{[\s\S]{50,}?\})', try_format_json_like, formatted_content)
            
            # Convert line breaks
            formatted_content = formatted_content.replace('\n', '<br>')
            
            return formatted_content
            
        except Exception as e:
            # Fallback to escaped content if formatting fails
            return html.escape(content).replace('\n', '<br>')
    
    def _highlight_json(self, json_text: str) -> str:
        """Apply syntax highlighting to JSON text."""
        import re
        import html
        
        # Escape HTML first
        highlighted = html.escape(json_text)
        
        # Highlight JSON syntax elements
        # Keys (strings before colons)
        highlighted = re.sub(r'"([^"]+)"\s*:', r'<span class="json-key">"\1"</span>:', highlighted)
        
        # String values
        highlighted = re.sub(r':\s*"([^"]*)"', r': <span class="json-string">"\1"</span>', highlighted)
        
        # Numbers
        highlighted = re.sub(r':\s*(-?\d+\.?\d*)', r': <span class="json-number">\1</span>', highlighted)
        
        # Booleans
        highlighted = re.sub(r':\s*(true|false)', r': <span class="json-boolean">\1</span>', highlighted)
        
        # Null
        highlighted = re.sub(r':\s*(null)', r': <span class="json-null">\1</span>', highlighted)
        
        # Punctuation
        highlighted = re.sub(r'([{}[\],])', r'<span class="json-punctuation">\1</span>', highlighted)
        
        return highlighted
    
    def render_single_step_container(self, current_step_key: str, content: str, status: str, progress: float):
        """Render a single container that updates for the current step."""
        step_config = self.steps_config.get(current_step_key, {})
        
        # Store step content for navigation
        self.step_contents[current_step_key] = content

        # Status indicators
        status_emoji = {
            "pending": "⏳",
            "starting": "🔄", 
            "streaming": "🔄",
            "completed": "✅",
            "failed": "❌"
        }.get(status, "⏳")

        # Show progress through all steps with navigation
        steps_overview = ""
        for i, (step_key, step_conf) in enumerate(self.steps_config.items()):
            step_status = self.step_statuses.get(step_key, "pending")
            step_emoji = {
                "pending": "⏳",
                "starting": "🔄", 
                "streaming": "🔄",
                "completed": "✅",
                "failed": "❌"
            }.get(step_status, "⏳")
            
            is_current = step_key == current_step_key
            is_completed = step_status == "completed"
            has_content = step_key in self.step_contents and self.step_contents[step_key] and len(self.step_contents[step_key].strip()) > 0
            
            step_class = "current-step" if is_current else ("completed-step" if is_completed else "other-step")
            clickable_class = "clickable" if has_content else ""
            
            onclick_handler = f"showStep('{step_key}')" if has_content else ""
            
            # Debug logging for step navigation
            logger.debug(f"Step {step_key}: status={step_status}, has_content={has_content}, content_length={len(self.step_contents.get(step_key, ''))}")
            
            steps_overview += f"""
            <div class="step-overview-item {step_class} {clickable_class}" 
                 data-step="{step_key}" 
                 onclick="{onclick_handler}"
                 title="{step_conf.get('description', '')}"
                 style="cursor: {'pointer' if has_content else 'default'};">
                {step_conf.get("icon", "📋")} {step_conf.get("name", step_key)} {step_emoji}
            </div>
            """

        # Format content based on step type
        formatted_content = self.format_step_content(current_step_key, content)

        # Single container with current step details and navigation
        container_html = f"""
        <div class="single-step-container" id="step-container-{current_step_key}">
            <div class="steps-overview">
                {steps_overview}
            </div>
            <div class="current-step-details" id="current-step-details">
                <div class="step-header">
                    <div class="step-title">
                        {step_config.get("icon", "📋")} {step_config.get("name", current_step_key)} {status_emoji}
                    </div>
                    <div class="step-progress">{progress:.0f}%</div>
                </div>
                <div class="step-description">
                    {step_config.get("description", "")}
                </div>
                <div class="step-content" id="step-content-display">
                    {formatted_content}
                </div>
            </div>
        </div>
        <script>
        // Store step data for navigation
        window.stepData = window.stepData || {{}};
        window.stepData['{current_step_key}'] = {{
            content: {json.dumps(str(content))},
            status: '{status}',
            progress: {progress},
            config: {{
                name: '{step_config.get("name", current_step_key)}',
                description: '{step_config.get("description", "")}',
                icon: '{step_config.get("icon", "📋")}'
            }}
        }};
        
        // Step navigation function
        function showStep(stepKey) {{
            const stepData = window.stepData[stepKey];
            if (!stepData) return;
            
            const detailsContainer = document.getElementById('current-step-details');
            const contentDisplay = document.getElementById('step-content-display');
            
            if (detailsContainer && contentDisplay) {{
                // Update step header
                const stepHeader = detailsContainer.querySelector('.step-header');
                const stepTitle = stepHeader.querySelector('.step-title');
                const stepProgress = stepHeader.querySelector('.step-progress');
                
                const statusEmoji = {{
                    "pending": "⏳",
                    "starting": "🔄", 
                    "streaming": "🔄",
                    "completed": "✅",
                    "failed": "❌"
                }}[stepData.status] || "⏳";
                
                stepTitle.innerHTML = `${{stepData.config.icon}} ${{stepData.config.name}} ${{statusEmoji}}`;
                stepProgress.innerHTML = `${{stepData.progress}}%`;
                
                // Update description
                const description = detailsContainer.querySelector('.step-description');
                description.innerHTML = stepData.config.description;
                
                // Format and update content
                const formattedContent = formatStepContent(stepKey, stepData.content);
                contentDisplay.innerHTML = formattedContent;
            }}
        }}
        
        // Content formatting function
        function formatStepContent(stepKey, content) {{
            if (!content || content.trim() === '') {{
                return '<div class="empty-content">No content available</div>';
            }}
            
            // Convert content to markdown-like format
            let formatted = content;
            
            // Basic markdown formatting
            formatted = formatted.replace(/\\\\*\\\\*(.*?)\\\\*\\\\*/g, '<strong>$1</strong>');
            formatted = formatted.replace(/\\\\*(.*?)\\\\*/g, '<em>$1</em>');
            formatted = formatted.replace(/```([\\s\\S]*?)```/g, '<pre class="code-block"><code>$1</code></pre>');
            formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
            formatted = formatted.replace(/\\n/g, '<br>');
            
            return `<div class="formatted-content">${{formatted}}</div>`;
        }}
        
        // Auto-scroll to current step
        setTimeout(function() {{
            const container = document.getElementById('step-container-{current_step_key}');
            if (container) {{
                container.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}, 100);
        
        // Auto-scroll to bottom during streaming
        if ('{status}' === 'streaming') {{
            setTimeout(function() {{
                const contentDisplay = document.getElementById('step-content-display');
                if (contentDisplay) {{
                    contentDisplay.scrollTop = contentDisplay.scrollHeight;
                }}
            }}, 100);
        }}
        </script>
        """

        return container_html

    def format_step_content(self, step_key: str, content: str) -> str:
        """Format step content - now handling pre-formatted markdown."""
        try:
            # Handle empty content
            if not content or content.strip() == "":
                return "<div class='empty-content'>No content available</div>"
            
            # Content is now pre-formatted markdown from enhanced workflow
            # Convert markdown to HTML for display
            def markdown_to_html(markdown_text):
                html = markdown_text
                
                # Convert headers
                import re
                html = re.sub(r'^# (.*)', r'<h1>\1</h1>', html, flags=re.MULTILINE)
                html = re.sub(r'^## (.*)', r'<h2>\1</h2>', html, flags=re.MULTILINE)
                html = re.sub(r'^### (.*)', r'<h3>\1</h3>', html, flags=re.MULTILINE)
                html = re.sub(r'^#### (.*)', r'<h4>\1</h4>', html, flags=re.MULTILINE)
                
                # Convert bold and italic
                html = re.sub(r'\\\*\\\*(.*?)\\\*\\\*', r'<strong>\\1</strong>', html)
                html = re.sub(r'\\\*(.*?)\\\*', r'<em>\\1</em>', html)
                
                # Convert code blocks
                html = re.sub(r'```(\w+)?\n(.*?)```', r'<pre class="code-block"><code class="language-\1">\2</code></pre>', html, flags=re.DOTALL)
                
                # Convert inline code
                html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
                
                # Convert lists
                html = re.sub(r'^- (.*)', r'<li>\1</li>', html, flags=re.MULTILINE)
                
                # Convert line breaks
                html = html.replace('\n', '<br>\n')
                
                return html
            
            # Get step icon and label
            step_icons = {
                "create_plan": "🎯",
                "create_prompts": "✏️", 
                "extract_data": "🔍",
                "arrange_data": "📊",
                "generate_code": "💻"
            }
            
            step_labels = {
                "create_plan": "Processing Plan",
                "create_prompts": "Prompt Engineering",
                "extract_data": "Data Extraction", 
                "arrange_data": "Data Arrangement",
                "generate_code": "Code Generation"
            }
            
            icon = step_icons.get(step_key, "📋")
            label = step_labels.get(step_key, "Processing")
            
            # Convert markdown to HTML
            formatted_content = markdown_to_html(content)
            
            # Determine step class
            step_class = "default-step"
            if step_key == "generate_code":
                step_class = "code-step"
            elif step_key == "extract_data":
                step_class = "data-step"
            elif step_key == "create_prompts":
                step_class = "prompts-step"
            
            return f"""
            <div class="step-content-wrapper {step_class}">
                <div class="step-content-header">
                    <span class="step-icon">{icon}</span>
                    <span class="step-label">{label}</span>
                </div>
                <div class="step-content-body markdown-content">
                    {formatted_content}
                </div>
            </div>
            """
            
        except Exception as e:
            logger.error(f"Error formatting step content: {str(e)}")
            return f"<div class='error-content'>Error formatting content: {str(e)}</div>"

    def format_results_as_markdown(self, final_data: dict) -> str:
        """Format the final results as user-friendly markdown."""
        try:
            markdown_content = "# 📊 Document Processing Results\n\n"
            
            for step_key, content in final_data.items():
                step_config = self.steps_config.get(step_key, {})
                step_name = step_config.get('name', step_key.replace('_', ' ').title())
                step_icon = step_config.get('icon', '📋')
                
                markdown_content += f"## {step_icon} {step_name}\n\n"
                
                if isinstance(content, dict):
                    # Handle dictionary content
                    for key, value in content.items():
                        if isinstance(value, (list, dict)):
                            markdown_content += f"**{key.replace('_', ' ').title()}:**\n```json\n{json.dumps(value, indent=2)}\n```\n\n"
                        else:
                            markdown_content += f"**{key.replace('_', ' ').title()}:** {value}\n\n"
                elif isinstance(content, list):
                    # Handle list content
                    for i, item in enumerate(content, 1):
                        if isinstance(item, dict):
                            markdown_content += f"### Item {i}\n"
                            for key, value in item.items():
                                markdown_content += f"- **{key.replace('_', ' ').title()}:** {value}\n"
                            markdown_content += "\n"
                        else:
                            markdown_content += f"- {item}\n"
                    markdown_content += "\n"
                else:
                    # Handle string content
                    if isinstance(content, str):
                        try:
                            # Try to parse as JSON first
                            parsed = json.loads(content)
                            markdown_content += f"```json\n{json.dumps(parsed, indent=2)}\n```\n\n"
                        except:
                            # If not JSON, treat as plain text
                            markdown_content += f"```\n{content}\n```\n\n"
                    else:
                        markdown_content += f"```\n{str(content)}\n```\n\n"
                        
                markdown_content += "---\n\n"
            
            return markdown_content
            
        except Exception as e:
            logger.error(f"Error formatting results as markdown: {str(e)}")
            # Fallback to JSON if markdown formatting fails
            return f"```json\n{json.dumps(final_data, indent=2)}\n```"

    def render_progress_bar(self, current_step: int, total_steps: int, step_name: str):
        """Render animated progress bar."""
        progress = current_step / total_steps if total_steps > 0 else 0

        progress_html = f"""
        <div class="progress-container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="font-weight: bold;">Step {current_step} of {total_steps}</span>
                <span style="color: #667eea; font-weight: bold;">{step_name}</span>
            </div>
            <div style="background: rgba(255,255,255,0.2); border-radius: 10px; height: 8px; overflow: hidden;">
                <div style="background: linear-gradient(90deg, #667eea, #764ba2); height: 100%; width: {progress * 100}%; transition: width 0.5s ease;"></div>
            </div>
        </div>
        """

        return progress_html

    def get_prompt_text(self, category_id, prompt_id):
        """Get the full text of a specific prompt."""
        prompt = prompt_gallery.get_prompt_by_id(category_id, prompt_id)
        return prompt.get('prompt', '') if prompt else ''

    def download_processed_files(self):
        """Create a zip file of all processed files and return for download."""
        # Update activity for auto-shutdown monitoring
        shutdown_manager.update_activity()
        
        try:
            import zipfile
            import tempfile
            import os
            import shutil
            from datetime import datetime
            
            # Get session output directory
            session_output_dir = Path(settings.TEMP_DIR) / self.session_id / "output"
            
            if not session_output_dir.exists():
                logger.warning(f"Output directory does not exist: {session_output_dir}")
                return None
                
            # Create a properly named zip file in a temporary location that Gradio can access
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"processed_files_{self.session_id}_{timestamp}.zip"
            
            # Use Python's tempfile to create a file in the system temp directory
            # This ensures Gradio can access it properly
            temp_dir = tempfile.gettempdir()
            zip_path = Path(temp_dir) / zip_filename
                
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all files from output directory
                file_count = 0
                for file_path in session_output_dir.rglob('*'):
                    if file_path.is_file():
                        # Calculate relative path for zip
                        arcname = file_path.relative_to(session_output_dir)
                        zipf.write(file_path, arcname)
                        file_count += 1
                        logger.debug(f"Added to zip: {arcname}")
                        
            if file_count == 0:
                logger.warning("No files found to download")
                # Debug: List all files in session directory
                session_dir = Path(settings.TEMP_DIR) / self.session_id
                if session_dir.exists():
                    logger.info(f"Session directory exists: {session_dir}")
                    for subdir in ['input', 'output', 'temp']:
                        subdir_path = session_dir / subdir
                        if subdir_path.exists():
                            files = list(subdir_path.glob('*'))
                            logger.info(f"{subdir} directory has {len(files)} files: {[f.name for f in files]}")
                        else:
                            logger.info(f"{subdir} directory does not exist")
                else:
                    logger.warning(f"Session directory does not exist: {session_dir}")
                # Clean up empty zip file
                if zip_path.exists():
                    zip_path.unlink()
                return None
                
            logger.info(f"Created zip file with {file_count} files: {zip_path}")
            
            # Ensure the file exists and has content
            if zip_path.exists() and zip_path.stat().st_size > 0:
                # For Gradio file downloads, we need to return the file path in a specific way
                abs_path = str(zip_path.absolute())
                logger.info(f"Returning zip file path for download: {abs_path}")
                logger.info(f"File size: {zip_path.stat().st_size} bytes")
                
                # Try to make the file accessible by setting proper permissions
                os.chmod(abs_path, 0o644)
                
                # Return the file path for Gradio to handle
                # Make sure to return the path in a way Gradio can process
                return abs_path
            else:
                logger.error("Zip file was created but is empty or doesn't exist")
                return None
                
        except Exception as e:
            logger.error(f"Error creating download: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return None


def create_gradio_app():
    """Create the main Gradio application."""
    ui = WorkflowUI()

    async def process_file(file, verbose_print, progress=gr.Progress()):
        """Process uploaded file with automated financial data extraction."""
        logger.info(f"Processing request - File: {file}, Verbose: {verbose_print}")
        
        # Update activity for auto-shutdown monitoring
        shutdown_manager.update_activity()

        if not file:
            logger.warning("Missing file")
            yield "", "", "", None
            return

        # Validate file (file.name contains Gradio's temp path)
        validation = ui.validate_file(file.name)
        logger.info(f"File validation result: {validation}")

        if not validation["valid"]:
            logger.error(f"File validation failed: {validation['error']}")
            yield "", "", "", None
            return

        # Save file to our session directory (file is the Gradio temp file object)
        logger.info("Saving uploaded file to session directory...")
        
        temp_path = ui.file_handler.save_uploaded_file(file, ui.session_id)
        logger.info(f"File saved from Gradio temp to session temp: {temp_path}")

        # Get file preview
        file_preview = ui.get_file_preview(temp_path)
        file_info = validation["file_info"]
        logger.info(f"File info: {file_info}")

        # Progress tracking variables
        progress_html = ""
        steps_html = ""
        status_message = "🚀 Starting processing..."

        def update_progress(prog_html, step_html):
            nonlocal progress_html, steps_html
            progress_html = prog_html
            steps_html = step_html
            # Yield intermediate results for real-time updates
            return (progress_html, steps_html, "", gr.Column(visible=False))

        def update_status(message, status_type):
            nonlocal status_message
            status_message = message
            logger.info(f"Status update: {message} ({status_type})")

        try:
            logger.info("Starting document processing...")

            total_steps = len(ui.steps_config)
            step_mapping = {
                step: i + 1 for i, step in enumerate(ui.steps_config.keys())
            }

            # Reset state
            ui.current_step = 0
            ui.step_contents = {}
            ui.step_statuses = {}

            logger.info(f"Starting streaming process with {total_steps} steps")

            # Process with new section-by-section complete output approach
            response_count = 0
            
            async for response in ui.workflow.run_financial_extraction(
                file_path=temp_path
            ):
                response_count += 1
                logger.info(f"Workflow response received: {response}")
                
                # Extract response info
                response_type = response.get("type", "unknown")
                step_key = response.get("step", "processing")
                message = response.get("message", "")
                data = response.get("data", "")
                agent = response.get("agent", "")
                
                # Ensure step_key is valid - map unknown keys to known ones
                if step_key not in ui.steps_config:
                    # Map common variations to correct keys
                    step_key_mapping = {
                        "processing": "data_extraction",
                        "extract_data": "data_extraction",
                        "arrange_data": "data_arrangement", 
                        "generate_excel": "excel_generation",
                        "generate_code": "excel_generation"
                    }
                    step_key = step_key_mapping.get(step_key, "data_extraction")
                    logger.info(f"Mapped unknown step key to: {step_key}")
                
                logger.info(f"Response type: {response_type}, Step: {step_key}, Agent: {agent}")
                
                # Handle different response types
                if response_type == "step_start":
                    # Step is starting - show progress message
                    ui.step_statuses[step_key] = "starting"
                    ui.step_contents[step_key] = message
                    
                    step_num = step_mapping.get(step_key, ui.current_step + 1)
                    if step_num > ui.current_step:
                        ui.current_step = step_num
                    
                    logger.info(f"Step started: {step_key} - {message}")
                    
                    # Update UI with starting message
                    current_step_name = (
                        list(ui.steps_config.keys())[ui.current_step - 1]
                        if ui.current_step > 0
                        else "Starting"
                    )
                    progress_html = ui.render_progress_bar(
                        ui.current_step, total_steps, current_step_name
                    )
                    steps_html = ui.render_multi_agent_workflow()
                    yield (progress_html, steps_html, "", gr.Column(visible=False))
                    
                elif response_type == "step_complete":
                    # Step completed - show complete output (NO JSON PARSING NEEDED!)
                    ui.step_statuses[step_key] = "completed"
                    ui.step_contents[step_key] = data  # Complete output, no parsing required
                    
                    logger.info(f"Step completed: {step_key} by {agent}")
                    
                    # Update UI with complete results
                    current_step_name = (
                        list(ui.steps_config.keys())[ui.current_step - 1]
                        if ui.current_step > 0
                        else "Completed"
                    )
                    progress_html = ui.render_progress_bar(
                        ui.current_step, total_steps, current_step_name
                    )
                    steps_html = ui.render_multi_agent_workflow()
                    yield (progress_html, steps_html, "", gr.Column(visible=False))
                    
                elif response_type == "error":
                    # Handle errors
                    ui.step_statuses[step_key] = "failed"
                    ui.step_contents[step_key] = message
                    logger.error(f"Step failed: {step_key} - {message}")
                    
                    # Update UI with error
                    progress_html = ui.render_progress_bar(
                        ui.current_step, total_steps, "Error"
                    )
                    steps_html = ui.render_multi_agent_workflow()
                    yield (progress_html, steps_html, "", gr.Column(visible=False))
                    break
                    
                elif response_type == "final_result":
                    # Final results - all steps completed
                    logger.info("All steps completed successfully")
                    break

            logger.info(f"Processing complete. Total responses received: {response_count}")

            # Processing complete - final status
            status_message = "🎉 Processing Complete!"
            
            # Return final results - use the last workflow result if available
            final_data = {}
            for step_key, content in ui.step_contents.items():
                final_data[step_key] = content  # Content is already formatted as markdown

            # --- NEW: Read the arranged data file for the final report ---
            arranged_data_filepath = ui.workflow.session_output_dir / "arranged_comprehensive_financial_data.json"
            if arranged_data_filepath.exists():
                with open(arranged_data_filepath, 'r') as f:
                    arranged_data_content = json.load(f)
                # Replace the confirmation message with the actual data
                final_data['data_arrangement'] = f"### Arranged Data\n\n```json\n{json.dumps(arranged_data_content, indent=2)}\n```"

            # Format final results as comprehensive markdown report
            results_markdown = "# 📊 Complete Processing Report\n\n"
            for step_key, content in final_data.items():
                if content and content.strip():
                    results_markdown += content + "\n\n"
            
            # Add code execution results if available  
            session_output_dir = Path(settings.TEMP_DIR) / ui.session_id / "output"
            results_markdown += "## 💻 Code Execution Results\n\n"
            results_markdown += f"**Output Directory**: `{session_output_dir}`\n\n"
            
            # Check if files were generated
            if session_output_dir.exists():
                files = list(session_output_dir.glob('*'))
                if files:
                    results_markdown += f"✅ **Execution Status**: Success ({len(files)} files generated)\n\n"
                    results_markdown += "**Generated Files:**\n"
                    for file in files:
                        results_markdown += f"- `{file.name}` ({file.stat().st_size} bytes)\n"
                    results_markdown += "\n"
                else:
                    results_markdown += "ℹ️ **Execution Status**: Code generated but no output files found\n\n"
            else:
                results_markdown += "ℹ️ **Execution Status**: Output directory not found\n\n"
            
            logger.info("Document processing completed successfully")
            if verbose_print:
                logger.info("Final model response:\n" + results_markdown)
            yield (progress_html, steps_html, results_markdown, gr.Column(visible=True))

        except Exception as e:
            logger.error(f"Processing failed: {str(e)}", exc_info=True)
            error_message = f"❌ Processing failed: {str(e)}"
            error_markdown = f"# ❌ Processing Error\n\n**Error:** {str(e)}\n\nPlease try again or check the logs for more details."
            yield ("", "", error_markdown, gr.Column(visible=True))

    
    def reset_session():
        """Reset the current session."""
        ui.session_id = str(uuid.uuid4())[:8]  # Generate new session ID
        ui.workflow = FinancialDataExtractionWorkflow(session_id=ui.session_id)  # Create new workflow instance with session ID
        ui.current_step = 0
        ui.step_contents = {}
        ui.step_statuses = {}
        ui.processing_started = False
        return ("", "", "", None)

    # Create Gradio interface
    with gr.Blocks(css=custom_css, title="📊 Data Extractor Using Gemini") as app:
        # Header
        gr.HTML("""
        <div class="header-title">
            📊 Data Extractor Using Gemini
        </div>
        """)

        with gr.Row():
            with gr.Column(scale=1):
                # Configuration Panel
                gr.Markdown("## ⚙️ Configuration")

                # Session info
                session_info = gr.Textbox(
                    label="Session ID", value=ui.session_id, interactive=False
                )

                # File upload
                gr.Markdown("### 📄 Upload Document")
                file_input = gr.File(
                    label="Choose a file",
                    file_types=[f".{ext}" for ext in settings.SUPPORTED_FILE_TYPES],
                )
                

                # Info about automated processing
                gr.Markdown("### 🎯 Automated Financial Data Extraction")
                gr.Markdown("This application automatically extracts financial data points from uploaded documents and generates comprehensive analysis reports. No additional input required!")

                # Control buttons
                with gr.Row():
                    process_btn = gr.Button(
                        "🚀 Start Processing", variant="primary", scale=2
                    )
                    reset_btn = gr.Button("🔄 Reset Session", scale=1)

                # System status section completely removed per user request

            with gr.Column(scale=2):
                # Processing Panel
                gr.Markdown("## ⚡ Processing Status")

                # Progress bar
                progress_display = gr.HTML(label="Progress")

                # Steps display
                steps_display = gr.HTML(label="Processing Steps")

                # Results - Hidden initially, shown when processing completes
                verbose_checkbox = gr.Checkbox(label="Print model response", value=False)
                
                 # Results section
                results_section = gr.Column(visible=False)
                with results_section:
                    gr.Markdown("### 📊 Results")
                    results_display = gr.Code(
                        label="Final Results", language="markdown", lines=10
                    )
                    
                    # Download section
                    gr.Markdown("### ⬇️ Download Processed Files")
                    download_btn = gr.Button("📥 Download All Files", variant="primary")
                    download_output = gr.File(
                        label="Download Files",
                        file_count="single",
                        file_types=[".zip"],
                        interactive=False,
                        visible=True
                    )

        # Event handlers
        process_btn.click(
            fn=process_file,
            inputs=[file_input, verbose_checkbox],
            outputs=[progress_display, steps_display, results_display, results_section],
        )

        download_btn.click(
            fn=ui.download_processed_files,
            outputs=[download_output],
            show_progress=True
        )

        reset_btn.click(
            fn=reset_session,
            outputs=[progress_display, steps_display, results_display, download_output],
        )

    return app


def main():
    """Main application entry point."""
    app = create_gradio_app()
    
    # Start auto-shutdown monitoring
    shutdown_manager.start_monitoring(app)
    
    logger.info("Starting Gradio application with auto-shutdown enabled")
    logger.info(f"Auto-shutdown timeout: {INACTIVITY_TIMEOUT_MINUTES} minutes")
    logger.info("Press Ctrl+C to stop the server manually")

    try:
        # Launch the app
        app.launch(
            server_name="0.0.0.0",
            server_port=7860,
            share=False,
            debug=False,
            show_error=True,
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        shutdown_manager._shutdown_server()
    except Exception as e:
        logger.error(f"Error during app launch: {e}")
        shutdown_manager._shutdown_server()


if __name__ == "__main__":
    main()
