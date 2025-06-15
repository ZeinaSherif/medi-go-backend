# Use a lightweight Python image
# Use Python 3.9.13 as the base image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Set environment variable for Uvicorn (optional)
ENV PORT=8080

# Expose the port that Uvicorn will run on
EXPOSE 8080

# Start the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
