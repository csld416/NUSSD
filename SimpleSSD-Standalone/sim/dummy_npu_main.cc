/*
 * Tiny LegoSim peer for exercising simplessd-legosim.
 *
 * It mirrors the SimpleSSD active endpoint:
 *   WRITE request to SSD -> wait SYNC -> READ result from SSD -> wait SYNC.
 */

#include <cerrno>
#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

const char kInterCmdHead[] = "[INTERCMD]";

struct Options {
  long npuX;
  long npuY;
  long ssdX;
  long ssdY;
  uint64_t requestBytes;
  uint64_t iterations;
  uint64_t startCycle;

  Options()
      : npuX(0),
        npuY(0),
        ssdX(1),
        ssdY(0),
        requestBytes(4096),
        iterations(1),
        startCycle(1) {}
};

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

void printUsage() {
  std::cerr << "Usage: simplessd-dummy-npu [npu_x] [npu_y] [ssd_x] [ssd_y] "
               "[request_bytes] [iterations] [start_cycle]"
            << std::endl;
}

bool parseOptions(int argc, char *argv[], Options &options) {
  if (argc > 8) {
    return false;
  }

  if (argc >= 2 && !parseLong(argv[1], options.npuX)) {
    return false;
  }
  if (argc >= 3 && !parseLong(argv[2], options.npuY)) {
    return false;
  }
  if (argc >= 4 && !parseLong(argv[3], options.ssdX)) {
    return false;
  }
  if (argc >= 5 && !parseLong(argv[4], options.ssdY)) {
    return false;
  }
  if (argc >= 6 && !parseUint64(argv[5], options.requestBytes)) {
    return false;
  }
  if (argc >= 7 && !parseUint64(argv[6], options.iterations)) {
    return false;
  }
  if (argc >= 8 && !parseUint64(argv[7], options.startCycle)) {
    return false;
  }

  return options.requestBytes > 0 && options.iterations > 0;
}

void emitWrite(uint64_t cycle, const Options &options) {
  std::cout << kInterCmdHead << " WRITE " << cycle << " " << options.npuX
            << " " << options.npuY << " " << options.ssdX << " "
            << options.ssdY << " " << options.requestBytes << " 0"
            << std::endl;
}

void emitRead(uint64_t cycle, const Options &options) {
  std::cout << kInterCmdHead << " READ " << cycle << " " << options.ssdX
            << " " << options.ssdY << " " << options.npuX << " "
            << options.npuY << " " << options.requestBytes << " 0"
            << std::endl;
}

void emitResult(const std::vector<std::string> &items) {
  std::cout << kInterCmdHead << " RESULT " << items.size();

  for (auto &item : items) {
    std::cout << " " << item;
  }

  std::cout << std::endl;
}

bool parseSyncLine(const std::string &line, uint64_t &cycle) {
  std::string message = line;

  if (message.compare(0, sizeof(kInterCmdHead) - 1, kInterCmdHead) == 0) {
    message = message.substr(sizeof(kInterCmdHead));
  }

  std::stringstream ss(message);
  std::string type;

  ss >> type;
  if (type != "SYNC") {
    return false;
  }

  ss >> cycle;

  return !!ss;
}

bool waitForSync(uint64_t &cycle) {
  std::string line;

  while (std::getline(std::cin, line)) {
    if (line.empty()) {
      continue;
    }

    if (parseSyncLine(line, cycle)) {
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

  uint64_t currentCycle = options.startCycle;

  for (uint64_t i = 0; i < options.iterations; i++) {
    uint64_t requestDone = 0;
    uint64_t responseDone = 0;

    emitWrite(currentCycle, options);

    if (!waitForSync(requestDone)) {
      std::cerr << "Failed to receive request SYNC." << std::endl;
      return 2;
    }

    emitRead(requestDone, options);

    if (!waitForSync(responseDone)) {
      std::cerr << "Failed to receive response SYNC." << std::endl;
      return 3;
    }

    currentCycle = responseDone;
  }

  emitResult({"requests", std::to_string(options.iterations), "last_cycle",
              std::to_string(currentCycle)});

  return 0;
}
