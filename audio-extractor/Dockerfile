FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/* && useradd --uid 10001 --create-home extractor && mkdir /data && chown extractor:extractor /data
WORKDIR /app
COPY service.py /app/service.py
USER 10001
ENV PYTHONUNBUFFERED=1 PORT=8080 DATA_DIR=/data
EXPOSE 8080
CMD ["python", "service.py"]
