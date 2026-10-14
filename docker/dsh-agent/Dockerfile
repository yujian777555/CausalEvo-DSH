FROM python@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

ENV PYTHONDONTWRITEBYTECODE=1

# Fully offline install from vendored, hash-recorded wheels (see
# docker/dsh-agent/wheels/SHA256SUMS). No network needed at build time.
COPY wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links /tmp/wheels \
        deepseek-harness-sdk==0.1.5rc1 \
    && rm -rf /tmp/wheels

# Unprivileged user; workspace mounted at /work by the runner.
RUN useradd -m agent
USER agent

COPY agent_entry.py /opt/agent_entry.py
ENTRYPOINT ["python", "/opt/agent_entry.py"]
