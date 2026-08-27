/*
 * SimpleSSD LegoSim active simlet entry point.
 *
 * stdout is reserved for LegoSim-compatible protocol output. Human-readable
 * SimpleSSD logs are routed to stderr through initSimpleSSDEngine().
 */

#include <cerrno>
#include <cinttypes>
#include <cstdlib>
#include <algorithm>
#include <functional>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "bil/entry.hh"
#include "sil/none/none.hh"
#include "sim/cfg_reader.hh"
#include "sim/engine.hh"
#include "simplessd/util/simplessd.hh"

namespace {

const char kInterCmdHead[] = "[INTERCMD]";

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

  Options()
      : ssdX(1),
        ssdY(0),
        npuX(0),
        npuY(0),
        requestBytes(4096),
        iterations(1),
        clockRate(1.0),
        startOffset(0),
        op(OP_READ) {}
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
         "[clock_rate] [start_offset] [read|write]"
      << std::endl;
}

bool parseOptions(int argc, char *argv[], Options &options) {
  if (argc < 4 || argc > 13) {
    return false;
  }

  options.simConfig = argv[1];
  options.ssdConfig = argv[2];
  options.outputDir = argv[3];

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
