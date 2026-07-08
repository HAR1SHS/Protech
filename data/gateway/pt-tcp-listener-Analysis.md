# pt-tcp-listener — Complete Technical Analysis & Reference

> **Location:** `data/pt-tcp-listener/`
> **What it is:** The **cloud-native ingestion layer** of a system called **DecodingEngine** — a small, multi-tenant **Python 3.12 asyncio** service that listens on plant-floor TCP ports, validates legacy meter checksums, and publishes the **raw** meter strings to **Azure Event Hubs** (Kafka-compatible).
> **Who it replaces:** the legacy .NET apps in [`../PortApps`](../PortApps/PortApps-Analysis.md) — `DP-31002`, `DP-31009`, `LP-30009`, and the control-port app (`MS16002` / `BmsSmart-CtrlGateway`).
> **Owner:** Sarral-ProTech (proprietary).

```
Plant meters ──► TCP listener (THIS service) ──► Event Hubs ──► Databricks ──► Delta + Lakebase
```

---

## Table of Contents

1. [Where this fits — relationship to PortApps](#1-where-this-fits--relationship-to-portapps)
2. [What it does (and deliberately does NOT do)](#2-what-it-does-and-deliberately-does-not-do)
3. [Folder inventory](#3-folder-inventory)
4. [Architecture & runtime model](#4-architecture--runtime-model)
5. [The packet protocol & checksum](#5-the-packet-protocol--checksum)
6. [End-to-end data flow](#6-end-to-end-data-flow)
7. [File-by-file analysis](#7-file-by-file-analysis)
   - [Source: `src/tcp_listener/`](#71-source--srctcp_listener)
   - [Tests: `tests/`](#72-tests--tests)
   - [Scripts: `scripts/`](#73-scripts--scripts)
   - [Infra: `infra/`](#74-infra--infra)
   - [Build & project files](#75-build--project-files)
8. [Multi-tenant configuration model](#8-multi-tenant-configuration-model)
9. [Configuration reference (env vars)](#9-configuration-reference-env-vars)
10. [Observability (metrics, health, logs)](#10-observability-metrics-health-logs)
11. [Reliability & delivery semantics](#11-reliability--delivery-semantics)
12. [Dependencies](#12-dependencies)
13. [Observations, discrepancies & risks](#13-observations-discrepancies--risks)
14. [Quick reference tables](#14-quick-reference-tables)

---

## 1. Where this fits — relationship to PortApps

The legacy [`PortApps`](../PortApps/PortApps-Analysis.md) system did **everything on-premise**: each `DP-*`/`LP-*` app accepted TCP, validated the checksum, **decoded** the raw string against the `CustomerUtilities` catalog, and wrote rows into SQL Server via stored procedures.

`pt-tcp-listener` splits that monolith into a modern pipeline and takes only the **first hop**:

| Concern | Legacy PortApps (.NET) | pt-tcp-listener (Python) |
|---------|------------------------|---------------------------|
| Accept TCP on plant ports | ✅ per-port process | ✅ one process, all ports (asyncio) |
| Validate checksum | ✅ `CheckSum.dll` | ✅ port of the same algorithm |
| **Decode** raw → readings | ✅ in-process | ❌ **moved downstream** (Databricks) |
| Persist | ✅ SQL stored procs | ❌ **publishes raw bytes to Event Hubs** |
| Multi-customer | ❌ separate builds/configs | ✅ **one image, env-driven** |
| Hosting | Windows Service / console | Docker → **Azure Container Apps** |

So this service is intentionally **thin**: receive → checksum → forward raw. All meaning (the `Byteposition`/`TotalBytes`/`DataType` decoding documented in [`../PortApps/Customer_Utilities-Decoder.md`](../PortApps/Customer_Utilities-Decoder.md)) now happens **after** Event Hubs, in Databricks, landing in Delta + Lakebase (Postgres).

---

## 2. What it does (and deliberately does NOT do)

**Does:**
- Binds **N TCP servers** (one per configured port) concurrently in a single asyncio loop.
- Per connection: enforces a **per-IP concurrency cap**, reads packets up to the `*` terminator, validates the **5-digit checksum**, computes a deterministic `msg_key = sha1(raw)`, **publishes raw bytes** to the matching Event Hubs topic with headers, and replies with an **ACK** (`005A`) on success.
- Exposes an **HTTP server** (`:8080`) with `/health`, `/ready`, `/metrics` (Prometheus).
- Handles **SIGTERM/SIGINT** for graceful drain + Kafka flush.

**Does NOT:**
- Parse/decode the payload (no catalog lookup, no float conversion).
- Touch SQL Server.
- Send an explicit NACK on failure — **failures are silent** so the meter times out and retransmits (preserves at-least-once).

---

## 3. Folder inventory

```
pt-tcp-listener/
├── README.md                       full operator-facing documentation
├── pyproject.toml                  package metadata, deps, tooling (pytest/ruff/mypy)
├── requirements.txt                pinned runtime deps for Docker
├── Dockerfile                      multi-stage, non-root container build
├── Makefile                        dev tasks (install/test/lint/run/docker)
├── .dockerignore / .gitignore      build & VCS hygiene (secrets excluded)
├── .env.example                    local-dev config template
│
├── src/tcp_listener/               THE SERVICE
│   ├── __init__.py                 version marker (1.0.0)
│   ├── __main__.py                 `python -m tcp_listener` entrypoint
│   ├── main.py                     asyncio TCP+HTTP servers, connection handling, shutdown
│   ├── settings.py                 pydantic env-var config + multi-tenant routing
│   ├── checksum.py                 port of legacy CheckSum.dll
│   ├── publisher.py                Event Hubs (Kafka) producer wrapper
│   ├── metrics.py                  thread-safe Prometheus counters/gauges
│   ├── http_server.py              /health · /ready · /metrics (stdlib only)
│   └── logging_config.py           structured JSON logging
│
├── tests/                          ~62 unit/integration tests (no network needed)
│   ├── conftest.py                 env isolation fixture
│   ├── test_checksum.py            checksum correctness + real McDonald's packet
│   ├── test_settings.py            port/topic parsing, prefixing, SAS lookup
│   ├── test_publisher.py           producer behaviour (Kafka mocked)
│   ├── test_metrics.py             counter/gauge + Prometheus rendering
│   └── test_http_server.py         live loopback HTTP probes
│
├── scripts/
│   ├── send_test_packet.py         craft+send a checksummed packet to the listener
│   └── consume_messages.py         read back from Event Hubs to verify
│
└── infra/
    ├── deploy.sh                   ACR build + Container App update (per customer)
    └── customers/
        ├── README.md               onboarding & topic-naming convention
        ├── mcdonalds-dev.env       McDonald's DEV config
        └── pharma-dev.env          Pharma (Lambda/Cipla) DEV config
```

---

## 4. Architecture & runtime model

- **Single process, single asyncio event loop.** One `python -m tcp_listener` process binds every TCP port in `PORT_TOPIC_MAP` plus the HTTP port. No threads for connection handling (asyncio coroutines), but **one daemon thread per Kafka producer** drives librdkafka delivery callbacks.
- **Stateless & horizontally scalable.** No local persistence; all state is in Event Hubs. Multiple replicas can run behind the same ports.
- **Config-driven multi-tenancy.** The exact same image runs for every customer; only environment variables differ.
- **Backpressure via meter retransmit.** If Event Hubs is slow/unreachable, the publish fails, no ACK is sent, and the meter retransmits later (the legacy contract). A large in-producer buffer (1M messages ≈ 13 min at 1,250 msg/s) absorbs short outages.

---

## 5. The packet protocol & checksum

Packets are the same legacy `$ … *` frames the PortApps system uses (see [`../PortApps/Customer_Utilities-Decoder.md`](../PortApps/Customer_Utilities-Decoder.md) for full payload decoding). This service only cares about the **frame envelope + checksum**, not the payload.

**Checksum algorithm** (`checksum.py`, a port of `CheckSum.dll`):
- Packet must start with `$` and end with `*`.
- The **5 decimal digits immediately before `*`** are the declared checksum.
- Validity: `sum(bytes between '$' and the checksum digits) % 100000 == declared`.
- The leading `$` is **excluded** from the sum.

```
$  <body bytes>  <5-digit checksum>  *
└┬┘ └────┬────┘  └───────┬────────┘ └┬┘
 not    summed        = sum(body)    terminator
 summed               % 100000
```

Example: `compute_checksum(b"hello") = 532` → `append_checksum(b"hello") = b"$hello00532*"`.
The canonical regression test uses a **real McDonald's packet** lifted from the legacy `ClientProcess.exe.config`:
`$00612100DMcDonalds12025000210DX02025805/03/202611:04:03+026.8…06319*`.

> **Note:** this is a simple additive checksum (sum mod 100000). It is intentionally byte-for-byte compatible with the legacy `.NET`/VB checksum so existing meters need no change.

---

## 6. End-to-end data flow

```
                 Meter opens TCP to a plant port (e.g. 30009)
                              │
                              ▼
   handle_connection()  ── PerIPConcurrencyLimiter.try_acquire(ip)
                              │   (reject + count if > MAX_CONNECTIONS_PER_IP)
                              ▼
        loop while not EOF (PERSISTENT_CONNECTIONS):
           readuntil(b"*")  with READ_TIMEOUT_SECONDS
                              │
                              ▼
        _process_one_packet():
           ├─ size > MAX_PACKET_BYTES?  → count tcp_nack_size_total, SILENT return
           ├─ checksum invalid?          → count tcp_nack_checksum_total, SILENT return
           ├─ publisher.publish(topic, raw, peer_ip)
           │     ├─ key = sha1(raw)
           │     ├─ headers: source_ip, customer_id, ingest_ts, schema_version=1
           │     ├─ produce() → Event Hubs (Kafka, acks=all)
           │     └─ await delivery (timeout EH_PUBLISH_TIMEOUT_SECONDS)
           │          └─ fail/timeout → count eh_publish_*; SILENT return (no ACK)
           └─ success → writer.write(ACK="005A"); count tcp_packets_acked_total
                              │
                              ▼
              Event Hubs topic (e.g. eh-mcd-raw-lv)
                              │
                              ▼
                 Databricks → decode → Delta + Lakebase
```

The HTTP server (`:8080`) runs alongside the whole time for liveness/readiness/metrics. On `SIGTERM`, the servers stop accepting, in-flight handlers drain, producers flush, then the process exits.

---

## 7. File-by-file analysis

### 7.1 Source — `src/tcp_listener/`

#### `__init__.py`
Package marker. Defines `__version__ = "1.0.0"`.

#### `__main__.py`
Enables `python -m tcp_listener`. Imports `run` from `main` and calls it under `if __name__ == "__main__"`.

#### `main.py` — the orchestrator
- **`PerIPConcurrencyLimiter`** — async, lock-guarded `dict[ip,count]`. `try_acquire` returns False once an IP hits `MAX_CONNECTIONS_PER_IP`; `release` decrements and prunes zero entries. Defence-in-depth on top of NSG.
- **`_process_one_packet()`** — the per-packet pipeline: count received → size guard → checksum guard → publish → on success write `ack_bytes` and count acked. **All failure paths are silent** (logged + counted, but no bytes returned) so the meter retransmits.
- **`handle_connection()`** — per-connection coroutine. Acquires the per-IP slot, increments the `tcp_active_connections` gauge, then loops `readuntil(b"*")` with a read timeout. Carefully handles `TimeoutError`, `IncompleteReadError`, `LimitOverrunError` (no terminator within the 64 KB StreamReader buffer), and `ConnectionReset/Aborted/BrokenPipe` — each with its own counter. After each packet it bounds `writer.drain()` to 5 s. Honours `PERSISTENT_CONNECTIONS` (loop vs. one-shot). `finally` closes the writer and releases the IP slot + gauge.
- **`serve()`** — starts one `asyncio.start_server` per port (binds `0.0.0.0`), starts the HTTP server, marks readiness, installs SIGTERM/SIGINT handlers (guarded for Windows where `add_signal_handler` raises `NotImplementedError`), then `serve_forever` until the stop future resolves, then closes servers and flushes the publisher.
- **`main()` / `run()`** — sets up logging, loads `PORT_TO_TOPIC` from settings, constructs the `EventHubPublisher`, and runs `serve`. `run()` is the sync entrypoint (`asyncio.run`).

#### `settings.py` — typed config & multi-tenant routing
- **`Settings(BaseSettings)`** (pydantic-settings) reads env (and `.env`). Fields: `eh_bootstrap`, `eh_publish_timeout_seconds`, `customer_id`, `port_topic_map`, `topic_prefix`, `read_timeout_seconds`, `max_packet_bytes`, `max_connections_per_ip`, `persistent_connections`, `ack_bytes` (default **`005A`**), `http_port`, `log_level`, `log_raw_on_nack`.
- **`get_port_to_topic()`** — parses `"port:topic,..."` into `{int: topic}`, validating: missing colon, non-integer port, port range 1–65535, empty topic, duplicate port, empty map. Applies `_apply_prefix()`.
- **`_apply_prefix()`** — prepends `TOPIC_PREFIX-`, stripping a trailing dash and avoiding double-prefixing.
- **`get_topic_sas_credentials()`** — for each unique effective topic, reads `EH_SAS_<TOPIC>` (uppercase, `-`→`_`); raises listing all missing vars.
- **`_LazySettings` / `settings`** — a lazy singleton proxy so importing the module doesn't force env validation (keeps tests importable without env).

#### `checksum.py` — legacy checksum port
`compute_checksum` (sum % 100000), `append_checksum` (`$`+body+5-digit+`*`), `is_valid` (frame markers + min length + numeric digits + sum match). Pure, dependency-free, fully unit-tested.

#### `publisher.py` — Event Hubs (Kafka) producer
- **One `confluent_kafka.Producer` per topic**, each with its own SAS password. Producer config is tuned specifically for **Azure Event Hubs' Kafka surface**:
  - `security.protocol=SASL_SSL`, `sasl.mechanism=PLAIN`, `sasl.username=$ConnectionString`, `sasl.password=<SAS>`.
  - `compression.type=none` (EH rejects some compressed batches), `acks=all`.
  - `api.version.request=False` + `broker.version.fallback=0.10.0.0` (EH only reliably supports ≤ v0.10 protocol; otherwise `UNSUPPORTED_FOR_MESSAGE_FORMAT`).
  - `enable.idempotence=False` (unsupported by EH).
  - Large buffer (`queue.buffering.max.messages=1_000_000`, ~2 GB kbytes), retries (10, 200 ms backoff), `delivery.timeout.ms=60_000`, aggressive reconnect/metadata refresh.
- **One daemon poll thread per producer** (`_poll_loop`, 100 ms blocking poll) so delivery callbacks fire promptly without blocking the event loop.
- **`publish()`** — builds `key=sha1(raw)` and headers (`source_ip`, `customer_id`, `ingest_ts`, `schema_version=1`); creates an asyncio future resolved from the librdkafka delivery callback (`call_soon_threadsafe`, guarded against a closing loop). Handles `BufferError` (local queue full) with exponential backoff (5 attempts: 100/200/400/800 ms); enforces the per-message timeout via `wait_for`. Raises `PublishError` on failure/timeout.
- **`flush()` / `close()`** — drain pending messages (logs leftovers), stop poll threads.

#### `metrics.py` — Prometheus registry
Thread-safe `Counters` (lock-guarded `defaultdict`s for counters + gauges). `inc`, `gauge_inc/dec`, `snapshot` (tests), `render_prometheus` (0.0.4 text with `# HELP`/`# TYPE`), `reset`. Labels are normalised to a sorted tuple so label order doesn't fragment series. A module-level `counters` singleton is shared everywhere (incl. the Kafka callback thread).

#### `http_server.py` — minimal stdlib HTTP
No framework. `_ReadinessState` (`readiness` singleton) flips to ready once TCP is bound and never flips back. Routes: `/health`+`/healthz` (always 200), `/ready`+`/readyz` (503 → 200), `/metrics` (Prometheus body). `_handle` parses the request line, discards headers, returns 405 for non-GET and 404 for unknown paths; bad clients are handled silently. `start_http_server` returns the server for shutdown management.

#### `logging_config.py` — structured JSON logs
`JsonFormatter` emits one JSON object per line (`ts`, `level`, `logger`, `msg`, optional `exc`, plus any `extra={…}` fields), ready for Azure Monitor / Log Analytics. `setup_logging` installs it on the root logger and quiets `asyncio` to WARNING.

### 7.2 Tests — `tests/`
~62 fast tests, no network (Kafka mocked, HTTP on loopback).
- **`conftest.py`** — autouse fixture that strips all relevant env vars and resets the settings singleton before/after each test, so config tests are hermetic.
- **`test_checksum.py`** — `compute/append/is_valid` correctness, modulus wraparound, zero-padding, frame-marker and length guards, non-numeric checksum, and the **real McDonald's packet** regression + truncation/corruption cases.
- **`test_settings.py`** — McDonald's vs. Pharma topologies, whitespace tolerance, all validation errors (empty/duplicate/invalid/range/missing-colon/empty-topic), prefixing (apply/avoid-double/strip-trailing-dash/multi-word env), and SAS lookup (per-unique-topic, missing-raises, numeric-suffix topics).
- **`test_publisher.py`** — one producer per topic, deterministic `sha1` key, expected headers, same/different payload key behaviour, delivery-failure → `PublishError`, unknown topic → `KeyError`, flush/close fan-out. Uses a `MagicMock` Producer.
- **`test_metrics.py`** — increment, label distinctness, label-order stability, `inc by=n`, gauge inc/dec, reset, and Prometheus rendering (counter/gauge `# TYPE`, labelled series).
- **`test_http_server.py`** — live loopback server: `/health` 200, `/ready` 503-before/200-after, `/metrics` Prometheus body, 404 unknown, 405 non-GET.

### 7.3 Scripts — `scripts/`
- **`send_test_packet.py`** — builds `append_checksum(SAMPLE_BODY)` (a realistic HVAC frame), connects to `--host:--port`, sends, prints the response and round-trip ms. Supports `--count`, `--interval`, and `--corrupt` (flip a checksum digit to force a silent drop). `--port` is restricted to `[31002, 30009, 16002]`.
- **`consume_messages.py`** — a Kafka `Consumer` smoke test that reads back up to `--max` messages from a topic, printing key/headers/value preview. Derives the SAS env var from the topic and needs `EH_BOOTSTRAP` + that SAS.

### 7.4 Infra — `infra/`
- **`deploy.sh`** — `./infra/deploy.sh <tag> <customer.env>`. Requires `ACR`/`RG`/`APP`. Builds the image **inside ACR** (`az acr build`, no local Docker), reads non-comment lines from the customer env file into `--set-env-vars`, updates the Container App image+env, prints the latest revision. Note the comment: `EH_SAS_*` values are usually blank in the file and resolved from **Key Vault references** on the Container App.
- **`customers/README.md`** — the onboarding contract: topic naming `<PREFIX>-<logical>` (`raw-sd`/`raw-lv`/`raw-control`), the `EH_SAS_<EFFECTIVE_TOPIC>` rule, why prefixing (tenant defence-in-depth, future consolidation, wildcard consumers), and step-by-step new-customer onboarding (e.g. "burgerking").
- **`customers/mcdonalds-dev.env`** — `CUSTOMER_ID=mcd`, `TOPIC_PREFIX=eh-mcd`, `PORT_TOPIC_MAP=31002:raw-sd,31009:raw-sd,30009:raw-lv`, EH namespace `ehns-decoding-mcd-dev`, `EH_SAS_EH_MCD_RAW_SD/LV=secretref:…`, `MAX_CONNECTIONS_PER_IP=200`, `ACK_BYTES=005A`. Comments map each port to its legacy stored proc and note McDonald's has **no control port**.
- **`customers/pharma-dev.env`** — `CUSTOMER_ID=pharma`, `TOPIC_PREFIX=pharma`, `PORT_TOPIC_MAP=31002:raw-sd,30009:raw-lv,16002:raw-control` (the **3rd, control topic**), `MAX_CONNECTIONS_PER_IP=16`. Comments reference the legacy "Pharma (Lambda/Cipla)" control proc `USP_MSControlStatus_Params`.

### 7.5 Build & project files
- **`Dockerfile`** — two stages. Builder (`python:3.12-slim` + `gcc/g++/librdkafka-dev`) pre-builds wheels from `requirements.txt`. Runtime installs only `librdkafka1`, creates a non-root `app` user (uid/gid 10001), installs the wheels, copies `src`, sets `PYTHONPATH=/app/src`, `EXPOSE 31002 30009 16002 8080`, runs as `app`, `CMD python -m tcp_listener`.
- **`Makefile`** — `install` (venv + editable `[dev]`), `test` (pytest -v), `lint`/`format` (ruff), `run`, `docker-build`, `docker-run`, `clean`.
- **`pyproject.toml`** — package `tcp-listener` 1.0.0, `requires-python >=3.12`, runtime deps (`confluent-kafka`, `pydantic`, `pydantic-settings`), dev deps (pytest/-asyncio/-cov, ruff, mypy), console script `tcp-listener`, setuptools src layout, pytest `asyncio_mode=auto`, ruff (line 100, rules `E,F,I,B,UP,N,RUF`), mypy `strict`.
- **`requirements.txt`** — pinned runtime: `confluent-kafka==2.6.0`, `pydantic==2.6.4`, `pydantic-settings==2.2.1`.
- **`.env.example`** — annotated local-dev template (McDonald's example).
- **`.dockerignore`** — keeps tests/scripts/infra/docs/markdown/secrets out of the image (ships only `src`).
- **`.gitignore`** — standard Python ignores plus **`*.local.env` / `*.local`** (local files with hardcoded secrets) and `.env*` (except `.env.example`).

---

## 8. Multi-tenant configuration model

One image, per-customer env file. The chain is:

```
PORT_TOPIC_MAP   "31002:raw-sd,31009:raw-sd,30009:raw-lv"   (logical topics)
        + TOPIC_PREFIX  "eh-mcd"
        ▼
effective topics   eh-mcd-raw-sd , eh-mcd-raw-lv            (what exists in Event Hubs)
        ▼
SAS env var rule   uppercase + '-'→'_'
        ▼
EH_SAS_EH_MCD_RAW_SD , EH_SAS_EH_MCD_RAW_LV                 (Key Vault → Container App secret)
```

| Customer | Ports → logical topic | Effective topics | Notes |
|----------|------------------------|------------------|-------|
| **McDonald's** (`mcd`) | 31002→raw-sd, 31009→raw-sd, 30009→raw-lv | `eh-mcd-raw-sd`, `eh-mcd-raw-lv` | 3 ports, 2 topics (31002+31009 share SD); no control port; cap 200/IP |
| **Pharma** (`pharma`) | 31002→raw-sd, 30009→raw-lv, 16002→raw-control | `pharma-raw-sd`, `pharma-raw-lv`, `pharma-raw-control` | adds a **control** topic; cap 16/IP |

Onboarding a new customer = copy an env file, edit 5 values, have the platform team provision EH topics + SAS + Key Vault, deploy. **No code change, no new image.**

---

## 9. Configuration reference (env vars)

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `CUSTOMER_ID` | ✅ | – | Tenant tag on every message header |
| `PORT_TOPIC_MAP` | ✅ | – | `port:topic` pairs; many ports may share a topic |
| `EH_BOOTSTRAP` | ✅ | – | Event Hubs Kafka endpoint `…servicebus.windows.net:9093` |
| `EH_SAS_<TOPIC>` | ✅ (per unique effective topic) | – | SAS connection string; name = uppercase topic, `-`→`_` |
| `TOPIC_PREFIX` | ➖ | `""` | Prepended to each topic (`-` joined); double-prefix-safe |
| `EH_PUBLISH_TIMEOUT_SECONDS` | ➖ | `10.0` | Per-message broker-ack wait |
| `ACK_BYTES` | ➖ | `005A` | Bytes returned to the meter on success |
| `PERSISTENT_CONNECTIONS` | ➖ | `true` | Many packets per connection vs. one-shot |
| `MAX_CONNECTIONS_PER_IP` | ➖ | `16` | Per-source-IP concurrency cap |
| `READ_TIMEOUT_SECONDS` | ➖ | `5.0` | Max wait for the `*` terminator |
| `MAX_PACKET_BYTES` | ➖ | `4096` | Oversize guard |
| `HTTP_PORT` | ➖ | `8080` | health/ready/metrics |
| `LOG_LEVEL` | ➖ | `INFO` | log verbosity |
| `LOG_RAW_ON_NACK` | ➖ | `false` | log raw hex on checksum failure |

---

## 10. Observability (metrics, health, logs)

**HTTP (`:8080`)** — `/health` (always 200), `/ready` (503 until TCP bound), `/metrics` (Prometheus 0.0.4).

**Metrics** (labels: `port` for TCP, `topic` for EH):

| Metric | Type | Fires when |
|--------|------|-----------|
| `tcp_packets_received_total` | counter | packet read |
| `tcp_packets_acked_total` | counter | ACK sent |
| `tcp_nack_checksum_total` | counter | checksum failed |
| `tcp_nack_size_total` | counter | over `MAX_PACKET_BYTES` |
| `tcp_read_timeout_total` | counter | terminator wait timed out |
| `tcp_incomplete_read_total` | counter | peer closed before `*` |
| `tcp_oversized_read_total` | counter | no terminator within 64 KB buffer |
| `tcp_peer_reset_total` | counter | connection reset/aborted by peer |
| `tcp_drain_failed_total` | counter | ACK drain failed |
| `tcp_connection_rejected_total` | counter | per-IP cap exceeded |
| `tcp_handler_error_total` | counter | unexpected handler exception |
| `tcp_active_connections` | gauge | live connections |
| `eh_publish_total` | counter | broker acked |
| `eh_publish_failure_total` | counter | broker error |
| `eh_publish_timeout_total` | counter | publish exceeded timeout |
| `eh_publish_queue_pressure_total` | counter | local queue full (retried) |
| `eh_publish_queue_full_total` | counter | queue still full after retries (dropped) |

**Logs** — single-line JSON on stdout with structured `extra` fields (port, peer, bytes, topic, …).

---

## 11. Reliability & delivery semantics

- **At-least-once.** EH is treated as a replayable log; no exactly-once at the producer.
- **Idempotent dedup downstream.** `msg_key = sha1(raw)` lets Delta `MERGE` / Postgres `ON CONFLICT` dedup retransmits and producer retries.
- **Silent-failure contract.** Oversize/checksum/publish failures return **no ACK** → the meter retransmits. This is the legacy meter behaviour, preserved deliberately.
- **Graceful shutdown.** SIGTERM → stop accepting → drain handlers → flush producers → exit (Container Apps gives ~30 s).
- **Buffered outage tolerance.** ~1M-message in-producer buffer rides out brief EH degradation / throughput-unit auto-inflate.

---

## 12. Dependencies

Runtime (3): **`confluent-kafka` 2.6** (librdkafka Kafka client for EH), **`pydantic` 2.6** + **`pydantic-settings` 2.2** (typed env config). Dev: pytest (+asyncio, +cov), ruff, mypy. System: `librdkafka1` (runtime), `librdkafka-dev` + `gcc/g++` (build only). Notably **no web framework** — the HTTP server is hand-rolled on the stdlib.

---

## 13. Observations, discrepancies & risks

| # | Severity | Finding |
|---|----------|---------|
| 1 | 🟠 Doc/code mismatch | The README "How it works" says the listener replies `NACK_CHECKSUM` / `NACK_SIZE`. **The code never sends a NACK** — failures are silent (only metrics named `tcp_nack_*` are incremented). The `tcp_nack_*` metric names are also slightly misleading since no NACK byte is transmitted. |
| 2 | 🟡 Minor | **`scripts/` are stale vs. the topic refactor.** `send_test_packet.py` hardcodes `--port` choices `[31002,30009,16002]`; `consume_messages.py` restricts `--topic` to `raw-31002/30009/16002` and derives the SAS var as `EH_SAS_<port>` — inconsistent with the current `raw-sd/raw-lv/raw-control` + `EH_SAS_<TOPIC>` convention in `settings.py`. They'd need updating to consume the real effective topics. |
| 3 | 🟡 Minor | **README metrics table is a subset** — it omits `tcp_oversized_read_total`, `tcp_peer_reset_total`, `tcp_drain_failed_total`, `eh_publish_queue_pressure_total`, `eh_publish_queue_full_total` which the code actually emits. |
| 4 | 🟢 Info | **Prefix differs per customer:** McDonald's uses `TOPIC_PREFIX=eh-mcd` (hubs are named `eh-mcd-…`), while docs elsewhere use `mcd-…`. It's internally consistent (the env file explains the platform-team `eh-` hub-naming), just easy to trip over when writing `EH_SAS_*` names. |
| 5 | 🟢 Info | **Windows note:** `add_signal_handler` is unsupported on Windows; the code guards it, so SIGTERM-based graceful shutdown only applies on Linux/containers (which is where it runs). |
| 6 | 🟢 Good | Solid security posture: non-root container, secrets via Key Vault/`secretref` (never in the image or git), `.gitignore` excludes `*.local.env`, SAS per-topic (least privilege), per-IP cap on top of NSG. |
| 7 | 🟢 Good | Genuinely customer-agnostic: every tenant-specific value is config; the 62 hermetic tests cover the tricky parsing/prefix/SAS edge cases. |

**Status (from README):** code, tests, Dockerfile, deploy script, probes/metrics, multi-tenancy = ✅ ready. Pending: Azure infra (Event Hubs, Container App), plant network access (ExpressRoute/VPN), load test vs. real EH, Azure Monitor alert rules in Bicep, runbooks.

---

## 14. Quick reference tables

### Ports (per customer)

| Port | McDonald's | Pharma | Legacy equivalent |
|------|-----------|--------|-------------------|
| 31002 | raw-sd | raw-sd | `DP-31002` (USP_Raw_To_SDTable_Port_31002_Data) |
| 31009 | raw-sd | — | `DP-31009` |
| 30009 | raw-lv | raw-lv | `LP-30009` (USP_Raw_To_LVTable_Port_30009_Live) |
| 16002 | — | raw-control | control app (USP_MSControlStatus_Params) |
| 8080 | HTTP health/ready/metrics | same | — |

### Logical topics

| Logical | Carries |
|---------|---------|
| `raw-sd` | Summary Data (historical readings) |
| `raw-lv` | Live readings + alert events |
| `raw-control` | Control-port queries (some customers) |

### Message headers (every published message)

| Header | Value |
|--------|-------|
| `source_ip` | meter's IP |
| `customer_id` | `CUSTOMER_ID` |
| `ingest_ts` | publish epoch seconds |
| `schema_version` | `1` |
| key | `sha1(raw)` (hex) |

---

*Generated from a full read of every file in `data/pt-tcp-listener/`. Unlike the compiled `PortApps` analysis, this project ships source, so behaviour is described directly from the code. See the companion docs [PortApps-Analysis.md](../PortApps/PortApps-Analysis.md) and [Customer_Utilities-Decoder.md](../PortApps/Customer_Utilities-Decoder.md) for the legacy system this service replaces and the downstream decoding catalog.*
