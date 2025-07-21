# Use the official Python 3.12 slim image as a base
FROM python:3.12-slim

# Set environment variables for better Python behavior
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# Explicitly set the user to root for global permissions
USER root

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies required for AI agents and data processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    cmake \
    pkg-config \
    curl \
    wget \
    git \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    libpng-dev \
    libfreetype6-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to latest version with global permissions
RUN python -m pip install --upgrade pip setuptools wheel

# Set global pip configuration for permissions
RUN pip config set global.trusted-host "pypi.org files.pythonhosted.org pypi.python.org" \
    && pip config set global.no-cache-dir true \
    && pip config set global.disable-pip-version-check true

# Copy the requirements file first to leverage Docker's build cache
COPY requirements.txt .

# Install Python dependencies with explicit global permissions
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the application code into the /app directory
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p temp logs uploads downloads cache \
    && chmod -R 755 /app \
    && chmod -R 777 temp logs uploads downloads cache

# Set global write permissions for Python site-packages (for agent installations)
RUN chmod -R 777 /usr/local/lib/python3.12/site-packages/ \
    && chmod -R 777 /usr/local/bin/

# Set environment variables for the application.
ENV PYTHONPATH=/app
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860
# Set the Matplotlib backend to 'Agg' to prevent it from trying to use a
# graphical user interface, which is not available in the container.
ENV MPLBACKEND=Agg

# Expose the port that the Gradio application will run on.
EXPOSE 7860

# The command to run when the container starts.
CMD ["python", "app.py"]
