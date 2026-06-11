# This docker file is used for local development via docker-compose
# Creating image based on official python3 image
FROM python:3.12.4

# Fix python printing
ENV PYTHONUNBUFFERED=1

# Installing all python dependencies
ADD requirements/ requirements/
RUN pip install -r requirements/base.txt

# ---- Universal CRLF fix ----
# Copy entrypoint OUTSIDE /app so the bind mount won't overwrite it.
# Use sed to strip any \r (Windows CRLF) and make it executable.
COPY entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//' /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Get the django project into the docker container
RUN mkdir -p /app
WORKDIR /app
ADD ./ /app/