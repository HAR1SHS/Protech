# PortApps — Complete Technical Analysis & Reference

> **Location:** `data/PortApps/`
> **System:** Building Management System (BMS) telemetry platform by **Protech**
> **Customer:** **McDonald's** (SQL database `Mcdonalds1_AD`)
> **Purpose:** Ingest sensor/meter readings from field devices over raw TCP, validate them, and persist them into SQL Server; control HVAC switches; visualize everything on a live dashboard.

---

## Table of Contents

1. [What PortApps Is (Big Picture)](#1-what-portapps-is-big-picture)
2. [Two Generations of Software](#2-two-generations-of-software)
3. [Folder Inventory](#3-folder-inventory)
4. [The Data Protocol (Packet Format)](#4-the-data-protocol-packet-format)
   - **Decoder catalog (`Customer_utilities.csv`)** → see companion doc [Customer_Utilities-Decoder.md](Customer_Utilities-Decoder.md)
5. [Legacy Apps — DP / LP Port Processors](#5-legacy-apps--dp--lp-port-processors)
6. [BmsSmart-DataGateway — Main Production Service](#6-bmssmart-datagateway--main-production-service)
7. [BmsSmart-CtrlGateway — HVAC Control Service](#7-bmssmart-ctrlgateway--hvac-control-service)
8. [BmsSmart.Shared — Common Library](#8-bmssmartshared--common-library)
9. [ClientProcess — Test Client](#9-clientprocess--test-client)
10. [Shared Libraries (Legacy) — SharedLib & CheckSum](#10-shared-libraries-legacy--sharedlib--checksum)
11. [Dependencies](#11-dependencies)
12. [Configuration & Security](#12-configuration--security)
13. [End-to-End Data Flow](#13-end-to-end-data-flow)
14. [Observations, Risks & Recommendations](#14-observations-risks--recommendations)
15. [Quick Reference Tables](#15-quick-reference-tables)

---

## 1. What PortApps Is (Big Picture)

`data/PortApps` is the **deployment / runtime folder** of a BMS telemetry platform. Field devices (meters, temperature probes, pH/Lambda sensors) installed in McDonald's stores send ASCII data frames over **raw TCP sockets** to this server. The applications here:

1. **Listen** on a range of TCP ports.
2. **Receive & parse** the `$…*` data frames.
3. **Validate** them with a checksum.
4. **Resolve** the site/customer from a cache.
5. **Write** the readings into SQL Server (via stored procedures in the legacy apps, via staging tables + bulk copy in the new apps).
6. **Acknowledge** the device, **control HVAC** equipment, and **surface health/anomalies** on a live dashboard.

---

## 2. Two Generations of Software

The folder contains **two distinct generations** of the same platform, deployed side-by-side. The new `BmsSmart` gateways are the **replacement** that consolidates the many single-port legacy apps into two multi-port Windows Services.

| Gen | Apps | Framework | Build Solution (from PDB paths) | Role |
|-----|------|-----------|----------------------------------|------|
| **Legacy** | `DP-31002`, `DP-31009`, `LP-30009` | .NET 6.0 | `G:\PharmaCustomers\Apps\PortsAppsVer11` | One **process per port** |
| **New** | `BmsSmart-DataGateway`, `BmsSmart-CtrlGateway` | .NET 8.0 | `E:\ProtechBMS25` | One **service for all ports** |
| **Test tool** | `ClientProcess` | .NET Framework 4.8 | — | TCP packet **simulator** |

- Legacy = "**PortsApps Version 11**" — naming convention `DP-####` / `LP-####` where the number is the TCP port.
  - `DP` = **Data Port** (writes to **SD** = Sensor Data tables).
  - `LP` = **Live Port** (writes to **LV** = Live tables).
- New = "**ProtechBMS25**" (2025 rewrite) — `BmsSmart.*` namespace, also shares a `BuildSmart.Api` project (not present in this folder).

---

## 3. Folder Inventory

```
data/PortApps/
├── DP-31002/                   Legacy single-port processor  (TCP 31002 → SD table)
├── DP-31009/                   Legacy single-port processor  (TCP 31009 → SD table)
├── LP-30009/                   Legacy single-port processor  (TCP 30009 → LV/Live table)
├── BmsSmart-DataGateway/       NEW multi-port sensor gateway (TCP 31001–31009)
├── BmsSmart-CtrlGateway/       NEW HVAC control gateway      (TCP 16002, 16005)
├── ClientProcess/              TCP test client / packet replayer
│
├── BmsSmart-DataGateway.zip    (~22 MB) packaged deployment archive / backup of the DataGateway build
├── Customer_utilities.csv      (~42 MB) decoder catalog — 81,972 rows (see Customer_Utilities-Decoder.md)
├── Customer_Utilities-Decoder.md   companion doc: how raw frames are decoded
└── PortApps-Analysis.md        this document
   (PortApps/New folder/ — the empty leftover noted in earlier revisions no longer exists here)
```

> **`.pdb` debug symbols are present in every app folder** (`DP-31002.pdb`, `SharedLib.pdb`,
> `BmsSmart.DataGateway.pdb`, `BmsSmart.Shared.pdb`, `ClientProcess.pdb`, etc.). They were shipped
> alongside the release binaries. They are how the build-machine paths
> (`G:\PharmaCustomers\Apps\PortsAppsVer11`, `E:\ProtechBMS25`) and many internal type/method names
> in this analysis were recovered — and, by the same token, they let anyone fully reverse-engineer
> the apps. See observation #7.

> **Unrelated sibling:** there is a `data/New folder/` *next to* `PortApps/` (not inside it) that
> contains **win-acme** — a Let's Encrypt/ACME TLS-certificate client — which has **nothing to do
> with the BMS system**. It is documented separately in
> [../New folder/README-win-acme.md](../New%20folder/README-win-acme.md).

> **Note on file counts:** Each app folder contains many `System.*` / `Microsoft.*` DLLs, a `runtimes/` tree (win-x64/x86/arm64, unix), and localization sub-folders (`cs/`, `de/`, `es/`, `fr/`, `it/`, `ja/`, `ko/`, `pl/`, `pt-BR/`, `ru/`, `tr/`, `zh-Hans/`, `zh-Hant/`). **These are third-party framework dependencies shipped by a self-contained .NET publish — not application code.** The files that carry the actual logic per app are only: the `.exe` (launcher/apphost), the same-named `.dll` (the real managed code), the `*.deps.json`, the `*.runtimeconfig.json`, and the config file.

### Per-app "real" files

| App | Launcher | Code DLL | Config | App-specific helper DLLs |
|-----|----------|----------|--------|--------------------------|
| DP-31002 | `DP-31002.exe` | `DP-31002.dll` (14 KB) | `DP-31002.dll.config` | `SharedLib.dll`, `CheckSum.dll` |
| DP-31009 | `DP-31009.exe` | `DP-31009.dll` | `DP-31009.dll.config` | `SharedLib.dll`, `CheckSum.dll` |
| LP-30009 | `LP-30009.exe` | `LP-30009.dll` | `LP-30009.dll.config` | `SharedLib.dll`, `CheckSum.dll` |
| BmsSmart-DataGateway | `BmsSmart.DataGateway.exe` | `BmsSmart.DataGateway.dll` (1 MB) | `appsettings.enc` (encrypted) | `BmsSmart.Shared.dll` |
| BmsSmart-CtrlGateway | `BmsSmart.CtrlGateway.exe` | `BmsSmart.CtrlGateway.dll` (94 KB) | `appsettings.enc` (encrypted) | `BmsSmart.Shared.dll` |
| ClientProcess | `ClientProcess.exe` (6.6 KB) | (in exe) | `ClientProcess.exe.config` | — (ships `.pdb`) |

---

## 4. The Data Protocol (Packet Format)

Field devices send ASCII frames delimited by `$ … *`. Real examples (from configs/logs):

```
$00612100DMcDonalds12025000210DX02025805/03/202611:04:03+026.81000001156940000003776-0000+031.3+028.0+XXXX10000124706319*
$0060590GCLambdaph122025000025XXXXXXXX27/07/207217:38:0703493*
```

### Frame structure (decoded from `SharedLib.HeaderObj` fields)

| Segment | Example | Meaning |
|---------|---------|---------|
| `$` | `$` | Start delimiter |
| Length / Protocol | `006`, `121` | Frame length + **ProtocolID** |
| **DataID** | `00D` | Message type. `00D` = **sensor data** (every log line shows `DataId='00D'`) |
| **CustomerID** | `McDonalds1` | Customer code |
| **CommunicationId / Site** | `2025000210` | Store / site / gateway ID |
| **MeterType** | `DX02` | Device/meter type code |
| **MeterSerial** | `0258` | Meter serial |
| **TxnDate** | `05/03/2026` | Device-reported date |
| **TxnTime** | `11:04:03` | Device-reported time |
| **Readings** | `+026.8 … +031.3 +028.0` | One or more sensor values (temperatures, pH/Lambda, etc.) |
| **Checksum** | `…319` | Validation digits before `*` |
| `*` | `*` | End delimiter |

`HeaderObj` (in `SharedLib` / `BmsSmart`) carries these parsed fields:
`DataID, ProtocolID, CustomerID, CommunicationId, AckCommand, SiteName, TxnTime, TxnDate, ServerTime, MeterType, MeterSerial, TotalString, TotalBytes, IpPort`.

> **The payload is positional (no separators).** The header is ≈ the first 56 chars; after it, each meter "line" is a fixed-width field. **How to slice and decode every field is defined by `Customer_utilities.csv`** — fully documented in the companion file [Customer_Utilities-Decoder.md](Customer_Utilities-Decoder.md). In short: each catalog row gives a `Byteposition`, `TotalBytes`, `DataType` (`HEX` = IEEE-754 big-endian float / `ASC` = ASCII number / `TXT` = text) and a `Multiplier`, so `value = decode(frame[pos : pos+len]) × Multiplier`.

---

## 5. Legacy Apps — DP / LP Port Processors

`DP-31002`, `DP-31009`, and `LP-30009` are **the same compiled program with different config**. Each is a standalone console app that owns **one TCP port**.

### 5.1 Configuration

`DP-31002/DP-31002.dll.config` (`appSettings` keys):

| Key | Value | Purpose |
|-----|-------|---------|
| `ShowRaw` | `0` | Echo raw frames to console (debug) |
| `IpAddress` | `10.0.0.4` | Bind/host address |
| `IpPort` | `31002` | TCP port to listen on |
| `CachePolicyTime` | `24` | Site-name cache lifetime (hours) |
| `DBConnectionString` | `Server=MsSQLServerDev;Database=Mcdonalds1_AD;user id=admin_sarral;password=LoopDown@002;…` | SQL connection (**plaintext**) |
| `PortSPName` | `[Mcdonalds1_AD].[PortProcess].[USP_Raw_To_SDTable_Port_31002_Data]` | Stored proc to persist the row |
| `ExceptionSPName` | `[Mcdonalds1_AD].[PortProcess].[USP_Update_Exceptions]` | Stored proc for errors |

**Differences between the three:**

| App | `IpPort` | `PortSPName` (stored proc) | Target table |
|-----|----------|----------------------------|--------------|
| DP-31002 | 31002 | `USP_Raw_To_SDTable_Port_31002_Data` | **SD** (Sensor Data) |
| DP-31009 | 31009 | `USP_Raw_To_SDTable_Port_31002_Data` ⚠️ *(points at 31002 — likely a copy-paste bug)* | SD |
| LP-30009 | 30009 | `USP_Raw_To_LVTable_Port_30009_Live` | **LV** (Live) |

All share `IpAddress=10.0.0.4`, DB `Mcdonalds1_AD`, and `USP_Update_Exceptions`.

### 5.2 Internal types (recovered from metadata)

- `Program` — `Main`, the entry point and TCP accept loop.
- `SharedLib.HeaderObj` / `HeaderBO` — parsed frame model.
- `SharedLib.Cache` — `MemoryCache "sitesChache"` of site names, with `CacheItemPolicy` / `AbsoluteExpiration`.
- `SharedLib.Sites` — `SiteNames` loader.
- `SharedLib.DataWriter` / `DataAccess` / `StoredProc` — SQL execution.
- `SharedLib.Errors` / `AlertProcess` — `ExceptionLog`, `SendToAlertLog`, `WriteException`.
- `CheckSum.ProtechLib` (`CheckSumLib`) — checksum validation (VB.NET).
- `UpsertGatewayAndStatus` / `TouchGatewayStatus_Throttled` — gateway online-status updates (throttled).

### 5.3 Flow (per app)

```
Program.Main
  └─ Read appSettings (Ip, Port, ConnString, SP names, CachePolicyTime)
  └─ TcpListener.Start() on IpPort
  └─ Async accept loop  (BeginAcceptTcpClient / EndAcceptTcpClient)
        └─ per connection → ThreadPool.QueueUserWorkItem
              └─ ProcessIncomingConnection
                    └─ ProcessIncomingData  (read $…* frame from NetworkStream)
                          └─ ProcessRawData
                                ├─ CheckSum.ProtechLib   → validate checksum
                                ├─ HeaderObj             → parse fields
                                ├─ SharedLib.Cache       → resolve SiteName (24h cache)
                                ├─ DataWriter/StoredProc → EXEC PortSPName (insert raw row)
                                │     └─ on error → EXEC ExceptionSPName + Errors.WriteException
                                └─ UpsertGatewayAndStatus (throttled, every N min)
```

**Summary:** one process per port → accept TCP → checksum → parse → cache site → call stored procedure → update gateway status. Simple, synchronous-ish, per-row DB writes.

---

## 6. BmsSmart-DataGateway — Main Production Service

**The heart of the system.** `BmsSmart.DataGateway.dll` (~1 MB, **.NET 8**, runs as a **Windows Service**). It **replaces all the DP/LP apps** by listening on **all sensor ports 31001–31009 simultaneously**.

It is extremely active: its Serilog files reach **200 MB – 1 GB per day** (`logs/gateway-YYYYMMDD.txt`). Each received packet produces log lines like:

```
[Gateway]    Port=31007 McDonalds1/2022000039 Meter=0002/0003 23/06/2026 00:06:46 — Queued
[SensorData] RX Port=31007 DataId='00D' McDonalds1/2022000039/0002/0003 readings=2 good=2
[StagingFlush] BC McDonalds1: batch capped to 50000 rows (more pending).
```

### 6.1 Hosted services (DI-registered `BackgroundService`s)

| Service | Responsibility |
|---------|----------------|
| **`TcpGatewayService`** | Listens on every port (`ListenOnPortAsync`), accepts clients (`HandleClientAsync`), reads the frame, **sends an ACK to the device** (`TrySendAckAsync` / `ReadAckAsync`), enqueues the packet (`StopAsync` on shutdown). |
| **`PacketQueue`** | Bounded in-memory `ConcurrentQueue` (`DequeueAsync`) with `MaxQueuePerDestination` / `QueueDepthThreshold` back-pressure. |
| **`PacketProcessorService`** + **`PacketDecoder`** | Dequeue and decode packets; route to the correct handler by port. |
| **`SensorDataHandler`** | Handles `00D` sensor data — see §6.2. |
| **`SwitchControlHandler`** | Handles HVAC switch/control packets on the gateway side. |
| **`StagingFlushService`** | Periodically drains staging tables into final tables via **`SqlBulkCopy` in batches capped at 50,000 rows** (`DiscoverAllPairsAsync`, `FlushAllAsync`, `FlushSetAsync`, `FlushOnePairAsync`, `FlushBcOnePairAsync`). |
| **`MasterSyncService`** | Provisions per-customer staging databases and syncs master/catalog data (`EnsureCustomerStagingDbAsync`, `EnsureStagingDbAsync`). |
| **`GatewayHealthService`** | Writes gateway health to a monitor table. |
| **`DashboardService`** | Serves the embedded real-time HTML dashboard ("Gateway Cockpit") — see §6.3. |
| **`PortAliasService`** | Maps ports → friendly names/roles (e.g. "HVAC Primary"). |
| **`InteractivePortService`** / **`RawStringReplayService`** | Diagnostics: interactive port tools, replay raw strings, `PrintPortDiagnosticTable`, `ScrubPortFromMessage`. |

### 6.2 SensorDataHandler (the core data path)

- **Ensures storage exists:** `EnsureCustomerStagingDbAsync` → creates the per-customer staging **database / schema / table** on demand (`EnsureSchemaSql`, `EnsureTableSql`).
- **Writes readings:** `WriteSdStagingAsync` (Sensor Data) and `WriteRdStagingAsync` (Raw Data) push rows into staging using **`SqlBulkCopy`** with explicit `SqlBulkCopyColumnMapping`.
- **Caches catalog:** `_catalogCache` / `_cuCache` (customer/unit catalog) with TTL (`CatalogCacheTtl`, `InvalidateCatalogCache`).
- Logs `readings=N good=M` per packet (M = readings passing validation).

### 6.3 Embedded dashboard — "Gateway Cockpit"

A complete real-time HTML/CSS/JS UI is baked into the DLL and served by `DashboardService`. Features:

- **Tabs:** Live Data (LV, green), Sensor Data (SD, amber), **HVAC Controls** (CTRL, cyan), Flow, **AI** (neural/ML, purple), CC (customer), CMD (commands), DTS.
- **Per-port rows** with animated **split-flap displays**, status LEDs (recv / idle / down), and live ACK counts.
- **Staging-flow visualizer** showing LV / SD / CTRL lanes and flush status (flushing / stale / stopped / nodata).
- **AI/ML footer** ("neural-tag") with healthy / warning / critical states and an alerts panel.

### 6.4 Anomaly detection ("AI" layer)

Real logic backs the dashboard's AI tab:

- Per-customer thresholds reloaded on schedule: `ReloadCustomerThresholdsIfDueAsync`.
- Metrics & rules: `ZScoreThreshold`, `ErrorRateThreshold`, `QueueDepthThreshold`, `AutoLearnSilenceThreshold`, packet-size EWMA (`PacketSizeEwma`).
- **Episodes** raised on anomalies / new customers: `RaiseNewCustomerEpisodeAsync`, `AckAiEpisodeAsync` → drive dashboard alerts and the AI health state.

### 6.5 Flow (DataGateway)

```
Startup (Windows Service)
  └─ SelfEncryptingConfig: decrypt/ensure appsettings.enc
  └─ Register all hosted services via DI

TcpGatewayService
  └─ For each port 31001..31009 → ListenOnPortAsync
        └─ AcceptTcpClientAsync → HandleClientAsync
              ├─ Read $…* frame
              ├─ TrySendAckAsync  → ACK back to device
              └─ Enqueue → PacketQueue   ([Gateway] … — Queued)

PacketProcessorService
  └─ DequeueAsync → PacketDecoder
        └─ Route by port → IPortPacketHandler
              ├─ SensorDataHandler (00D)
              │     ├─ EnsureCustomerStagingDbAsync (schema/table on demand)
              │     ├─ WriteSdStagingAsync / WriteRdStagingAsync (SqlBulkCopy → staging)
              │     └─ anomaly checks → RaiseNewCustomerEpisode / thresholds
              └─ SwitchControlHandler (HVAC)

StagingFlushService (timer)
  └─ DiscoverAllPairsAsync → FlushBcOnePairAsync
        └─ SqlBulkCopy staging → FINAL tables, ≤ 50,000 rows/batch

GatewayHealthService → monitor table
DashboardService     → http dashboard (Gateway Cockpit)
```

**Why staging + bulk copy:** the packet rate is very high (logs are GB/day). Writing each packet to staging and then bulk-copying 50k-row batches into final tables is far more scalable than the legacy per-row stored-procedure inserts.

---

## 7. BmsSmart-CtrlGateway — HVAC Control Service

`BmsSmart.CtrlGateway.dll` (94 KB, **.NET 8**, Windows Service). Smaller and low-traffic (its log is only ~8 KB). It is **deliberately independent from the DataGateway** so HVAC control keeps running even if the data pipeline restarts.

**Startup banner (from log):**
```
BmsSmart CtrlGateway — HVAC Switch Service
Ports: 2 (16002 HVAC Primary, 16005 HVAC Secondary)
Config: ENCRYPTED (.enc only — secure at rest)
Independent from Gateway — always running
```

### 7.1 Hosted services

| Service | Responsibility |
|---------|----------------|
| **`SwitchControlService`** | Listens on 16002 / 16005; processes control packets (`ProcessCtrlPacketAsync`, `GetSwitchStatusAsync`); drives HVAC relays/switches on a schedule (`SetCtrlSchedule`, `LastCtrlMode`, `LastCtrlStartTime` / `LastCtrlEndTime`, `LastCtrlPatternValue`, manual vs. effective status). Auto-restarts a port listener 5 s after a socket error. |
| **`CtrlStatusService`** | Exposes status at `http://localhost:5101/api/status` (`BuildStatusJson`). |
| **`CtrlHealthWriterService`** | Writes to a monitor table every **30 s**. |
| **`SwitchHealthTracker`** | Tracks per-switch health & ordering (`SwitchOrder`). |

### 7.2 Flow (CtrlGateway)

```
Startup (Windows Service, independent process)
  └─ SelfEncryptingConfig (appsettings.enc only)
  └─ SwitchControlService → listen on 16002, 16005
        └─ ProcessCtrlPacketAsync
              ├─ parse control command / schedule
              ├─ set switch state (on/off, mode, pattern, start/end)
              └─ SwitchHealthTracker update
  └─ CtrlStatusService     → http://localhost:5101/api/status
  └─ CtrlHealthWriterService → monitor table every 30s
  (on listener error → log WRN, restart port in 5s)
```

---

## 8. BmsSmart.Shared — Common Library

`BmsSmart.Shared.dll` (18 KB, .NET 8). Shared by **`BmsSmart.DataGateway`, `BmsSmart.CtrlGateway`, and `BuildSmart.Api`** (the API project is not deployed in this folder).

Key components:

- **`SelfEncryptingConfig`** (`BmsSmart.Shared.Security`) — on first startup, **encrypts `appsettings.json` → `appsettings.enc` using Windows DPAPI** (`System.Security.Cryptography.ProtectedData`) and deletes the plaintext, so secrets are encrypted at rest. Result states (`SelfEncryptResult` / `SelfEncryptSeverity`):
  - `AlreadyEncrypted`, `ReEncryptedAndJsonRemoved`, `EncryptedButJsonRemains`, `SkippedNotService`, `FailedEncrypt`.
  - Skips encryption when not running as a Windows Service (`IsWindowsService`).
  - This is why both gateway folders contain only `appsettings.enc` (no plaintext) — the opposite of the legacy plaintext configs.
  - Log evidence: `SelfEncryptingConfig: first run — encrypted appsettings.json to appsettings.enc and removed plaintext.`
- **`BmsSmart.Shared.TimeZones`** — timezone normalization (devices report local time).

---

## 9. ClientProcess — Test Client

`ClientProcess.exe` (.NET Framework 4.8, 6.6 KB; ships its `.pdb`). Class **`EMSClientTcp`**.

**Purpose:** a **manual simulator** to feed test meter packets into a port without real hardware.

**Config** (`ClientProcess.exe.config`):
```xml
<add key="IpAddress" value="10.0.0.4"/>
<add key="IpPort" value="30009"/>
<add key="TestRawString" value="$00612100DMcDonalds1...319*"/>
```

**Flow:** read `TestRawString` from config → open `TcpClient` to `IpAddress:IpPort` → `GetStream` → send the frame bytes → close. (Also references `TcpListener`, so it can listen/echo too.) Note the misspelled symbol `DBonnecionString` in its metadata.

---

## 10. Shared Libraries (Legacy) — SharedLib & CheckSum

Used by all three DP/LP apps.

### 10.1 `SharedLib.dll` (15 KB, C#)

| Class | Responsibility |
|-------|----------------|
| `HeaderObj` / `HeaderBO` | Parsed frame model (`GetCommandData`, `ProcessBlthData`, `ProcessRawData`). Fields: DataID, ProtocolID, CustomerID, CommunicationId, AckCommand, SiteName, TxnTime, ServerTime, MeterType, TxnDate, TotalString, MeterSerial, TotalBytes, IpPort. |
| `Cache` | `MemoryCache "sitesChache"` — site-name cache with `CacheItemPolicy`. |
| `Sites` | `SiteNames` loader (DB → cache). |
| `DataWriter` / `DataAccess` / `StoredProc` | `SqlConnection` / `SqlCommand` execution; `EnsureGatewayAndGetEndpointId`, `ExecuteScalar`, `Fill`. |
| `Errors` / `AlertProcess` | `ExceptionLog`, `SendToAlertLog`, `WriteException`, `UpsertGatewayAndStatus`. |
| `Ver` | Version info (`VersionNum`). |

### 10.2 `CheckSum.dll` (8.7 KB, VB.NET)

- `CheckSum.ProtechLib` (`CheckSumLib`) — validates the **Protech protocol checksum** (the digits before `*`). Uses `Math.Round`, `Substring`, thread-safe singleton (`ThreadSafeObjectProvider`).

---

## 11. Dependencies

### Legacy DP/LP (`DP-31002.deps.json`)

`BCrypt.Net-Next 4.0.3` · `Nancy 2.0.0` (micro HTTP framework) · `Newtonsoft.Json 13.0.1` · `System.Data.SqlClient 4.8.6` · `System.Runtime.Caching 9.0.2` · `System.Security.Cryptography.ProtectedData 9.0.2` · `System.Configuration.ConfigurationManager 9.0.2` · `SharedLib 1.0.0` · `CheckSum.Reference 1.0.0` · native SQL `sni` runtimes (win-x64/x86/arm64).

### New BmsSmart gateways (`BmsSmart.DataGateway.deps.json` — 70 packages)

`Microsoft.Data.SqlClient` (modern SQL + `SqlBulkCopy`) · `Serilog` + `Serilog.Sinks.File` + `Serilog.Extensions.Hosting/Logging` (the large logs) · `EPPlus` + `EPPlus.Interfaces` (Excel export) · `Microsoft.IdentityModel.JsonWebTokens` / `.Tokens` / `.Protocols.OpenIdConnect` (JWT auth, likely for dashboard/API) · `System.Security.Cryptography.Xml` · `Microsoft.Extensions.Configuration.*` / `Hosting` / DI.

---

## 12. Configuration & Security

| Aspect | Legacy DP/LP | New BmsSmart |
|--------|--------------|--------------|
| Config file | `*.dll.config` (XML `appSettings`) | `appsettings.enc` (encrypted JSON) |
| Secrets at rest | **Plaintext** SQL credentials | **DPAPI-encrypted** via `SelfEncryptingConfig` |
| Connection string | `Server=MsSQLServerDev;Database=Mcdonalds1_AD;user id=admin_sarral;password=LoopDown@002;…` | Inside `appsettings.enc` |
| Hosting | Console app | Windows Service |
| Logging | Console + DB exception SP | Serilog file sinks (`logs/`) |

**DPAPI note:** `appsettings.enc` is encrypted with the Windows account / machine key (DPAPI), so it can only be decrypted by the same service account on the same machine. There is no readable plaintext config in the BmsSmart folders.

---

## 13. End-to-End Data Flow

```
                 ┌─────────────────────────────────────────────────────────┐
 Field devices   │  Meters / temp probes / pH-Lambda sensors in stores     │
 (per store)     │  send  $…*  ASCII frames over raw TCP                    │
                 └───────────────┬─────────────────────────────────────────┘
                                 │  TCP
        ┌────────────────────────┼─────────────────────────────┐
        │                        │                              │
   LEGACY (per port)        NEW DataGateway               NEW CtrlGateway
   DP-31002 (31002)         (ports 31001–31009)           (ports 16002/16005)
   DP-31009 (31009)         TcpGatewayService             SwitchControlService
   LP-30009 (30009)            │  ACK + Queue                 │  control HVAC
        │                      │                              │  switches/relays
        │ checksum+parse       │ PacketQueue                  │
        │ resolve site cache   ▼                              ▼
        │ EXEC stored proc   PacketProcessor → SensorDataHandler   CtrlStatusService
        ▼                      │  SqlBulkCopy → staging        (http :5101/api/status)
   SQL Server                  ▼                              CtrlHealthWriter (30s)
   Mcdonalds1_AD          StagingFlushService
   SD / LV tables          (bulk copy ≤50k → FINAL tables)
   gateway status              │
                               ├─ GatewayHealthService → monitor table
                               ├─ DashboardService → "Gateway Cockpit" UI
                               └─ AI/anomaly episodes (z-score, error-rate, EWMA)
```

**Migration trajectory:** *N processes × 1 port each* (DP/LP, .NET 6, per-row stored-proc inserts, plaintext config) → *2 consolidated Windows Services* (BmsSmart, .NET 8, staging + 50k-row bulk copy, back-pressured queue, dashboard, anomaly detection, encrypted config).

---

## 14. Observations, Risks & Recommendations

| # | Severity | Finding | Recommendation |
|---|----------|---------|----------------|
| 1 | 🔴 High | **Plaintext SQL credentials** in `DP-*/LP-*.dll.config` (`admin_sarral / LoopDown@002`). | Migrate legacy apps to the BmsSmart encrypted-config approach, or decommission them; rotate the exposed password. |
| 2 | 🟠 Medium | **DP-31009 misconfiguration** — its `PortSPName` points at the **31002** stored procedure, not a 31009 one. | Verify intended SP; fix the config. |
| 3 | 🟠 Medium | **Log volume** — DataGateway writes up to **~1 GB/day** (`gateway-20260615.txt` = 1.07 GB) with no visible rotation cap in the folder. | Add Serilog rolling/retention limits; reduce per-packet INF logging (currently 2 lines per packet). |
| 4 | 🟡 Low | A generically-named **`New folder/`** sits at `data/` level (sibling of `PortApps`). It is **not** a BMS artifact — it holds **win-acme** (TLS cert client). See [../New folder/README-win-acme.md](../New%20folder/README-win-acme.md). | Rename to `win-acme/` or remove (check Task Scheduler for a renew task first). |
| 5 | 🟡 Low | **Both generations deployed simultaneously.** If both bind the sensor ports they would conflict — presumably only the BmsSmart gateways are actually started; DP/LP are legacy/standby. | Confirm which services are running; retire the legacy set once validated. |
| 6 | 🟡 Low | `appsettings.enc` is DPAPI-bound to the service account/machine — not portable. | Document the service account; re-encryption is automatic on first run if plaintext is dropped in. |
| 7 | 🟡 Low | **Debug symbols (`.pdb`) shipped to production** in every app folder, exposing internal build paths and full type/method names (eases reverse engineering). | Publish Release builds without PDBs (or strip them) for production deployments. |
| 8 | 🟢 Info | **`BmsSmart-DataGateway.zip` (~22 MB)** sits at the PortApps root — a packaged copy/backup of the DataGateway build, not a running component. | Keep as a rollback artifact or move to a build-archive location; not needed at runtime. |

---

## 15. Quick Reference Tables

### Ports

| Port(s) | Owner | Purpose |
|---------|-------|---------|
| 30009 | LP-30009 (legacy) | Live data → LV table |
| 31002 | DP-31002 (legacy) | Sensor data → SD table |
| 31009 | DP-31009 (legacy) | Sensor data → SD table |
| 31001–31009 | BmsSmart-DataGateway | All sensor data (replaces DP/LP) |
| 16002, 16005 | BmsSmart-CtrlGateway | HVAC switch control (Primary / Secondary) |
| 5101 (HTTP) | BmsSmart-CtrlGateway | `/api/status` |

### Stored procedures (legacy)

| SP | Used by | Purpose |
|----|---------|---------|
| `USP_Raw_To_SDTable_Port_31002_Data` | DP-31002, DP-31009 | Insert raw row → Sensor Data table |
| `USP_Raw_To_LVTable_Port_30009_Live` | LP-30009 | Insert raw row → Live table |
| `USP_Update_Exceptions` | all | Record processing exceptions |

### Key namespaces / types

| Namespace | Notable types |
|-----------|---------------|
| `BmsSmart.DataGateway.Services` | TcpGatewayService, PacketQueue, PacketProcessorService, StagingFlushService, MasterSyncService, GatewayHealthService, DashboardService, PortAliasService, InteractivePortService, RawStringReplayService |
| `BmsSmart.DataGateway.Services.Handlers` | SensorDataHandler, SwitchControlHandler, IPortPacketHandler, PacketDecoder |
| `BmsSmart.CtrlGateway.Services` | SwitchControlService, CtrlStatusService, CtrlHealthWriterService, SwitchHealthTracker |
| `BmsSmart.Shared.Security` | SelfEncryptingConfig, SelfEncryptResult |
| `SharedLib` (legacy) | HeaderObj, Cache, Sites, DataWriter, DataAccess, StoredProc, Errors, AlertProcess, Ver |
| `CheckSum.ProtechLib` (legacy) | CheckSumLib |

---

*Generated from static analysis of the compiled assemblies (metadata + string extraction), config files, dependency manifests, and runtime logs in `data/PortApps/`. No source code was available; behavioral details were inferred from .NET metadata, embedded literals, and Serilog output.*
