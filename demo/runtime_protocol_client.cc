#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

#include "pipe_comm.h"
#include "ssd_ipc_protocol.h"
#include "ssd_ipc_trace.h"

namespace {

constexpr long kNpuX = 0;
constexpr long kNpuY = 0;
constexpr long kSsdX = 1;
constexpr long kSsdY = 0;

struct Result {
  NUSSD::SsdIpcResponse response;
  InterChiplet::TimeType completion_cycle;
};

NUSSD::SsdIpcTrace &trace() {
  static NUSSD::SsdIpcTrace value("NPU", "npu.events.tsv");
  return value;
}

Result roundTrip(InterChiplet::PipeComm &pipe,
                 const NUSSD::SsdIpcRequest &request,
                 InterChiplet::TimeType issue_cycle,
                 std::uint64_t request_bytes,
                 std::uint64_t response_bytes) {
  const long descriptor = static_cast<long>(request.request_id);

  const std::string request_pipe =
      InterChiplet::sendSync(kNpuX, kNpuY, kSsdX, kSsdY);
  if (pipe.write_data(request_pipe.c_str(),
                      const_cast<NUSSD::SsdIpcRequest *>(&request),
                      sizeof(request)) != static_cast<int>(sizeof(request))) {
    throw std::runtime_error("failed to write complete SSD request");
  }
  trace().emit("NPU_REQUEST_FIFO_SENT", request, issue_cycle);
  const InterChiplet::TimeType command_arrival = InterChiplet::writeSync(
      issue_cycle, kNpuX, kNpuY, kSsdX, kSsdY,
      static_cast<int>(request_bytes), descriptor);
  trace().emit("NPU_COMMAND_ARRIVAL_RESOLVED", request, command_arrival);

  const std::string response_pipe =
      InterChiplet::receiveSync(kSsdX, kSsdY, kNpuX, kNpuY);
  NUSSD::SsdIpcResponse response;
  if (pipe.read_data(response_pipe.c_str(), &response, sizeof(response)) !=
      static_cast<int>(sizeof(response))) {
    throw std::runtime_error("failed to read complete SSD response");
  }
  trace().emit("NPU_RESPONSE_FIFO_RECEIVED", request, issue_cycle,
               response.completed_tick_ps, response.status);

  const std::uint64_t actual_response_bytes =
      response.status == NUSSD::SsdIpcStatus::Success
          ? response_bytes
          : NUSSD::kSsdReadCommandBytes;
  const InterChiplet::TimeType completion_cycle = InterChiplet::readSync(
      issue_cycle, kSsdX, kSsdY, kNpuX, kNpuY,
      static_cast<int>(actual_response_bytes), descriptor);
  trace().emit("NPU_RESPONSE_ARRIVED", request, completion_cycle,
               response.completed_tick_ps, response.status);

  if (!NUSSD::hasValidHeader(response) ||
      response.request_id != request.request_id ||
      response.status != NUSSD::SsdIpcStatus::Success) {
    throw std::runtime_error("SimpleSSD returned an invalid protocol response");
  }
  trace().emit("NPU_REQUEST_COMPLETE", request, completion_cycle,
               response.completed_tick_ps, response.status);
  return {response, completion_cycle};
}

std::uint64_t parseUnsigned(const char *text, const char *name) {
  try {
    std::size_t consumed = 0;
    const std::uint64_t value = std::stoull(text, &consumed, 0);
    if (text[consumed] != '\0') {
      throw std::invalid_argument("trailing input");
    }
    return value;
  }
  catch (const std::exception &) {
    std::cerr << "Invalid " << name << ": " << text << std::endl;
    std::exit(2);
  }
}

}  // namespace

int main(int argc, char **argv) {
  if (argc != 3) {
    std::cerr << "Usage: " << argv[0] << " <offset_bytes> <length_bytes>"
              << std::endl;
    return 2;
  }

  const std::uint64_t offset = parseUnsigned(argv[1], "offset");
  const std::uint64_t length = parseUnsigned(argv[2], "length");
  if (length == 0 ||
      length > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
    std::cerr << "Length must be between 1 and INT_MAX bytes." << std::endl;
    return 2;
  }

  try {
    InterChiplet::PipeComm pipe;
    NUSSD::SsdIpcRequest read;
    read.operation = NUSSD::SsdIpcOperation::Read;
    read.request_id = 1;
    read.offset_bytes = offset;
    read.length_bytes = length;
    trace().emit("NPU_ISSUE", read, 1);
    const Result read_result = roundTrip(
        pipe, read, 1, NUSSD::kSsdReadCommandBytes, length);

    NUSSD::SsdIpcRequest shutdown;
    shutdown.operation = NUSSD::SsdIpcOperation::Shutdown;
    shutdown.request_id = 2;
    trace().emit("NPU_SHUTDOWN", shutdown, read_result.completion_cycle);
    const Result shutdown_result = roundTrip(
        pipe, shutdown, read_result.completion_cycle,
        NUSSD::kSsdReadCommandBytes, NUSSD::kSsdReadCommandBytes);

    InterChiplet::sendCycleCmd(shutdown_result.completion_cycle);
    std::cout << "NUSSD protocol demo completed: request_id=1 offset="
              << offset << " bytes=" << length
              << " completion_cycle=" << read_result.completion_cycle
              << std::endl;
  }
  catch (const std::exception &error) {
    std::cerr << "NUSSD protocol demo failed: " << error.what() << std::endl;
    return 1;
  }
  return 0;
}
