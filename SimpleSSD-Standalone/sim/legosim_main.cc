/*
 * SimpleSSD LegoSim active simlet entry point.
 *
 * stdout is reserved for LegoSim-compatible protocol output. Human-readable
 * SimpleSSD logs are routed to stderr through initSimpleSSDEngine().
 */

#include <cerrno>
#include <cmath>
#include <cinttypes>
#include <cstdlib>
#include <algorithm>
#include <functional>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#include "bil/entry.hh"
#include "pipe_comm.h"
#include "sil/none/none.hh"
#include "sim/cfg_reader.hh"
#include "sim/engine.hh"
#include "simplessd/util/simplessd.hh"
#include "ssd_ipc_protocol.h"
#include "ssd_ipc_trace.h"

namespace {

const char kInterCmdHead[] = "[INTERCMD]";

NUSSD::SsdIpcTrace &protocolTrace() {
  static NUSSD::SsdIpcTrace trace("SSD", "ssd.events.tsv");
  return trace;
}

// --- Read-path command/data leg split -----------------------------------
// See PyTorchSim/TOGSim/src/DramLegoSim.cc for the full rationale (search
// for kEnableReadCommandShrink there). Summary: for read requests, the
// request-arrival leg (this side's READ, paired against the NPU's WRITE)
// should declare a small fixed-size command instead of the full transfer
// size; the completion leg (this side's WRITE, carrying the real data)
// stays at the real request size.
//
// IMPORTANT: kReadCmdBytes here MUST be numerically identical to the
// constant of the same name in DramLegoSim.cc. LegoSim's coordinator
// (interchiplet/includes/cmd_handler.h: hasMatchWrite/hasMatchRead)
// requires the WRITE and READ legs of a pair to declare the exact same
// nbytes, or the two simlets hang waiting for a SYNC that never arrives.
//
// Set kEnableReadCommandShrink = false (matching the NPU side) to restore
// the original single-size-both-legs baseline without touching anything
// else.
constexpr bool kEnableReadCommandShrink = true;
constexpr uint64_t kReadCmdBytes = 64;  // e.g. an NVMe read command (LBA + length)

enum StorageOp {
  OP_READ,
  OP_WRITE,
};

struct SyncResponse {
  bool ok;
  bool hasDesc;
  uint64_t cycle;
  long desc;

  SyncResponse() : ok(false), hasDesc(false), cycle(0), desc(0) {}
};

struct PendingIO {
  long desc;
  uint64_t offset;
  uint64_t bytes;
  uint64_t arrivalCycle;
  uint64_t submittedTick;
  uint64_t completionTick;
  uint64_t completionCycle;
  bool done;
  bool returned;
  SimpleSSD::Event submitEvent;

  PendingIO()
      : desc(0),
        offset(0),
        bytes(0),
        arrivalCycle(0),
        submittedTick(0),
        completionTick(0),
        completionCycle(0),
        done(false),
        returned(false),
        submitEvent(0) {}
};

struct Options {
  std::string simConfig;
  std::string ssdConfig;
  std::string outputDir;
  long ssdX;
  long ssdY;
  long npuX;
  long npuY;
  uint64_t requestBytes;
  uint64_t iterations;
  double clockRate;
  uint64_t startOffset;
  StorageOp op;
  bool runtimeIpc;

  Options()
      : ssdX(1),
        ssdY(0),
        npuX(0),
        npuY(0),
        requestBytes(4096),
        iterations(1),
        clockRate(1.0),
        startOffset(0),
        op(OP_READ),
        runtimeIpc(false) {}
};

bool parseUint64(const char *text, uint64_t &value) {
  char *end = nullptr;
  errno = 0;
  unsigned long long parsed = std::strtoull(text, &end, 0);

  if (errno != 0 || end == text || *end != '\0') {
    return false;
  }

  value = static_cast<uint64_t>(parsed);
  return true;
}

bool parseLong(const char *text, long &value) {
  char *end = nullptr;
  errno = 0;
  long parsed = std::strtol(text, &end, 0);

  if (errno != 0 || end == text || *end != '\0') {
    return false;
  }

  value = parsed;
  return true;
}

bool parseDouble(const char *text, double &value) {
  char *end = nullptr;
  errno = 0;
  double parsed = std::strtod(text, &end);

  if (errno != 0 || end == text || *end != '\0' || parsed <= 0.0) {
    return false;
  }

  value = parsed;
  return true;
}

bool parseOp(const char *text, StorageOp &op) {
  std::string value(text);

  if (value == "read") {
    op = OP_READ;
    return true;
  }
  if (value == "write") {
    op = OP_WRITE;
    return true;
  }

  return false;
}

void printUsage() {
  std::cerr
      << "Usage: simplessd-legosim <Simulation configuration file> "
         "<SimpleSSD configuration file> <Output directory> "
         "[ssd_x] [ssd_y] [npu_x] [npu_y] [request_bytes] [iterations] "
         "[clock_rate] [start_offset] [read|write]\n"
         "   or: simplessd-legosim <Simulation configuration file> "
         "<SimpleSSD configuration file> <Output directory> --runtime-ipc "
         "[ssd_x] [ssd_y] [npu_x] [npu_y] [clock_rate]"
      << std::endl;
}

bool parseOptions(int argc, char *argv[], Options &options) {
  if (argc < 4) {
    return false;
  }

  options.simConfig = argv[1];
  options.ssdConfig = argv[2];
  options.outputDir = argv[3];

  if (argc >= 5 && std::string(argv[4]) == "--runtime-ipc") {
    if (argc > 10) {
      return false;
    }

    options.runtimeIpc = true;
    if (argc >= 6 && !parseLong(argv[5], options.ssdX)) {
      return false;
    }
    if (argc >= 7 && !parseLong(argv[6], options.ssdY)) {
      return false;
    }
    if (argc >= 8 && !parseLong(argv[7], options.npuX)) {
      return false;
    }
    if (argc >= 9 && !parseLong(argv[8], options.npuY)) {
      return false;
    }
    if (argc >= 10 && !parseDouble(argv[9], options.clockRate)) {
      return false;
    }
    return true;
  }

  if (argc > 13) {
    return false;
  }

  if (argc >= 5 && !parseLong(argv[4], options.ssdX)) {
    return false;
  }
  if (argc >= 6 && !parseLong(argv[5], options.ssdY)) {
    return false;
  }
  if (argc >= 7 && !parseLong(argv[6], options.npuX)) {
    return false;
  }
  if (argc >= 8 && !parseLong(argv[7], options.npuY)) {
    return false;
  }
  if (argc >= 9 && !parseUint64(argv[8], options.requestBytes)) {
    return false;
  }
  if (argc >= 10 && !parseUint64(argv[9], options.iterations)) {
    return false;
  }
  if (argc >= 11 && !parseDouble(argv[10], options.clockRate)) {
    return false;
  }
  if (argc >= 12 && !parseUint64(argv[11], options.startOffset)) {
    return false;
  }
  if (argc >= 13 && !parseOp(argv[12], options.op)) {
    return false;
  }

  return options.requestBytes > 0 && options.iterations > 0;
}

uint64_t requestWireBytes(const NUSSD::SsdIpcRequest &request) {
  return request.operation == NUSSD::SsdIpcOperation::Write
             ? request.length_bytes
             : NUSSD::kSsdReadCommandBytes;
}

uint64_t responseWireBytes(const NUSSD::SsdIpcRequest &request) {
  return request.operation == NUSSD::SsdIpcOperation::Read
             ? request.length_bytes
             : NUSSD::kSsdReadCommandBytes;
}

bool requestToBioType(const NUSSD::SsdIpcRequest &request,
                      BIL::BIO_TYPE &type) {
  switch (request.operation) {
    case NUSSD::SsdIpcOperation::Read:
      type = BIL::BIO_READ;
      return true;
    case NUSSD::SsdIpcOperation::Write:
      type = BIL::BIO_WRITE;
      return true;
    case NUSSD::SsdIpcOperation::Flush:
      type = BIL::BIO_FLUSH;
      return true;
    case NUSSD::SsdIpcOperation::Trim:
      type = BIL::BIO_TRIM;
      return true;
    case NUSSD::SsdIpcOperation::Shutdown:
      return false;
  }

  return false;
}

NUSSD::SsdIpcStatus validateRuntimeRequest(
    const NUSSD::SsdIpcRequest &request, uint64_t capacity) {
  if (!NUSSD::hasValidHeader(request) || request.flags != 0 ||
      request.request_id == NUSSD::kInvalidSsdRequestId ||
      request.request_id >
          static_cast<uint64_t>(std::numeric_limits<long>::max())) {
    return NUSSD::SsdIpcStatus::InvalidProtocol;
  }

  if (request.operation == NUSSD::SsdIpcOperation::Shutdown) {
    return NUSSD::SsdIpcStatus::Success;
  }

  BIL::BIO_TYPE ignored;
  if (!requestToBioType(request, ignored)) {
    return NUSSD::SsdIpcStatus::InvalidOperation;
  }

  if (request.operation == NUSSD::SsdIpcOperation::Flush) {
    return NUSSD::SsdIpcStatus::Success;
  }

  if (request.length_bytes == 0 || request.offset_bytes >= capacity ||
      request.length_bytes > capacity - request.offset_bytes) {
    return NUSSD::SsdIpcStatus::InvalidRange;
  }

  return NUSSD::SsdIpcStatus::Success;
}

void emitRead(uint64_t cycle, const Options &options, uint64_t bytes,
              long desc) {
  std::cout << std::endl << kInterCmdHead << " READ " << cycle << " " << options.npuX
            << " " << options.npuY << " " << options.ssdX << " "
            << options.ssdY << " " << bytes << " " << desc << std::endl;
}

void emitWrite(uint64_t cycle, const Options &options, uint64_t bytes,
               long desc) {
  std::cout << std::endl << kInterCmdHead << " WRITE " << cycle << " " << options.ssdX
            << " " << options.ssdY << " " << options.npuX << " "
            << options.npuY << " " << bytes << " " << desc << std::endl;
}

void emitResult(const std::vector<std::string> &items) {
  std::cout << std::endl << kInterCmdHead << " RESULT " << items.size();

  for (auto &item : items) {
    std::cout << " " << item;
  }

  std::cout << std::endl;
}

void emitCycle(uint64_t cycle) {
  std::cout << std::endl << kInterCmdHead << " CYCLE " << cycle << std::endl;
}

bool parseSyncLine(const std::string &line, SyncResponse &response) {
  std::string message = line;

  if (message.compare(0, sizeof(kInterCmdHead) - 1, kInterCmdHead) == 0) {
    message = message.substr(sizeof(kInterCmdHead));
  }

  std::stringstream ss(message);
  std::string type;
  uint64_t cycle = 0;

  ss >> type;
  if (type != "SYNC") {
    return false;
  }

  ss >> cycle;
  if (!ss) {
    return false;
  }

  response.ok = true;
  response.cycle = cycle;
  if (ss >> response.desc) {
    response.hasDesc = true;
  }

  return true;
}

bool waitForSync(SyncResponse &response) {
  std::string line;

  while (std::getline(std::cin, line)) {
    if (line.empty()) {
      continue;
    }

    if (parseSyncLine(line, response)) {
      return true;
    }

    std::cerr << "Ignoring non-SYNC command on stdin: " << line << std::endl;
  }

  return false;
}

int runRuntimeIpc(const Options &options, Engine &engine,
                  BIL::BlockIOEntry &bioEntry, uint64_t capacity,
                  uint32_t minBlockSize) {
  InterChiplet::PipeComm pipeComm;
  uint64_t currentCycle = 1;
  uint64_t submittedReads = 0;
  uint64_t submittedWrites = 0;
  uint64_t bytesRead = 0;
  uint64_t bytesWritten = 0;
  uint64_t completedRequests = 0;

  emitResult({"capacity", std::to_string(capacity), "min_io_size",
              std::to_string(minBlockSize), "runtime_ipc", "1"});

  while (true) {
    // receiveSync/read_data are blocking operations. While the request queue
    // is idle, the kernel sleeps this process until the requester and LegoSim
    // make the FIFO available; there is no polling loop here.
    std::string requestPipe = InterChiplet::receiveSync(
        options.npuX, options.npuY, options.ssdX, options.ssdY);
    NUSSD::SsdIpcRequest request;
    if (pipeComm.read_data(requestPipe.c_str(), &request, sizeof(request)) !=
        static_cast<int>(sizeof(request))) {
      std::cerr << "Failed to receive complete SSD IPC request." << std::endl;
      return 4;
    }
    protocolTrace().emit("SSD_REQUEST_FIFO_RECEIVED", request, currentCycle,
                         engine.getCurrentTick());

    const long desc =
        request.request_id <=
                static_cast<uint64_t>(std::numeric_limits<long>::max())
            ? static_cast<long>(request.request_id)
            : 0;
    const uint64_t requestBytes = requestWireBytes(request);
    if (requestBytes >
        static_cast<uint64_t>(std::numeric_limits<int>::max())) {
      std::cerr << "SSD IPC request leg exceeds LegoSim's byte-count range."
                << std::endl;
      return 4;
    }

    const InterChiplet::TimeType arrivalCycle = InterChiplet::readSync(
        currentCycle, options.npuX, options.npuY, options.ssdX,
        options.ssdY, static_cast<int>(requestBytes), desc);
    protocolTrace().emit("SSD_REQUEST_ARRIVED", request, arrivalCycle,
                         engine.getCurrentTick());

    NUSSD::SsdIpcResponse response;
    response.request_id = request.request_id;
    response.status = validateRuntimeRequest(request, capacity);

    const bool shutdown =
        response.status == NUSSD::SsdIpcStatus::Success &&
        request.operation == NUSSD::SsdIpcOperation::Shutdown;

    if (response.status == NUSSD::SsdIpcStatus::Success && !shutdown) {
      BIL::BIO_TYPE bioType = BIL::BIO_READ;
      if (!requestToBioType(request, bioType)) {
        response.status = NUSSD::SsdIpcStatus::InvalidOperation;
      }
      else {
        bool done = false;
        SimpleSSD::Event submitEvent = 0;
        const uint64_t requestedArrivalTick = static_cast<uint64_t>(
            static_cast<double>(arrivalCycle) * options.clockRate);
        const uint64_t arrivalTick =
            std::max(engine.getCurrentTick(), requestedArrivalTick);

        submitEvent = engine.allocateEvent([&](uint64_t) {
          BIL::BIO bio;
          response.submitted_tick_ps = engine.getCurrentTick();
          protocolTrace().emit("SSD_BIO_SUBMITTED", request, arrivalCycle,
                               response.submitted_tick_ps);
          bio.id = request.request_id;
          bio.type = bioType;
          bio.offset = request.offset_bytes;
          bio.length = request.length_bytes;
          bio.callback = [&](uint64_t completedID) {
            if (completedID == request.request_id) {
              response.completed_tick_ps = engine.getCurrentTick();
              protocolTrace().emit("SSD_BIO_COMPLETED", request, arrivalCycle,
                                   response.completed_tick_ps);
              done = true;
            }
          };
          bioEntry.submitIO(bio);
        });

        engine.scheduleEvent(submitEvent, arrivalTick);
        while (!done && engine.doNextEvent()) {
        }
        engine.deallocateEvent(submitEvent);

        if (!done) {
          response.status = NUSSD::SsdIpcStatus::InternalError;
          response.completed_tick_ps = engine.getCurrentTick();
        }
        else {
          completedRequests++;
          if (request.operation == NUSSD::SsdIpcOperation::Read) {
            submittedReads++;
            bytesRead += request.length_bytes;
          }
          else if (request.operation == NUSSD::SsdIpcOperation::Write) {
            submittedWrites++;
            bytesWritten += request.length_bytes;
          }
        }
      }
    }

    uint64_t completionCycle = currentCycle;
    if (response.completed_tick_ps > 0) {
      completionCycle = static_cast<uint64_t>(std::ceil(
          static_cast<double>(response.completed_tick_ps) /
          options.clockRate));
    }
    completionCycle = std::max(completionCycle,
                               static_cast<uint64_t>(arrivalCycle));

    std::string responsePipe = InterChiplet::sendSync(
        options.ssdX, options.ssdY, options.npuX, options.npuY);
    if (pipeComm.write_data(responsePipe.c_str(), &response,
                            sizeof(response)) !=
        static_cast<int>(sizeof(response))) {
      std::cerr << "Failed to send complete SSD IPC response." << std::endl;
      return 5;
    }

    const uint64_t responseBytes =
        response.status == NUSSD::SsdIpcStatus::Success
            ? responseWireBytes(request)
            : NUSSD::kSsdReadCommandBytes;
    if (responseBytes >
        static_cast<uint64_t>(std::numeric_limits<int>::max())) {
      std::cerr << "SSD IPC response leg exceeds LegoSim's byte-count range."
                << std::endl;
      return 5;
    }

    const InterChiplet::TimeType returnedCycle = InterChiplet::writeSync(
        completionCycle, options.ssdX, options.ssdY, options.npuX,
        options.npuY, static_cast<int>(responseBytes), desc);
    protocolTrace().emit("SSD_RESPONSE_TRANSFER_RESOLVED", request, returnedCycle,
                         response.completed_tick_ps, response.status);
    currentCycle = std::max(completionCycle,
                            static_cast<uint64_t>(returnedCycle));

    if (shutdown) {
      protocolTrace().emit("SSD_SHUTDOWN", request, currentCycle,
                           engine.getCurrentTick(), response.status);
      break;
    }
  }

  emitResult({"reads", std::to_string(submittedReads), "writes",
              std::to_string(submittedWrites), "bytes_read",
              std::to_string(bytesRead), "bytes_written",
              std::to_string(bytesWritten), "completed",
              std::to_string(completedRequests)});
  emitCycle(currentCycle);
  return 0;
}

}  // namespace

int main(int argc, char *argv[]) {
  Options options;

  if (!parseOptions(argc, argv, options)) {
    printUsage();
    return 1;
  }

  Engine engine;
  ConfigReader simConfig;

  if (!simConfig.init(options.simConfig)) {
    std::cerr << "Failed to open simulation configuration file." << std::endl;
    return 2;
  }

  auto ssdConfig =
      initSimpleSSDEngine(&engine, &std::cerr, &std::cerr, options.ssdConfig);
  SIL::None::Driver driver(engine, ssdConfig);
  BIL::BlockIOEntry bioEntry(simConfig, engine, &driver, nullptr);

  bool initialized = false;
  std::function<void()> beginCallback = [&initialized]() { initialized = true; };
  driver.init(beginCallback);

  while (!initialized && engine.doNextEvent()) {
  }

  if (!initialized) {
    std::cerr << "Failed to initialize SimpleSSD driver." << std::endl;
    releaseSimpleSSDEngine();
    return 3;
  }

  uint64_t capacity = 0;
  uint32_t minBlockSize = 0;
  driver.getInfo(capacity, minBlockSize);

  if (options.runtimeIpc) {
    int status =
        runRuntimeIpc(options, engine, bioEntry, capacity, minBlockSize);
    releaseSimpleSSDEngine();
    return status;
  }

  uint64_t nextID = 1;
  uint64_t submittedReads = 0;
  uint64_t submittedWrites = 0;
  uint64_t bytesRead = 0;
  uint64_t bytesWritten = 0;
  uint64_t currentCycle = 1;

  auto runStorageIOBlocking = [&](uint64_t arrivalCycle, uint64_t offset,
                                  uint64_t bytes, StorageOp op) -> uint64_t {
    bool done = false;
    uint64_t submittedTick = 0;
    uint64_t completionTick = 0;
    SimpleSSD::Event submitEvent = 0;

    submitEvent = engine.allocateEvent([&](uint64_t) {
      BIL::BIO bio;

      submittedTick = engine.getCurrentTick();
      bio.id = nextID++;
      bio.type = op == OP_READ ? BIL::BIO_READ : BIL::BIO_WRITE;
      bio.offset = offset;
      bio.length = bytes;
      bio.callback = [&](uint64_t) {
        completionTick = engine.getCurrentTick();
        done = true;
      };

      bioEntry.submitIO(bio);

      if (op == OP_READ) {
        submittedReads++;
        bytesRead += bytes;
      }
      else {
        submittedWrites++;
        bytesWritten += bytes;
      }
    });

    engine.scheduleEvent(
        submitEvent, static_cast<uint64_t>(arrivalCycle * options.clockRate));

    while (!done && engine.doNextEvent()) {
    }

    engine.deallocateEvent(submitEvent);

    return static_cast<uint64_t>((completionTick - submittedTick) /
                                 options.clockRate);
  };

  auto submitStorageIOAsync = [&](PendingIO &pending, StorageOp op) {
    PendingIO *pendingPtr = &pending;
    pending.submitEvent = engine.allocateEvent([&, op, pendingPtr](uint64_t) {
      BIL::BIO bio;

      pendingPtr->submittedTick = engine.getCurrentTick();
      bio.id = nextID++;
      bio.type = op == OP_READ ? BIL::BIO_READ : BIL::BIO_WRITE;
      bio.offset = pendingPtr->offset;
      bio.length = pendingPtr->bytes;
      bio.callback = [pendingPtr, &engine, &options](uint64_t) {
        pendingPtr->completionTick = engine.getCurrentTick();
        uint64_t latency =
            static_cast<uint64_t>((pendingPtr->completionTick -
                                   pendingPtr->submittedTick) /
                                  options.clockRate);
        pendingPtr->completionCycle = pendingPtr->arrivalCycle + latency;
        pendingPtr->done = true;
      };

      bioEntry.submitIO(bio);

      if (op == OP_READ) {
        submittedReads++;
        bytesRead += pendingPtr->bytes;
      }
      else {
        submittedWrites++;
        bytesWritten += pendingPtr->bytes;
      }
    });

    engine.scheduleEvent(
        pending.submitEvent,
        static_cast<uint64_t>(pending.arrivalCycle * options.clockRate));
  };

  emitResult({"capacity", std::to_string(capacity), "min_io_size",
              std::to_string(minBlockSize)});

  std::vector<PendingIO> pending(options.iterations);
  uint64_t nextOffset = options.startOffset;

  for (uint64_t i = 0; i < options.iterations; i++) {
    pending[i].desc = static_cast<long>((i + 1) * 8);
    pending[i].offset = nextOffset;
    pending[i].bytes = options.requestBytes;

    if (options.op == OP_READ) {
      runStorageIOBlocking(0, pending[i].offset, pending[i].bytes, OP_WRITE);
    }

    nextOffset += options.requestBytes;
    if (capacity > 0 && nextOffset >= capacity) {
      nextOffset %= capacity;
    }
  }

  // Wire size of the request-arrival leg. For reads, this pairs against
  // DramLegoSim's WRITE(command_bytes) leg and must match it exactly (see
  // kReadCmdBytes comment above); the SSD's own internal service size
  // (pending[i].bytes, set above) is unaffected and stays the real
  // options.requestBytes regardless of this leg's declared wire size.
  const uint64_t requestLegBytes =
      (kEnableReadCommandShrink && options.op == OP_READ)
          ? kReadCmdBytes
          : options.requestBytes;
  for (uint64_t i = 0; i < options.iterations; i++) {
    emitRead(currentCycle + i, options, requestLegBytes, pending[i].desc);
  }

  uint64_t arrivals = 0;
  while (arrivals < options.iterations) {
    SyncResponse arrival;
    if (!waitForSync(arrival)) {
      std::cerr << "Failed to receive request-arrival SYNC." << std::endl;
      releaseSimpleSSDEngine();
      return 4;
    }

    uint64_t index = arrivals;
    if (arrival.hasDesc) {
      if (arrival.desc <= 0 || arrival.desc % 8 != 0 ||
          static_cast<uint64_t>(arrival.desc / 8) == 0 ||
          static_cast<uint64_t>(arrival.desc / 8) > pending.size()) {
        std::cerr << "Received request-arrival SYNC with invalid desc "
                  << arrival.desc << "." << std::endl;
        releaseSimpleSSDEngine();
        return 4;
      }
      index = static_cast<uint64_t>(arrival.desc / 8 - 1);
    }

    pending[index].arrivalCycle = arrival.cycle;
    submitStorageIOAsync(pending[index], options.op);
    arrivals++;
  }

  uint64_t completed = 0;
  while (completed < options.iterations && engine.doNextEvent()) {
    for (auto &item : pending) {
      if (item.done && item.submitEvent != 0) {
        engine.deallocateEvent(item.submitEvent);
        item.submitEvent = 0;
        emitWrite(item.completionCycle, options, item.bytes, item.desc);
        completed++;
      }
    }
  }

  if (completed != options.iterations) {
    std::cerr << "Failed to complete all storage requests." << std::endl;
    releaseSimpleSSDEngine();
    return 5;
  }

  uint64_t returnedCount = 0;
  while (returnedCount < options.iterations) {
    SyncResponse returned;
    if (!waitForSync(returned)) {
      std::cerr << "Failed to receive return-path SYNC." << std::endl;
      releaseSimpleSSDEngine();
      return 6;
    }

    uint64_t index = returnedCount;
    if (returned.hasDesc) {
      if (returned.desc <= 0 || returned.desc % 8 != 0 ||
          static_cast<uint64_t>(returned.desc / 8) == 0 ||
          static_cast<uint64_t>(returned.desc / 8) > pending.size()) {
        std::cerr << "Received return-path SYNC with invalid desc "
                  << returned.desc << "." << std::endl;
        releaseSimpleSSDEngine();
        return 6;
      }
      index = static_cast<uint64_t>(returned.desc / 8 - 1);
    }

    pending[index].returned = true;
    currentCycle = std::max(currentCycle, returned.cycle);
    returnedCount++;
  }

  emitResult({"reads", std::to_string(submittedReads), "writes",
              std::to_string(submittedWrites), "bytes_read",
              std::to_string(bytesRead), "bytes_written",
              std::to_string(bytesWritten), "completed",
              std::to_string(options.iterations)});
  emitCycle(currentCycle);

  releaseSimpleSSDEngine();

  return 0;
}
