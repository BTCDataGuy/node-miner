FROM ubuntu:22.04

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies for building cpuminer-multi and running Flask
RUN apt-get update && apt-get install -y \
    build-essential \
    libcurl4-openssl-dev \
    libssl-dev \
    libjansson-dev \
    libgmp-dev \
    zlib1g-dev \
    automake \
    autoconf \
    pkg-config \
    git \
    python3 \
    python3-pip \
    curl \
    cpulimit \
    && rm -rf /var/lib/apt/lists/*

# Clone and build cpuminer-multi
WORKDIR /tmp
RUN git clone https://github.com/tpruvot/cpuminer-multi.git
WORKDIR /tmp/cpuminer-multi
RUN ./build.sh || (./autogen.sh && ./configure CFLAGS="-O3" && make)
RUN make install

# Set up application directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py /app/
COPY index.html /app/
COPY config.json /app/

# Copy static files (includes all CSS, JS, fonts, etc.)
COPY static/ /app/static/

# Create data directory for persistent config
RUN mkdir -p /data

# Expose Flask port
EXPOSE 5000

# Run Flask app
CMD ["python3", "app.py"]
