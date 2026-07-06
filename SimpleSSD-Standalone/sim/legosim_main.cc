/*
 * SimpleSSD LegoSim active simlet entry point.
 *
 * stdout is reserved for LegoSim-compatible protocol output. Human-readable
 * SimpleSSD logs are routed to stderr through initSimpleSSDEngine().
 */

#include <cerrno>
#include <cinttypes>
#include <cstdlib>
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

enum StorageOp {
  OP_READ,
  OP_WRITE,
};

struct SyncResponse {
  bool ok;
  uint64_t cycle;

  SyncResponse() : ok(false), cycle(0) {}
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

void emitRead(uint64_t cycle, const Options &options, uint64_t bytes) {
  std::cout << kInterCmdHead << " READ " << cycle << " " << options.npuX
            << " " << options.npuY << " " << options.ssdX << " "
            << options.ssdY << " " << bytes << " 0" << std::endl;
}

void emitWrite(uint64_t cycle, const Options &options, uint64_t bytes) {
  std::cout << kInterCmdHead << " WRITE " << cycle << " " << options.ssdX
            << " " << options.ssdY << " " << options.npuX << " "
            << options.npuY << " " << bytes << " 0" << std::endl;
}

void emitResult(const std::vector<std::string> &items) {
  std::cout << kInterCmdHead << " RESULT " << items.size();

  for (auto &item : items) {
    std::cout << " " << item;
  }

  std::cout << std::endl;
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

  uint64_t nextOffset = options.startOffset;
  uint64_t nextID = 1;
  uint64_t submittedReads = 0;
  uint64_t submittedWrites = 0;
  uint64_t bytesRead = 0;
  uint64_t bytesWritten = 0;
  uint64_t currentCycle = 1;

  auto runStorageIO = [&](uint64_t arrivalCycle, uint64_t bytes) -> uint64_t {
    bool done = false;
    uint64_t completionTick = 0;
    SimpleSSD::Event submitEvent = 0;

    submitEvent = engine.allocateEvent([&](uint64_t) {
      BIL::BIO bio;

      bio.id = nextID++;
      bio.type = options.op == OP_READ ? BIL::BIO_READ : BIL::BIO_WRITE;
      bio.offset = nextOffset;
      bio.length = bytes;
      bio.callback = [&](uint64_t) {
        completionTick = engine.getCurrentTick();
        done = true;
      };

      bioEntry.submitIO(bio);

      if (options.op == OP_READ) {
        submittedReads++;
        bytesRead += bytes;
      }
      else {
        submittedWrites++;
        bytesWritten += bytes;
      }

      nextOffset += bytes;
      if (capacity > 0 && nextOffset >= capacity) {
        nextOffset %= capacity;
      }
    });

    engine.scheduleEvent(
        submitEvent, static_cast<uint64_t>(arrivalCycle * options.clockRate));

    while (!done && engine.doNextEvent()) {
    }

    engine.deallocateEvent(submitEvent);

    return static_cast<uint64_t>(completionTick / options.clockRate);
  };

  emitResult({"capacity", std::to_string(capacity), "min_io_size",
              std::to_string(minBlockSize)});

  for (uint64_t i = 0; i < options.iterations; i++) {
    SyncResponse arrival;
    SyncResponse returned;

    emitRead(currentCycle, options, options.requestBytes);

    if (!waitForSync(arrival)) {
      std::cerr << "Failed to receive request-arrival SYNC." << std::endl;
      releaseSimpleSSDEngine();
      return 4;
    }

    uint64_t flashDoneCycle =
        runStorageIO(arrival.cycle, options.requestBytes);

    emitWrite(flashDoneCycle, options, options.requestBytes);

    if (!waitForSync(returned)) {
      std::cerr << "Failed to receive return-path SYNC." << std::endl;
      releaseSimpleSSDEngine();
      return 5;
    }

    currentCycle = returned.cycle;
  }

  emitResult({"reads", std::to_string(submittedReads), "writes",
              std::to_string(submittedWrites), "bytes_read",
              std::to_string(bytesRead), "bytes_written",
              std::to_string(bytesWritten), "completed",
              std::to_string(options.iterations)});

  releaseSimpleSSDEngine();

  return 0;
}
