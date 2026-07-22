# Use official Node.js image
FROM node:20

# Set working directory
WORKDIR /app

# Increase file descriptor limits for file watchers
RUN echo "fs.inotify.max_user_watches=524288" >> /etc/sysctl.conf && \
    echo "fs.file-max=2097152" >> /etc/sysctl.conf

# Copy package files for reproducible installs
COPY package.json package-lock.json ./

# Install dependencies using lockfile for reproducible builds
RUN npm ci

# Copy the entire React app
COPY . .
RUN rm -f .env

# Create a non-root user for running the application
# Using UID 1001 to avoid conflicts with common system users
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --shell /bin/bash --create-home appuser

# Set ownership of the application directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the Vite dev server port (configured to 3000 in vite.config.ts)
EXPOSE 3000

# Start the Vite dev server
CMD ["npm", "start"]
