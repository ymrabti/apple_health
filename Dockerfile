# Use a lightweight base image with Chrome
FROM debian:bullseye-slim
# docker build -t safe-chrome .
# docker run -it --rm --shm-size=1gb safe-chrome

# Avoid interactive prompts during install
ENV DEBIAN_FRONTEND=noninteractive

# Install dependencies
RUN apt-get update && apt-get install -y   wget   gnupg   ca-certificates   fonts-liberation   libappindicator3-1   libasound2   libatk-bridge2.0-0   libatk1.0-0   libcups2   libdbus-1-3   libgdk-pixbuf2.0-0   libnspr4   libnss3   libx11-xcb1   libxcomposite1   libxdamage1   libxrandr2   xdg-utils   curl   unzip   --no-install-recommends &&   rm -rf /var/lib/apt/lists/*

# Download and install the latest stable Chrome
RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb &&  apt-get update &&  apt-get install -y /tmp/chrome.deb &&  rm /tmp/chrome.deb

# Run as non-root user for extra safety
RUN useradd -m chromeuser
USER chromeuser

# Entrypoint
# CMD [ "google-chrome", "--no-sandbox", "--disable-dev-shm-usage", "--disable-extensions", "--incognito", "--disable-gpu" ]
CMD [ "google-chrome", "--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--dump-dom", "https://example.com" ]
