# Use an official lightweight Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app_1

# Copy your requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app's code into the container
COPY . .

# Give execution rights on the entrypoint
RUN chmod +x entrypoint.sh

# Expose port 8080 (Cloud Run's default)
EXPOSE 8080

# Command to run both the backend and frontend
CMD ["./entrypoint.sh"]