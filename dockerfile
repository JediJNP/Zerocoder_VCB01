FROM python:3.11-slim

# System dependencies needed for pygame (SDL2, fonts, X11)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 libxext6 libxrender1 libxrandr2 libxcursor1 libxi6 libxinerama1 libxxf86vm1 \
    libgl1 libglu1-mesa \
    libasound2 libpulse0 libudev1 libdbus-1-3 \
    libfreetype6 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    SDL_VIDEODRIVER=x11

WORKDIR /app

# Copy source
COPY VCB01 ./VCB01
COPY gui.py ./

# Use up-to-date pip and install runtime deps
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir pygame

# The game window will appear via X11 forwarding
ENTRYPOINT ["python", "gui.py"]

