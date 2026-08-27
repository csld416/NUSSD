#include "DramLegoSim.h"

#include <poll.h>
#include <unistd.h>

#include <cerrno>
#include <algorithm>
#include <iostream>
#include <sstream>
#include <stdexcept>

#include <spdlog/spdlog.h>

namespace {

constexpr const char* kInterCmdHead = "[INTERCMD]";

// --- Read-path command/data leg split -----------------------------------
// Baseline behavior (matches every measurement in LOG.md through
// 2026-08-27): both the request leg (WRITE, NPU->SSD) and the response leg
// (READ, SSD->NPU) declare the full request size in bytes, regardless of
// whether the underlying op is a load or a store. That does not match a
// real NVMe/UCIe protocol, where a read's *request* is a small fixed-size
// command (LBA + length) and only the *response* carries the data payload.
//
// When kEnableReadCommandShrink is true, DramLegoSim::push() uses
// command_bytes = kReadCmdBytes on the request leg for reads only, while
// data_bytes (the response leg) stays the real request size. The write
// path is intentionally left untouched -- see LOG.md, 2026-08-27 entry.
//
// Set kEnableReadCommandShrink = false to restore the original
// single-size-both-legs baseline without touching any other logic.
//
// IMPORTANT: kReadCmdBytes here MUST be numerically identical to the
// constant of the same name in
// SimpleSSD-Standalone/sim/legosim_main.cc. LegoSim's coordinator
// (interchiplet/includes/cmd_handler.h: hasMatchWrite/hasMatchRead)
// requires the WRITE and READ legs of a pair to declare the exact same
// nbytes, or the two simlets hang waiting for a SYNC that never arrives.
constexpr bool kEnableReadCommandShrink = true;
constexpr uint64_t kReadCmdBytes = 64;  // e.g. an NVMe read command (LBA + length)

}  // namespace

DramLegoSim::DramLegoSim(SimulationConfig config, cycle_type* core_cycle)
    : Dram(config, core_cycle) {
  _cycles = 0;
  spdlog::info("[DramLegoSim] NPU ({},{}) <-> SSD ({},{}), descriptor {}, max pending {}",
               _config.legosim_npu_x, _config.legosim_npu_y,
               _config.legosim_ssd_x, _config.legosim_ssd_y,
               _config.legosim_desc, _config.legosim_max_pending);
}

bool DramLegoSim::running() {
  if (!_request_inflight.empty() || !_response_inflight.empty())
    return true;
  for (uint32_t ch = 0; ch < _n_ch; ch++) {
    if (!m_to_crossbar_queue[ch].empty())
      return true;
  }
  return false;
}

void DramLegoSim::cycle() {
  _cycles++;

  std::string line;
  while (read_line(line)) {
    cycle_type sync_cycle = 0;
    long desc = 0;
    bool has_desc = false;
    if (!parse_sync(line, sync_cycle, desc, has_desc)) {
      spdlog::debug("[DramLegoSim] Ignoring non-SYNC stdin line: {}", line);
      continue;
    }
    handle_sync(sync_cycle, desc, has_desc);
  }
}

void DramLegoSim::cache_cycle() {}

bool DramLegoSim::is_full(uint32_t, mem_fetch*) {
  return _config.legosim_max_pending != 0 &&
         _request_inflight.size() + _response_inflight.size() >=
             static_cast<size_t>(_config.legosim_max_pending);
}

void DramLegoSim::push(uint32_t cid, mem_fetch* request) {
  if (request == nullptr)
    throw std::runtime_error("[DramLegoSim] null mem_fetch");
  if (cid >= _n_ch)
    throw std::runtime_error("[DramLegoSim] channel id out of range");
  if (is_full(cid, request))
    throw std::runtime_error("[DramLegoSim] pending queue is full");

  const cycle_type now = current_cycle();
  const uint64_t nbytes = std::max<uint64_t>(1, request->get_data_size());
  const bool is_write = request->is_write();

  request->request_cycle = now;
  request->current_state = "LEGOSIM_REQUEST";

  PendingRequest pending;
  pending.request_id = request->get_request_id();
  pending.cid = cid;
  pending.data_bytes = nbytes;
  pending.command_bytes =
      (kEnableReadCommandShrink && !is_write) ? kReadCmdBytes : nbytes;
  pending.desc =
      _config.legosim_desc + static_cast<long>((request->get_request_id() + 1) * 8);
  pending.issue_cycle = now;
  pending.request = request;
  pending.stage = PendingStage::REQUEST_IN_FLIGHT;

  if (is_write)
    _issued_writes++;
  else
    _issued_reads++;

  _request_inflight.push_back(pending);
  emit_request_write(pending, now);
}

bool DramLegoSim::is_empty(uint32_t cid) {
  return m_to_crossbar_queue[cid].empty();
}

mem_fetch* DramLegoSim::top(uint32_t cid) {
  assert(!is_empty(cid));
  return m_to_crossbar_queue[cid].front();
}

void DramLegoSim::pop(uint32_t cid) {
  assert(!is_empty(cid));
  m_to_crossbar_queue[cid].pop();
}

void DramLegoSim::print_stat() {
  spdlog::info("[DramLegoSim] issued reads {}, issued writes {}, completed reads {}, completed writes {}, pending {}",
               _issued_reads, _issued_writes, _completed_reads, _completed_writes,
               _request_inflight.size() + _response_inflight.size());
}

void DramLegoSim::print_cache_stats() {}

cycle_type DramLegoSim::current_cycle() const {
  return _core_cycles != nullptr ? *_core_cycles : _cycles;
}

bool DramLegoSim::read_line(std::string& line) {
  std::string::size_type newline = _stdin_buffer.find('\n');
  if (newline != std::string::npos) {
    line = _stdin_buffer.substr(0, newline);
    _stdin_buffer.erase(0, newline + 1);
    return true;
  }

  pollfd pfd;
  pfd.fd = STDIN_FILENO;
  pfd.events = POLLIN;
  pfd.revents = 0;

  const int ready = poll(&pfd, 1, 0);
  if (ready <= 0 || (pfd.revents & (POLLIN | POLLHUP)) == 0)
    return false;

  char buffer[4096];
  const ssize_t nread = ::read(STDIN_FILENO, buffer, sizeof(buffer));
  if (nread < 0) {
    if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)
      return false;
    return false;
  }
  if (nread == 0)
    return false;

  _stdin_buffer.append(buffer, static_cast<size_t>(nread));
  newline = _stdin_buffer.find('\n');
  if (newline == std::string::npos)
    return false;

  line = _stdin_buffer.substr(0, newline);
  _stdin_buffer.erase(0, newline + 1);
  return true;
}

bool DramLegoSim::parse_sync(const std::string& line, cycle_type& sync_cycle,
                             long& desc, bool& has_desc) const {
  std::string message = line;
  if (message.compare(0, std::char_traits<char>::length(kInterCmdHead), kInterCmdHead) == 0) {
    message = message.substr(std::char_traits<char>::length(kInterCmdHead));
  }

  std::stringstream ss(message);
  std::string type;
  ss >> type;
  if (type != "SYNC")
    return false;

  ss >> sync_cycle;
  if (!ss)
    return false;

  if (ss >> desc) {
    has_desc = true;
  }
  else {
    desc = 0;
    has_desc = false;
  }

  return true;
}

void DramLegoSim::handle_sync(cycle_type sync_cycle, long desc, bool has_desc) {
  auto request_iter = _request_inflight.end();
  if (has_desc) {
    request_iter = std::find_if(_request_inflight.begin(), _request_inflight.end(),
                                [desc](const PendingRequest& pending) {
                                  return pending.desc == desc;
                                });
  }
  else if (!_request_inflight.empty()) {
    request_iter = _request_inflight.begin();
  }

  if (request_iter != _request_inflight.end()) {
    PendingRequest pending = *request_iter;
    _request_inflight.erase(request_iter);
    pending.arrival_cycle = sync_cycle;
    pending.stage = PendingStage::RESPONSE_IN_FLIGHT;
    pending.request->current_state = "LEGOSIM_FLASH";
    emit_response_read(pending, sync_cycle);
    _response_inflight.push_back(pending);
    return;
  }

  auto response_iter = _response_inflight.end();
  if (has_desc) {
    response_iter = std::find_if(_response_inflight.begin(), _response_inflight.end(),
                                 [desc](const PendingRequest& pending) {
                                   return pending.desc == desc;
                                 });
  }
  else if (!_response_inflight.empty()) {
    response_iter = _response_inflight.begin();
  }

  if (response_iter == _response_inflight.end()) {
    spdlog::warn("[DramLegoSim] Received SYNC {} with no pending request", sync_cycle);
    return;
  }

  PendingRequest pending = *response_iter;
  _response_inflight.erase(response_iter);

  pending.request->response_cycle = sync_cycle;
  pending.request->current_state = "LEGOSIM_REPLY";
  const bool was_write = pending.request->is_write();
  if (pending.request->is_request())
    pending.request->set_reply();
  if (was_write)
    _completed_writes++;
  else
    _completed_reads++;
  m_to_crossbar_queue[pending.cid].push(pending.request);
}

void DramLegoSim::emit_request_write(const PendingRequest& pending, cycle_type cycle) {
  std::cout << std::endl
            << kInterCmdHead << " WRITE " << cycle << " "
            << _config.legosim_npu_x << " " << _config.legosim_npu_y << " "
            << _config.legosim_ssd_x << " " << _config.legosim_ssd_y << " "
            << pending.command_bytes << " " << pending.desc << std::endl;
}

void DramLegoSim::emit_response_read(const PendingRequest& pending, cycle_type cycle) {
  std::cout << std::endl
            << kInterCmdHead << " READ " << cycle << " "
            << _config.legosim_ssd_x << " " << _config.legosim_ssd_y << " "
            << _config.legosim_npu_x << " " << _config.legosim_npu_y << " "
            << pending.data_bytes << " " << pending.desc << std::endl;
}
