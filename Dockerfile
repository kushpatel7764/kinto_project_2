# Stage 1: Build Python dependencies and prepare Kinto Admin
FROM python:3.10-bullseye AS python-builder

# Create a virtual environment for Python
RUN python -m venv /opt/venv
ARG KINTO_VERSION=1
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_KINTO=${KINTO_VERSION} \
    PATH="/opt/venv/bin:$PATH"

# Install bash to ensure compatibility with the script
RUN apt-get update && apt-get install -y bash curl tar

# Set working directory for Kinto Admin
WORKDIR /kinto-admin

# Copy necessary files for Kinto Admin
COPY kinto/plugins/admin kinto/plugins/admin
COPY scripts/pull-kinto-admin.sh .

# Ensure the environment has required tools
RUN apt-get update && apt-get install -y bash curl tar dos2unix

# Convert Windows-style line endings to Unix
RUN dos2unix pull-kinto-admin.sh kinto/plugins/admin/VERSION

# Ensure the script is executable
RUN chmod +x pull-kinto-admin.sh

# Run the script explicitly with bash
RUN /bin/bash pull-kinto-admin.sh

# Set working directory for Kinto
WORKDIR /pkg-kinto

# Install Python dependencies
COPY constraints.txt pyproject.toml ./
RUN pip install --upgrade pip && pip install -r constraints.txt

# Copy the Kinto source code
COPY kinto/ kinto/
RUN cp -r /kinto-admin/kinto/plugins/admin/build kinto/plugins/admin/
RUN pip install ".[postgresql,memcached,monitoring]" -c constraints.txt && pip install kinto-attachment kinto-emailer httpie

# Stage 2: Prepare final runtime environment
FROM python:3.10-slim-bullseye

# Create app user
RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid 10001 --home /app --create-home app

# Copy the virtual environment from the build stage
COPY --from=python-builder /opt/venv /opt/venv

# Set environment variables
ENV KINTO_INI=/etc/kinto/kinto.ini \
    PORT=8888 \
    PATH="/opt/venv/bin:$PATH"

# Initialize Kinto
RUN kinto init --ini $KINTO_INI --host 0.0.0.0 --backend=postgresql --cache-backend=postgresql

# Set working directory for the app
WORKDIR /app
USER app

# Run database migrations and start the Kinto server
CMD ["sh", "-c", "kinto migrate --ini $KINTO_INI && kinto start --ini $KINTO_INI --port $PORT"]