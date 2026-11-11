FROM python:3.11-slim-bookworm

# A compact, explicit runtime avoids pulling the much larger moving notebook image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless ca-certificates curl procps tini fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && ln -s /usr/local/lib/python3.11/site-packages/pyspark /usr/local/spark \
    && useradd --create-home --uid 1000 --shell /bin/bash jovyan \
    && mkdir -p /home/jovyan/work \
    && chown -R jovyan:jovyan /home/jovyan

COPY scripts/start-notebook.sh /usr/local/bin/start-notebook.sh
RUN chmod +x /usr/local/bin/start-notebook.sh

ENV SPARK_HOME=/usr/local/spark
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH=/usr/local/spark/bin:$PATH
ENV PYTHONPATH=/home/jovyan/work/src
ENV PYSPARK_PYTHON=python3
ENV PYSPARK_DRIVER_PYTHON=python3
USER jovyan
WORKDIR /home/jovyan/work
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["start-notebook.sh"]
