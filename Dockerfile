# Knowledge Acquisition — container image for the NEXOS Universal Build (Cloud Run IT).
#
# Build only: this image does not make the service deployable. KA keeps its object store as JSON files plus
# in-process caches under KA_STORAGE_ROOT and runs background threads, so a Cloud Run deployment needs a durable
# volume at /data, exactly one instance and CPU always allocated; see the readiness notes in
# pankajkamble75/nexos-deployment.
#
#   * one importable copy of the package, installed into /opt/venv from a wheel (no source tree at runtime,
#     so config.py finds no .env next to it);
#   * the store on an explicit path outside the code (KA_STORAGE_ROOT=/data/ka_storage);
#   * no secrets in the image (ANTHROPIC_API_KEY, KA_ACCESS_TOKEN, KA_AGENTX_TOKEN, … come from Secret Manager);
#   * non-root, binds 0.0.0.0 on Cloud Run's $PORT (default 8080) via KA_BACKEND_PORT;
#   * the graph grammar bundled read-only at /opt/ka/grammar (KA_GRAMMAR_DIR), so the service is ready without an
#     Enterprise OS checkout or a Knowledge Worker call: grammar.json + process_types.json copied verbatim from
#     pankajkamble75/knowledge-worker knowledge_worker/graph_model (see docs/deploy/cloud-run-mvp.md).
#
# NEXOS Cloud Run MVP: KA_STORAGE_ROOT is set at deploy time to the NFS v4 mount (/mnt/nfs/ka/ka_storage); see
# docs/deploy/cloud-run-mvp.md for the env vars, probes and the one-off demo seed.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

# ── build: dependencies (hash-locked) and the wheel ─────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
RUN python -m venv /opt/venv
COPY requirements.lock requirements-build.lock ./
RUN /opt/venv/bin/pip install --require-hashes --no-deps -r requirements.lock \
 && python -m pip install --require-hashes --no-deps -r requirements-build.lock
COPY pyproject.toml README.md ./
COPY ka ./ka
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir /wheels . \
 && /opt/venv/bin/pip install --no-deps /wheels/knowledge_acquisition-*.whl \
 && /opt/venv/bin/python -I -c "import ka, sys; assert '/opt/venv/' in ka.__file__, ka.__file__"

# ── runtime ─────────────────────────────────────────────────────────────────────────────────────────────────────
FROM ${PYTHON_IMAGE} AS runtime
ARG KA_UID=10001
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    KA_BACKEND_HOST=0.0.0.0 \
    KA_STORAGE_ROOT=/data/ka_storage \
    KA_ACCESS_POLICY=token \
    KA_GRAMMAR_DIR=/opt/ka/grammar
RUN groupadd --system --gid ${KA_UID} ka \
 && useradd --system --uid ${KA_UID} --gid ka --home-dir /data --shell /usr/sbin/nologin ka \
 && mkdir -p /data/ka_storage \
 && chown -R ka:ka /data
COPY --from=build /opt/venv /opt/venv
# root-owned and read-only for uid 10001; the load check fails the build if either file is not a grammar / process-types version
COPY deploy/grammar/grammar.json deploy/grammar/process_types.json /opt/ka/grammar/
RUN chmod 0444 /opt/ka/grammar/*.json \
 && python -I -c "import json; g=json.load(open('/opt/ka/grammar/grammar.json')); t=json.load(open('/opt/ka/grammar/process_types.json')); \
assert g['version'].startswith('grammar/') and t['version'].startswith('process-types/'), (g['version'], t['version'])"
WORKDIR /data
USER ka
VOLUME ["/data"]
EXPOSE 8080
# exec: the server is PID 1 and receives SIGTERM directly.
CMD ["sh", "-c", "KA_BACKEND_PORT=\"$PORT\" exec knowledge-acquisition serve"]
