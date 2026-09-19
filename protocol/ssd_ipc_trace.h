#pragma once

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <string>

#include "ssd_ipc_protocol.h"

namespace NUSSD {

// Optional, human-facing protocol trace. It is separate from the FIFO wire
// format so observing a run never participates in the simulation protocol.
class SsdIpcTrace {
 public:
  SsdIpcTrace(const char* source, const char* filename) : source_(source) {
    const char* enabled = std::getenv("NUSSD_PROTOCOL_TRACE");
    const char* directory = std::getenv("NUSSD_TRACE_DIR");
    if (enabled == nullptr || std::string(enabled) != "1" ||
        directory == nullptr || *directory == '\0') {
      return;
    }

    stream_.open(std::string(directory) + "/" + filename,
                 std::ios::out | std::ios::app);
    if (!stream_.is_open()) {
      return;
    }
    stream_.seekp(0, std::ios::end);
    if (stream_.tellp() == 0) {
      stream_ << "wall_time_ns\tsource\tevent\trequest_id\toperation\t"
                 "offset_bytes\tlength_bytes\tsim_cycle\tssd_tick_ps\t"
                 "status\n";
      stream_.flush();
    }
  }

  void emit(const char* event, const SsdIpcRequest& request,
            std::uint64_t sim_cycle = 0, std::uint64_t ssd_tick_ps = 0,
            SsdIpcStatus status = SsdIpcStatus::Success) {
    if (!stream_.is_open()) {
      return;
    }
    const auto wall_time_ns =
        std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::system_clock::now().time_since_epoch())
            .count();
    stream_ << wall_time_ns << '\t' << source_ << '\t' << event << '\t'
            << request.request_id << '\t' << operationName(request.operation)
            << '\t' << request.offset_bytes << '\t' << request.length_bytes
            << '\t' << sim_cycle << '\t' << ssd_tick_ps << '\t'
            << statusName(status) << '\n';
    stream_.flush();
  }

 private:
  static const char* operationName(SsdIpcOperation operation) {
    switch (operation) {
      case SsdIpcOperation::Read: return "READ";
      case SsdIpcOperation::Write: return "WRITE";
      case SsdIpcOperation::Flush: return "FLUSH";
      case SsdIpcOperation::Trim: return "TRIM";
      case SsdIpcOperation::Shutdown: return "SHUTDOWN";
    }
    return "UNKNOWN";
  }

  static const char* statusName(SsdIpcStatus status) {
    switch (status) {
      case SsdIpcStatus::Success: return "SUCCESS";
      case SsdIpcStatus::InvalidProtocol: return "INVALID_PROTOCOL";
      case SsdIpcStatus::InvalidOperation: return "INVALID_OPERATION";
      case SsdIpcStatus::InvalidRange: return "INVALID_RANGE";
      case SsdIpcStatus::InternalError: return "INTERNAL_ERROR";
    }
    return "UNKNOWN";
  }

  std::string source_;
  std::ofstream stream_;
};

}  // namespace NUSSD
