#pragma once

#include <cstdint>
#include <type_traits>

namespace NUSSD {

// FIFO protocol shared by the TOGSim requester and the SimpleSSD simlet.
// LegoSim carries the timing information separately through READ/WRITE/SYNC
// commands, so simulation cycles are intentionally absent from the request.
constexpr std::uint32_t kSsdIpcMagic = 0x4E555353U;  // "NUSS"
constexpr std::uint16_t kSsdIpcVersion = 1;

// A read request is represented on the simulated NPU-to-SSD link as a small
// command. The FIFO still carries sizeof(SsdIpcRequest) bytes; this constant
// is the logical transfer size passed to LegoSim/PopNet.
constexpr std::uint64_t kSsdReadCommandBytes = 64;

// Request ID zero is reserved for malformed/uninitialized messages. Runtime
// IDs must also fit in LegoSim's signed-long descriptor field.
constexpr std::uint64_t kInvalidSsdRequestId = 0;

enum class SsdIpcOperation : std::uint8_t {
  Read = 1,
  Write = 2,
  Flush = 3,
  Trim = 4,
  Shutdown = 255,
};

enum class SsdIpcStatus : std::uint16_t {
  Success = 0,
  InvalidProtocol = 1,
  InvalidOperation = 2,
  InvalidRange = 3,
  InternalError = 4,
};

// TOGSim -> SimpleSSD semantic request. offset_bytes is a logical SSD byte
// offset, not a PyTorch host pointer; address translation happens before this
// boundary. flags is reserved for version-1 extension and must currently be 0.
struct SsdIpcRequest {
  std::uint32_t magic = kSsdIpcMagic;
  std::uint16_t version = kSsdIpcVersion;
  SsdIpcOperation operation = SsdIpcOperation::Read;
  std::uint8_t flags = 0;
  std::uint64_t request_id = kInvalidSsdRequestId;
  std::uint64_t offset_bytes = 0;
  std::uint64_t length_bytes = 0;
};

// SimpleSSD -> TOGSim completion metadata. Times are absolute SimpleSSD ticks
// in picoseconds. They describe SSD service only; TOGSim must use LegoSim's
// resolved response-arrival cycle when determining total DMA completion time.
struct SsdIpcResponse {
  std::uint32_t magic = kSsdIpcMagic;
  std::uint16_t version = kSsdIpcVersion;
  SsdIpcStatus status = SsdIpcStatus::Success;
  std::uint64_t request_id = kInvalidSsdRequestId;
  std::uint64_t submitted_tick_ps = 0;
  std::uint64_t completed_tick_ps = 0;
};

constexpr bool hasValidHeader(const SsdIpcRequest& request) {
  return request.magic == kSsdIpcMagic &&
         request.version == kSsdIpcVersion;
}

constexpr bool hasValidHeader(const SsdIpcResponse& response) {
  return response.magic == kSsdIpcMagic &&
         response.version == kSsdIpcVersion;
}

static_assert(std::is_standard_layout<SsdIpcRequest>::value,
              "SSD IPC request must have a stable raw layout");
static_assert(std::is_trivially_copyable<SsdIpcRequest>::value,
              "SSD IPC request must be safe to copy through PipeComm");
static_assert(sizeof(SsdIpcRequest) == 32,
              "SSD IPC request layout changed; bump the protocol version");

static_assert(std::is_standard_layout<SsdIpcResponse>::value,
              "SSD IPC response must have a stable raw layout");
static_assert(std::is_trivially_copyable<SsdIpcResponse>::value,
              "SSD IPC response must be safe to copy through PipeComm");
static_assert(sizeof(SsdIpcResponse) == 32,
              "SSD IPC response layout changed; bump the protocol version");

}  // namespace NUSSD
