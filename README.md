LLM Inference Bottleneck Analysis on UCIe-Connected Flash Systems

1. End Goal

Evaluate LLM inference workloads — including dense, sparse, and MoE models — on two NPU–Flash architectures, identify where and why each stage becomes bottlenecked, and use those results to determine what architectural changes are actually necessary.

The goal is therefore not simply:

Run an LLM → measure performance.

Instead:

Build system → characterize bottlenecks → verify bottlenecks → explain LLM behavior → propose architectural solutions.

⸻

2. Target Architectures

Architecture 1 — NPU → SSD via UCIe

My responsibility
```txt
            UCIe
┌─────┐  ─────────►  ┌────────────── SSD ──────────────┐
│ NPU │              │                                  │
└─────┘              │ Controller                       │
                     │     │                            │
                     │     ├── Flash Channel 0 ── NAND  │
                     │     ├── Flash Channel 1 ── NAND  │
                     │     ├── ...                      │
                     │     └── Flash Channel N ── NAND  │
                     └──────────────────────────────────┘
```
The NPU accesses the entire SSD through a single external UCIe link.

Potential bottlenecks include:

* External: NPU ↔ SSD UCIe link
* Internal: SSD controller ↔ aggregated flash channels
* Device: NAND read latency (tR)

⸻

Architecture 2 — NPU → Flash Channels via UCIe

Sammy’s responsibility
```text
                     ┌── UCIe ── Flash Channel 0
                     │
┌─────┐              ├── UCIe ── Flash Channel 1
│ NPU │──────────────┼── ...
└─────┘              │
                     └── UCIe ── Flash Channel N
```
The SSD-level shared path is flattened.

N flash channels → N UCIe links.

This architecture is important because it provides an alternative when Architecture 1 is fundamentally limited by its shared external/internal communication path.

⸻

3. Why Running the LLM Alone Is Not Enough

Suppose we run an LLM and observe that one operation is slow.

That result alone does not tell us:

* which resource is saturated;
* whether the bottleneck is caused by bandwidth, serialization, or NAND latency;
* whether the behavior is expected;
* whether changing the architecture would actually solve it.

Therefore, the LLM workload should not be the first experiment.

We first need controlled microbenchmarks that deliberately stress individual parts of the system.

⸻

4. Phase I — Build the Simulation Platform

Objective

Connect the existing NPU simulator and SSD simulator through a well-defined interconnect simulator.

NPU Simulator
     │
     ▼
Interconnect Simulator
     │
     ▼
SSD Simulator
     │
     ▼
Flash Channels / NAND

The simulator must expose enough statistics to separately observe:

NPU
 │
 │ ① External-link delay / utilization
 ▼
SSD
 │
 │ ② Internal aggregated-channel delay / utilization
 ▼
Flash
 │
 │ ③ NAND read latency / tR
 ▼
Data

Deliverable

A working end-to-end simulation path:

NPU → Interconnect → SSD → NAND → NPU

with measurable latency/bandwidth/utilization at each boundary.

⸻

5. Phase II — Bottleneck Characterization

Before running full LLM workloads, construct controlled test cases that deliberately create known bottlenecks.

Test A — External-Link-Bound

Target: NPU ↔ SSD UCIe link

Generate sufficient traffic so that the external UCIe connection becomes the limiting resource.

Expected signature:

Increasing downstream SSD/Flash capability no longer improves performance because the UCIe link is saturated.

⸻

Test B — Internal-Channel-Bound

Target: SSD ↔ aggregated Flash channels

Provide enough external bandwidth while generating enough concurrent Flash accesses to saturate the SSD’s internal Flash-channel bandwidth.

Expected signature:

External UCIe bandwidth remains available, but increasing Flash-channel capability improves performance.

⸻

Test C — NAND-Read-Bound

Target: NAND tR

Reduce communication bottlenecks sufficiently that Flash read latency dominates.

Expected signature:

Neither additional UCIe bandwidth nor additional channel bandwidth significantly improves performance; NAND read latency becomes dominant.

⸻

6. Phase III — Run LLM Workloads

After establishing the bottleneck signatures, run:

* Dense LLM
* Sparse LLM
* MoE LLM

Break inference into meaningful operation/stages rather than reporting only end-to-end latency.

For each operation, determine:

LLM Operation
      │
      ▼
Where is time spent?
      │
      ├── NPU ↔ SSD UCIe
      ├── SSD ↔ Flash channels
      └── NAND tR

The output should therefore look conceptually like:

LLM Stage / Operation	Observed Bottleneck	Evidence
Operation A	NPU–SSD link	Matches external-link microbenchmark
Operation B	Flash channels	Matches internal-channel microbenchmark
Operation C	NAND tR	Matches NAND-latency microbenchmark

The important point is that bottleneck identification is supported by previously characterized system behavior, rather than inferred only from one LLM run.

⸻

7. Phase IV — Verify and Explain

For every identified LLM bottleneck, answer two separate questions:

Q1. Is this actually the bottleneck?

Verify it by changing the corresponding resource.

For example:

Suspect UCIe bottleneck
        ↓
Increase UCIe bandwidth
        ↓
Does operation latency decrease?

If yes, the causal relationship is strengthened.

Q2. Why does this LLM operation hit this resource?

Relate the operation’s:

* data movement,
* access pattern,
* parallelism,
* Flash traffic,

to the bottleneck signatures established in Phase II.

Thus:

Observation → Controlled verification → Architectural explanation

⸻

8. Phase V — Solve the Bottleneck

Once the bottleneck is identified and verified, determine which architectural change addresses it.

Case 1 — Shared UCIe / SSD Path Is the Bottleneck

If Architecture 1 remains communication-bound even with UCIe:

NPU
 │
 UCIe   ← bottleneck
 │
SSD

then simply replacing the existing external interface with UCIe is insufficient.

This motivates evaluating Architecture 2:

              ┌─ UCIe → Channel 0
NPU ──────────┼─ UCIe → Channel 1
              ├─ ...
              └─ UCIe → Channel N

The question becomes:

Does flattening Flash-channel access remove the shared-path bottleneck?

⸻

Case 2 — Flash Channel / NAND Becomes the Bottleneck

If communication is no longer dominant and the bottleneck moves into Flash:

NPU ── UCIe ── SSD ── Flash
                         ↑
                     bottleneck

then additional host-side bandwidth provides diminishing benefit.

This motivates in-Flash / near-Flash processing techniques to reduce data movement or exploit computation closer to the data.

⸻

9. Overall Experimental Logic

[1] Build Simulator
        │
        ▼
NPU + Interconnect + SSD
        │
        ▼
[2] Controlled Microbenchmarks
        │
        ├── External-link-bound
        ├── Internal-channel-bound
        └── NAND-tR-bound
        │
        ▼
[3] Establish Bottleneck Signatures
        │
        ▼
[4] Run LLM Workloads
Dense / Sparse / MoE
        │
        ▼
[5] Break Down Each Operation
        │
        ▼
[6] Identify Bottleneck
        │
        ▼
[7] Verify Against Controlled Tests
        │
        ▼
[8] Explain Why It Occurs
        │
        ▼
[9] Architectural Response
        │
        ├── Shared path bottleneck
        │       → Architecture 2
        │
        └── Flash bottleneck
                → Flash processing

⸻

Current Status

NOW: Phase I — Simulation Platform Integration

Current objective:

Connect the NPU simulator and SSD simulator through a well-defined interconnect simulator.

Immediate Tasks

* Define the NPU ↔ interconnect interface
* Define the interconnect ↔ SSD interface
* Determine request/response format
* Determine timing model
* Determine UCIe bandwidth/latency parameters
* Expose external-link statistics
* Expose SSD internal-channel statistics
* Expose NAND tR / device-level statistics
* Verify end-to-end NPU → SSD → NAND requests

NEXT: Phase II — Design Microbenchmarks

Once the simulator works, my next responsibility is to construct test cases that deliberately attack:

1. NPU ↔ SSD external UCIe bandwidth
2. SSD ↔ Flash aggregated internal bandwidth
3. NAND read latency (tR)

These tests will form the reference points needed to interpret the later LLM experiments.

⸻

One-Sentence Research Logic

Characterize the system first, use those signatures to explain where individual LLM operations bottleneck, verify the bottlenecks experimentally, and then determine whether the solution requires flattened channel access or computation closer to Flash.