#pragma once

#include <cstdint>
#include <deque>
#include <queue>
#include <string>

#include "Dram.h"

class DramLegoSim : public Dram {
 public:
  DramLegoSim(SimulationConfig config, cycle_type* core_cycle);

  bool running() override;
  void cycle() override;
  void cache_cycle() override;
  bool is_full(uint32_t cid, mem_fetch* request) override;
  void push(uint32_t cid, mem_fetch* request) override;
  bool is_empty(uint32_t cid) override;
  mem_fetch* top(uint32_t cid) override;
  void pop(uint32_t cid) override;
  void print_stat() override;
  void print_cache_stats() override;

 private:
  enum class PendingStage {
    REQUEST_IN_FLIGHT,
    RESPONSE_IN_FLIGHT,
  };

  struct PendingRequest {
    uint64_t request_id = 0;
    uint32_t cid = 0;
    // Wire size of the request/announce leg (WRITE, NPU->SSD). Equals
    // data_bytes except for reads when kEnableReadCommandShrink is set, in
    // which case it is the small fixed-size command (see DramLegoSim.cc).
    uint64_t command_bytes = 0;
    // Wire size of the response/data leg (READ, SSD->NPU). Always the real
    // request size in bytes.
    uint64_t data_bytes = 0;
    long desc = 0;
    cycle_type issue_cycle = 0;
    cycle_type arrival_cycle = 0;
    mem_fetch* request = nullptr;
    PendingStage stage = PendingStage::REQUEST_IN_FLIGHT;
  };

  cycle_type current_cycle() const;
  bool read_line(std::string& line);
  bool parse_sync(const std::string& line, cycle_type& sync_cycle, long& desc,
                  bool& has_desc) const;
  void handle_sync(cycle_type sync_cycle, long desc, bool has_desc);
  void emit_request_write(const PendingRequest& pending, cycle_type cycle);
  void emit_response_read(const PendingRequest& pending, cycle_type cycle);

  std::deque<PendingRequest> _request_inflight;
  std::deque<PendingRequest> _response_inflight;
  uint64_t _issued_reads = 0;
  uint64_t _issued_writes = 0;
  uint64_t _completed_reads = 0;
  uint64_t _completed_writes = 0;
  std::string _stdin_buffer;
};
