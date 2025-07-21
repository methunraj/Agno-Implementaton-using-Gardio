# Agno Document Analysis Workflow

A sophisticated document processing application built with Agno v1.7.4 featuring a multi-agent workflow for intelligent document analysis and data extraction.

## Features

- **5-Agent Workflow**: Coordinator, Prompt Engineer, Data Extractor, Data Arranger, Code Generator
- **Multi-format Support**: PDF, TXT, PNG, JPG, JPEG, DOCX, XLSX, CSV, MD, JSON, XML, HTML, PY, JS, TS, DOC, XLS, PPT, PPTX
- **Real-time Processing**: Streaming interface with live updates
- **Sandboxed Execution**: Safe code execution environment
- **Beautiful UI**: Modern Gradio interface with custom animations

## Quick Start

### Automated Installation

```bash
# Clone the repository
git clone <repository-url>
cd Data_Extractor

# Quick installation (recommended)
./install.sh

# Or use Python setup script
python setup.py
```

### Manual Installation

```bash
# Create virtual environment
python -m venv data_extractor_env
source data_extractor_env/bin/activate  # On Windows: data_extractor_env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env  # Update with your API keys

# Run the application
python app.py
```

## Installation Options

### Requirements Files

- **`requirements-minimal.txt`**: Essential dependencies only (~50 packages)
  ```bash
  pip install -r requirements-minimal.txt
  ```

- **`requirements.txt`**: Complete feature set (~200+ packages)
  ```bash
  pip install -r requirements.txt
  ```

- **`requirements-dev.txt`**: Development dependencies with testing tools
  ```bash
  pip install -r requirements-dev.txt
  ```

### System Dependencies

Some features require system-level dependencies:

**macOS:**
```bash
brew install tesseract imagemagick poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr libmagickwand-dev poppler-utils
```

**Windows:**
```bash
choco install tesseract imagemagick poppler
```

## Usage

1. **Setup Environment**: Follow installation instructions above
2. **Configure API Keys**: Update `.env` file with your API keys
3. **Upload Document**: Support for 20+ file formats
4. **Select Analysis**: Choose from predefined types or custom prompts
5. **Process**: Watch the multi-agent workflow in real-time
6. **Download Results**: Get structured data and generated Excel reports

## Environment Variables

Create a `.env` file with the following variables:

```bash
# Required API Keys
GOOGLE_API_KEY=your_google_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional

# Application Settings
DEBUG=False
LOG_LEVEL=INFO
SESSION_TIMEOUT=3600

# File Processing
MAX_FILE_SIZE=50MB
SUPPORTED_FORMATS=pdf,docx,xlsx,txt

# Database (Optional)
DATABASE_URL=sqlite:///data_extractor.db
```

## Advanced Features

### Financial Document Processing
- Comprehensive financial data extraction
- 13-category data organization
- Excel report generation with charts
- XBRL and SEC filing support

### OCR and Image Processing
- EasyOCR and PaddleOCR integration
- Tesseract OCR support
- Advanced image preprocessing

### Machine Learning Integration
- TensorFlow and PyTorch support
- Scikit-learn for data analysis
- XGBoost and LightGBM for predictions

## Troubleshooting

For detailed troubleshooting and installation issues, see:
- [`INSTALLATION.md`](INSTALLATION.md) - Comprehensive installation guide
- [`FIXES_SUMMARY.md`](FIXES_SUMMARY.md) - Known issues and solutions

### Common Issues

1. **Import Errors**: Try minimal installation first
2. **OCR Issues**: Install system dependencies
3. **Memory Issues**: Use smaller batch sizes
4. **API Errors**: Verify API keys in `.env` file

## Docker Support

```dockerfile
# Build and run with Docker
docker build -t data-extractor .
docker run -p 7860:7860 --env-file .env data-extractor
```
