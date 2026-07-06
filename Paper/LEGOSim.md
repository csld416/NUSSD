## **LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration** 

## Xiaohang Wang[†] 

## Cheng Qiu[∗] 

## Tiantian Lin[∗] 

The State Key Laboratory of Blockchain and Data Security, Zhejiang University and Hangzhou High-Tech Zone (Binjiang), Institute of Blockchain and Data Security Hangzhou, China 12421257@zju.edu.cn 

South China University of Technology Guangzhou, China 15112585363@163.com 

The State Key Laboratory of Blockchain and Data Security, Zhejiang University and Hangzhou High-Tech Zone (Binjiang), Institute of Blockchain and Data Security Hangzhou, China xiaohangwang@zju.edu.cn 

## Ling Wang[†] 

## Zhulin Zheng 

## Yingtao Jiang 

The University of Western Australia Western Australia, Australia ling.wang@uwa.edu.au 

The State Key Laboratory of Blockchain and Data Security, Zhejiang University and Hangzhou High-Tech Zone (Binjiang), Institute of Blockchain and Data Security Hangzhou, China hziee_zzl@163.com 

University of Nevada, Las Vegas Las Vegas, USA yingtao.jiang@unlv.edu 

## Sihai Qiu 

## Amit Kumar Singh 

## Jieming Yin 

Beijing Smart-chip Microelectronics Technology Co., Ltd, Beijing, China qiusihai@sgchip.sgcc.com.cn 

Nanjing University of Posts and Telecommunications Nanjing, China jieming.yin@njupt.edu.cn 

University of Essex Essex, United Kingdom a.k.singh@essex.ac.uk 

Xiaodong Li Ant Group Beijing, China fanxiao.lxd@antgroup.com 

Jie Song Ant Group Beijing, China charlie.sj@antgroup.com 

Xin Tang Ant Group Beijing, China zhizhong.tx@antgroup.com 

## Mingzhe Zhang 

## Kui Ren 

The State Key Laboratory of Blockchain and Data Security, Zhejiang University and Hangzhou High-Tech Zone (Binjiang), Institute of Blockchain and Data Security Hangzhou, China kuiren@zju.edu.cn 

Ant Group Beijing, China huayi.zmz@antgroup.com 

## **Abstract** 

> ∗Both authors contributed equally to this research 

†Corresponding authors 

Permission to make digital or hard copies of all or part of this work for personal or classroom use is granted without fee provided that copies are not made or distributed for profit or commercial advantage and that copies bear this notice and the full citation on the first page. Copyrights for components of this work owned by others than the author(s) must be honored. Abstracting with credit is permitted. To copy otherwise, or republish, to post on servers or to redistribute to lists, requires prior specific permission and/or a fee. Request permissions from permissions@acm.org. _MICRO ’25, Seoul, Republic of Korea_ 

© 2025 Copyright held by the owner/author(s). Publication rights licensed to ACM. ACM ISBN 979-8-4007-1573-0/25/10 https://doi.org/10.1145/3725843.3756068 

The rise of multi-chiplet integration challenges existing simulators like gem5 [55] and GPGPU-Sim [45] for efficiently simulating heterogeneous multiple-chiplet systems due to incapability to modularly integrate heterogeneous chiplets and high synchronization overheads in parallel simulation. To address these limitations, this paper introduces LEGOSim, a unified parallel simulation framework capable of flexibly integrating various open-source and in-house designed chiplet simulators as processes in parallel simulation, referred to as "simlets" with minimal modifications needed. It introduces an on-demand synchronization protocol with adaptive 

1347 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

time quanta and non-global fencing, ensuring synchronization only occurs when necessary, thus reducing overhead while maintaining correctness. The framework also integrates Network-on-Interposer (NoI) simulator for modeling inter-chiplet communication, enabling accurate assessment of various interconnection architectures’ performance. Evaluated with diverse benchmarks, LEGOSim shows high accuracy in simulating multi-chiplet architectures like SIMBA [69] and a CiM-based accelerator [14], with average errors of 3.79% and 3.94%, respectively. It significantly reduces synchronization overhead by up to 99.9% compared to per-cycle synchronization and by 66.1% compared to time quantum synchronization, without synchronization errors. Five case studies show that LEGOSim also provides precise system performance metrics and stall cause reporting, simplifying tasks such as performance analysis and optimization, and can be used for design space exploration of various multi-chiplet systems. 

incurs huge synchronization overhead, while time quantum improves speed by relaxing the synchronization to be performed for each time quantum and but degrades accuracy. 

To address these challenges, we propose LEGOSim, a unified parallel simulation framework for heterogeneous multi-chiplet systems, which is released in [7]. The accuracy of LEGOSim has been validated with two published works, SIMBA [69] and a compute-inmemory (CiM) based accelerator architecture [14]. The simulation errors are below 10%, confirming its fidelity. 

LEGOSim is showcased by five case studies to help explore the design space in multi-chiplet system design flows, including identifying performance bottlenecks, and design space exploration for inter-chiplet interconnection network and buffer size, inter-chiplet network topology selection, memory interfaces, and inter-chiplet interconnection protocols, demonstrating the versatility of LEGOSim in multi-chiplet system design flows. 

The contributions of this paper are as follows: 

## **Keywords** 

Architectural simulation, multi-chiplet system simulation. 

## **ACM Reference Format:** 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, and Kui Ren. 2025. LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration. In _58th IEEE/ACM International Symposium on Microarchitecture (MICRO ’25), October 18–22, 2025, Seoul, Republic of Korea._ ACM, New York, NY, USA, 16 pages. https://doi.org/10.1145/3725843.3756068 

## **1 Introduction** 

As semiconductor technology approaches its physical limits, multichiplet integration has become an essential design paradigm for the post-Moore era. Compared to traditional monolithic chip architectures, multi-chiplet systems package multiple heterogeneous chiplets (such as CPUs, GPUs, NPUs, CiMs, etc.) into a single system, which not only enhances computational performance but also optimizes power consumption, reduces costs, and improves chip yield. However, these highly integrated architectures also bring unprecedented challenges in design space exploration, especially in terms of the system-level simulation and evaluation. 

The challenges of architectural level multi-chiplet system simulation include: 

**1. Lack of modular integration flexibility:** Numerous simulators have been developed to simulate individual components/chiplets such as CPUs, GPUs, and NoIs [2]- [83], as shown in Table 1. While these simulators are highly detailed and accurate for their specific targets, they lack the flexibility to be integrated into multi-chiplet systems as they are not designed for modular integration. Existing works[60] used gem5 to simulate multi-chiplet system, which incurs scalability issue. Modular simulators, like SimBricks [49] or SST [63], cannot model the Network-on-Interposer(NoI), and also cannot support flexibly integrating various simlets. 

**2. Synchronization inefficiency:** To overcome the slow simulation speed problem of sequential simulation, parallel simulation with per-cycle synchronization [24] and time quantum synchronization [24] were proposed. However, per-cycle synchronization 

- We propose an **on-demand synchronization scheme** that triggers synchronization only during inter-chiplet communication, reducing overhead by 99.9% compared to per-cycle synchronization while preserving accuracy. 

- We propose a **detailed NoI modeling** that refines interchiplet communication latency, improving communication modeling efficiency and accuracy. A detailed NoI model is integrated to simulate various NoI network architectures. 

- We propose a **Unified Integration Interface (UII)** to enable seamless integration of diverse simulators (e.g., gem5, Sniper, GPGPU-Sim) into LEGOSim with parallel simulation and minimal code changes. 

- We have **implemented and open-sourced LEGOSim** in [7] with detailed configurations and usage documentation, integrating multiple simlets, and invite researchers to contribute to design space exploration for multi-chiplet systems with LEGOSim. 

## **2 Background & Motivation** 

## **2.1 Limitations of Existing Simulators in Modular Integration** 

In recent years, multi-chiplet architectures have been widely adopted in high-performance computing (HPC) and AI chips due to their superior scalability and energy efficiency. Notable examples include AMD’s Zen 5 [10] with modular CCD/IOD design, supporting 32-64 cores and delivering over 2 TFLOPS of computing power. However, the design space exploration for such systems remains highly challenging due to the vast configuration space and complex interdependencies across interconnects, memory hierarchies, and communication protocols. For instance, Intel’s Ponte Vecchio [34] integrates 47 chiplets and over 100 billion transistors, with a design cycle of a few years [5]. 

The limitations of existing simulators—especially their inability to support modular integration and high synchronization overhead— exacerbates low efficiency in design space exploration. Numerous simulators have been developed to simulate individual components/chiplets such as CPUs, GPUs, and NoIs [2]- [83], as tabulated in Table 1, which unfortunately lack the flexibility to be 

1348 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

**Table 1: Summation of existing simulators.** 

|Simulator|Target|Simulator|Target|Simulator|Target|Simulator|Target|
|---|---|---|---|---|---|---|---|
|SimBricks [49]|CPU|gem5 [55]|CPU/GPU|ROCm [40]|GPU|SimpleSSD [36]|SSD|
|Sniper [30]|CPU|MacSim [42]|CPU|Arbitor [33]|AI Acc|SSDExplorer [83]|SSD|
|ZSim [67]|CPU|Manifold [75]|GPU|NeuroSim [18]|AI Acc|BookSim [35]|NoC|
|GPGPU-Sim [45]|CPU/GPU|MGPU-sim [72]|GPU|Scale-Sim [66]|AI Acc|Garnet [9]|NoC|
|Graphite [56]|CPU/GPU|Nsight Compute [48]|GPU|MNSIM 2.0 [82]|CiM|Noxim [17]|NoC|
|Multi2Sim [73]|CPU/GPU|Nsight Systems [48]|GPU|DRAMsim3 [51]|DRAM|Ns-3 [16]|NoC|
|Accel-Sim [38]|GPU|PPT-GPU [11]|GPU|Ramulator [44]|DRAM|OMNeT++ [74]|NoC|
|SimpleScalar [12]|CPU/GPU|HRaid [19]|Storage Devices|FlashSim [43]|Storage Devices|Dinero IV [23]|Cache|
|SST [63]|CPU|PIMSim [78]|PIM|Neupims [31]|PIM|CacheSim [53]|Cache|
|Beignet[32]|GPU|OpenVINO Toolkit[2]|GPU|MQSim-E[46]|SSD|**LEGOSim**|**CPU+GPU+NPU+...**|



Note: AI Acc stands for AI accelerator and CiM stands for compute-in-memory. 

**==> picture [504 x 125] intentionally omitted <==**

**----- Start of picture text -----**<br>
Synchronization Overhead<br>Simlet ID Simlet ID Simlet ID<br>Simlet 1 cycle 0 cycle 1 cycle 2 Simlet 1 cycle 0~ n -1 cycle  n ~2 n -1 Simlet 1 cycle 0~ x<br>Simlet 2 0 1 2 ... Simlet 2 0~ n -1 n ~2 n -1 ... Simlet 2 0~ x ...<br>No synchronization @ x<br>Simlet 3 0 1 2 Simlet 3 0~ n -1 n ~2 n -1 Simlet 3 0~ y<br>t t t<br>(a) per-cycle synchronization (b) time quantum synchronization (c) on-demand synchronization<br>**----- End of picture text -----**<br>


**Figure 1: Comparison of different synchronization mechanisms.** 

integrated to simulate heterogenous multi-chiplet systems. Modular simulators aim to integrate various components into a unified framework. For example, SimBricks [49] can integrate multiple simulators, but its complex integration mechanism results in low simulation speed, and it cannot model inter-chiplet transmission. ZSim [67] can efficiently simulate large-scale systems, but it has accuracy issues in simulating multi-chiplet interconnection networks. In addition, gem5-X [59] and its extended series (e.g., gem5-GPU [58], gem5-AcceSys [54], gem5-SALAM [64], etc.) also attempt to provide integration of CPUs, GPUs, memory models, and accelerators. However, these integrations require deep internal modification of the simulators, and they are fixed architectures, instead of modular integration of many other system architectures. SST (Structural Simulation Toolkit [63]) is another modular framework that supports integration across different simulation models and allows component plug-ins. However, SST cannot model inter-chiplet communication network and has significant simulation overhead and complexity, and also needs significant code modification to existing simulators. 

## **2.2 Limitations of Existing Parallel Simulation Synchronization Schemes** 

In sequential simulation (e.g., gem5), the simulation of each simlet (i.e., the simulation module of an individual chiplet) and Networkon-Interposer (NoI) simulation is performed sequentially, resulting in low utilization of computing resources. The execution of sequential simulation, where the execution of simlets and NoI is strictly sequential with no overlap, significantly limits the simulation efficiency. Moreover, as the system size scales up, the simulation 

time grows exponentially as more events need to be simulated. For example, with gem5 simulating one second of a many-core system takes 1 and 10 weeks [20], making sequential simulation impractical for large-scale multi-chiplet systems. Parallel simulation improves efficiency compared to sequential simulation. However, synchronization overhead remains a bottleneck in parallel simulation, particularly for large-scale multi-chiplet systems or wafer scale architectures. Traditional synchronization methods, such as per-cycle synchronization [24] and time quantum synchronization [24] struggle to balance simulation efficiency and accuracy at scale. 

**1) Per-cycle synchronization (Figure 1a).** Per-cycle (PC) synchronized parallel simulation (e.g., parti-gem5 [20]) allows the simulation of multiple simlets in parallel, while overlapping with the simulation of the NoI. However, synchronization at each simulation cycle introduces significant overhead. As shown in Figure 2, the synchronization overhead increases drastically with the number of cores. For example, in a 32-core system, synchronization consumes up to 85% of the total simulation time, making per-cycle synchronization infeasible for large-scale systems. 

**2) Time quantum synchronization (Figure 1b).** To mitigate the synchronization overhead in per-cycle synchronization, the Time Quantum (TQ) approach reduces synchronization frequency by grouping events into fixed time windows (such as adopted by Astra-Sim [61], SimAI [76], SlackSim [65], WWT [62] and Zsim [67]). However, the accuracy of TQ synchronization is highly sensitive to the time window size ( _x_ ). A large time window masks short-period cross-chiplet events (e.g., inter-chiplet data transmission or synchronization for the benchmark/application threads), 

1349 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

causing important interactions to be delayed or ignored and leading to timing errors and low accuracy. On the other hand, small time windows increase synchronization frequency and effectively degrade to near per-cycle synchronization, resulting in poor scalability. Although the optimal quantum lengths can be predicted using machine learning, as the case in **SimAI** [76] , they are heavily dependent on training data quality, while **Astra-Sim** [61] focuses on network modeling and is less suited for tightly coupled multisimlet interactions. **SlackSim** [65] further relaxes synchronization to improve simulation speed, albeit at the potential cost of simulation accuracy. **WWT** [62] attempts to group operations within time windows but lacks fine-grained adaptability across workloads. 

**==> picture [195 x 156] intentionally omitted <==**

**----- Start of picture text -----**<br>
R/W Request<br>—<br>Simlet n<br>Permission<br>ee<br>Benchmark<br>Simlet 1 ... | 4 ... Simlet 2<br>UII<br>Benchmark Benchmark<br>| 4<br>Global<br>UII Manager UII<br>Traffic Traces Communication Delay<br>NoI<br>simulator<br>**----- End of picture text -----**<br>


**==> picture [263 x 109] intentionally omitted <==**

**----- Start of picture text -----**<br>
8 cores 16 cores 32 cores<br>1.00<br>0.75 40<br>0.50<br>20<br>0.25<br>0.00 0<br>= Simlet Time | Sync Time i | NoI Time — Error Rate<br>TQ-2TQ-10 1 02 1 03 TQ-2TQ-10 1 02 1 03 TQ-2TQ-10 102 103<br>Per-cycle T Q T Q Per-cycle T Q T Q Per-cycle TQ TQ<br>Sequential Sequential Sequential<br>Error Rate (%)<br>Norm. simulation time<br>**----- End of picture text -----**<br>


**Figure 2: Comparison of overheads of different synchronization methods. Error is computed with respect to the sequential simulation. The simulation time is normalized to that of sequential simulation with 32 cores.** 

Our experiments (Figure 2) evaluated these synchronization schemes on 8-, 16-, and 32-core configurations using parti-gem5 [20] for parallel simulation, modified to support both per-cycle synchronization and TQ- _𝑥_ synchronization. As the number of cores increases, both sequential simulation and per-cycle simulation becomes impractical. While TQ synchronization reduces overhead, for instance _𝑇𝑄_ − 10[3] cuts synchronization overhead by 99.9% compared to per-cycle synchronization, it introduces 56% timing error in the 32-core case, making it unsuitable for accuracy-critical studies. 

To address the above challenges, we propose **on-demand (OD) synchronization** , which has two key features: 

1) adaptive and accurate time quantum, where the synchronization only occurs when there are inter-chiplet communications, and 2) non-global fencing, where only the communication chiplets/simlets are involved in synchronization instead of stalling all the simlets. As shown in Figure 1c, consider simlets 1–3, if simlets 1, 2, and 3 have no communication prior to cycle _x_ , there will be no need to synchronize. Only when simlets 1 and 2 communicate at cycle _x_ , only they synchronize. Simlet 3, which has no communication dependency, continues uninterrupted. This avoids global stalling and significantly reduces synchronization overhead without compromising accuracy. 

**Figure 3: Overview of LEGOSim architecture and its components.** 

## **3 LEGOSim Architecture and Design Principles 3.1 Overview of LEGOSim** 

LEGOSim supports parallel simulation and breaks down the simulation of a multi-chiplet system into the following three components, as shown in Figure 3: 

1) **Heterogeneous Chiplet Simulation Units (Simlets)** : Different simlets (CPUs, GPUs, NPUs, CiMs, etc.) are independent simulation processes in parallel simulation, each of which can be existing open-source simulators (e.g., gem5 [55] or Sniper [30] ~~for CPU chiplets, GPGPU-Sim [45] for GPU chiplets, MNSIM [82]~~ for compute-in-memory chiplets, etc.). Simlets interact with each other through a Unified Integration Interface (UII), which will be described in Section 4. 

2) **Network-on-Interposer (NoI) Simulator** : Used for modeling the interconnection topologies of inter-chiplet network, to accurately simulate inter-chiplet communication latency. 

3) **Global Manager (GM)** : Responsible for coordinating interchiplet data synchronization, scheduling NoI simulation, and executing synchronization strategies. The GM employs on-demand synchronization to minimize synchronization overhead while ensuring simulation accuracy. 

Simlets perform their respective chiplet simulation in parallel, communicate and synchronize with the GM through the UII, while the GM coordinates these simlets’ synchronization and data transfers, ensuring the accuracy of the simulation. The NoI simulator simulates the communication behavior between chiplets and provides the GM with communication delay of inter-chiplet data transfer, thus enabling the GM to make correct synchronization decisions. 

## **3.2 On-Demand Synchronization Mechanism** 

An application is partitioned into multiple threads to run on each chiplet. They are compiled using compilers according to the ISA of the chiplets. APIs in Section 4 are used for inter-chiplet communication and data access. Each simlet runs the application threads and upon inter-chiplet communications, calling of application level APIs are captured by the simlets. Simlets then request the global manager (GM) for synchronization and data transfer. LEGOSim runs in three 

1350 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

**==> picture [506 x 209] intentionally omitted <==**

**----- Start of picture text -----**<br>
Stage 1<br>Algorithm ... Simlet 1 ... Simlet  n<br>Inter-chiplet<br>Communication with<br>Zero Load Latency<br>Application ... ... Inter-Simlet Traffics<br> Level Stage 2<br>—Ea Tr<br>CPU code 1 CPU code 2 GPU code 1 CiM Inter-Simlet  Network-on- Simulated Latency<br>Traffics Interposer of Each Flow<br>Stage 3<br>Simulator  Simlet 1 Simlet 2 Simlet 3 Simlet 4<br>Level CPU CPU GPU CiM Simlet 1 ... Simlet  n<br>Inter-chiplet<br>Communication with<br>Simulated Latency<br>Global Manager<br>aca hs<br>Figure 4: Workflow of the three-stage decoupled simulation of LEGOSim. Left hand side: The overall flow of an application<br>running in LEGOSIM. Right hand side: The three-stage simulation.<br>**----- End of picture text -----**<br>


stages, as shown in Figure 4. In stage 1, both timing and functional models are simulated and inter-chiplet communication latency is estimated by zero load latency [41] in NoI, and all inter-chiplet communication traffic traces are recorded. In stage 2, these traces are simulated by a separate NoI simulator to obtain accurate latency results. In stage 3, LEGOSim runs with the accurate inter-chiplet communication latencies integrated. In this manner, inter-chiplet communication latency can be obtained separately which is used to compute clock cycles to safely advance for each simlet so as to avoid per-cycle synchronization and improve simulation efficiency. As a comparison, the previous parallel simulation schemes use percycle synchronization upon inter-chiplet communication to ensure temporal causality [24], leading to high synchronization overhead. 

As shown in Figure 5, inter-simlet synchronization is coordinated by the GM, which operates as a centralized controller thread/process. The simulation workflow involves the following four steps: 

① **Simlet Requesting** : A simlet _𝑖_ generates a _send/receive_ or shared memory/cache chiplet access request and sends it to the GM. This request includes timing information such as the simlet’s local clock cycle _𝜏𝑖_ . Upon submission, this simlet halts local clock progression and waits for the response from the GM. 

② **Request Handling by the Global Manager** : The GM handles requests as follows: 

1) For _send/receive_ requests, the GM matches the sender and responder simlets using a producer-consumer model to ensure ordered inter-chiplet communication. The GM calculates the next target clock cycle to be advanced for the simlet, coordinating with other active simlets to maintain consistent timing across the system. 

After identifying communication pairs, the GM computes the next admissible simulation cycle for the requesting simlet to avoid timing violation. In stage 1, where accurate inter-simlet traffic delays are not known yet, the simlet’s clock is advanced to the maximum of the two participating simlets’ cycles plus the zero load inter-chiplet transmission latency [41]. In stage 3, in contrast, the GM takes into account the actual latency obtained from stage 2: 

the sender simlet advances to the maximum cycle between the two, while the receiver simlet’s advancement is offset by the corresponding NoI transmission delay. 

2) For shared memory access requests, the GM identifies conflicting accesses. In stage 1, conflicts can be detected by setting a sliding time window _𝜌_ whereby each simlet _𝑗_ checks whether _𝑡 𝑗_ falls within the range _𝜏𝑖_ − _𝜌_ cycles, indicating a potential overlap in memory address. In stage 3, conflict information is directly derived from the recorded traces of Stage 1. 

For shared memory access, a simlet _𝑖_ is only permitted to proceed once all other conflicting simlets _𝑗_ , accessing the same address with earlier simulation time ( _𝑡 𝑗_ < _𝑡𝑖_ ), have advanced to time _𝑡𝑖_ at least. This ensures stric ~~t~~ temporal causali ~~t~~ y. The GM keeps an ordered request list for each shared m ~~emor~~ y address _𝑎_ as _𝐿𝑎_ = _< 𝑎,_ { _𝛼𝑖,𝜏𝑖_ + _𝑙𝑖_ } _>_ , where _𝜏𝑖_ is the simlet’s request timestamp, _𝑙𝑖_ is NoI transmission latency (which is zero load latency [41] in NoI in Stage 1 and accurate NoI latency in Stage 3), and _𝛼𝑖_ represents the 

**==> picture [197 x 113] intentionally omitted <==**

**----- Start of picture text -----**<br>
Simlet A Global Manager Simlet B<br>write ①Re  and t quest: A ②Handling<br>①Request:<br>②Handling<br>read and tB<br>③Response  ③Response<br>Clock Synchronization<br>④ Data Transfer<br>**----- End of picture text -----**<br>


**Figure 5: Workflow of inter-simlet** _**send/receive**_ **. Response in Step** ③ **includes permission (for Step** ④ **data transfer) and the clock cycle to be advanced.** 

1351 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

effective clock cycle when simlet _𝑖_ ’s request arrives at the shared memory. These requests are sorted by _𝛼𝑖_ in ascending order to ensure that earlier simulation events are processed first, even if their corresponding simlets progress more slowly in real time (wall clock time). 

③ **Request Response** : After processing the request, the GM returns a response to the originating simlet. 

1) For _send/receive_ requests, this response authorizes the data transfer to proceed and specifies the clock cycle to be advanced. 

2) For shared memory access requests, the response contains: (a) a valid cycle value _𝛼𝑖_ if _𝑖_ is the earliest requester in _𝐿𝑎_ , granting it access to address _𝑎_ ; (b) a zero advancement value for all other simlets in _𝐿𝑎_ , indicating they must wait until the earlier access completes. This mechanism preserves memory access order and prevents causality violations across simlets. 

④ **Data Transfer Execution/Shared Memory Access** : Upon receiving the synchronization response from the GM, the simlet advances its local clock to ~~t~~ he designated cyc ~~l~~ e and performs the requested operations, ~~eithe~~ r data transfer ~~or sh~~ ared memory access. 

In stage 3, discrepancies between the observed memory access order and that of stage 1 may lead to timing violations. In such cases, an optimistic [27] execution approach can be used. The simulation uses checkpointing and rollback to resolve conflicts, ensuring ~~that both the functional and temporal correctness are preserved.~~ Our experiments show that such violations are rare, especially for dataflow-dominated workloads, making this approach practical and efficient. By dynamically adjusting the synchronization points based on a ~~ctual communication b~~ ehavior and accurate data latency, LEGOSim achieves a favorable trade-off between simulation efficiency and model accuracy. 

Figure 6 shows a case where both simlet A and B need to write to shared memory chiplet M at their respective clock cycles of 100 and 50. Although simlet A runs faster, it is prevented from advancing past cycle 100 by the GM, as B has an earlier scheduled access at cycle 50. The GM ensures that B writes to M first, after which A is 

**==> picture [233 x 154] intentionally omitted <==**

**----- Start of picture text -----**<br>
A: cycle 100 — GM sorts events by  a=<br>M<br>B: cycle 50<br>—_*|| L, =a,{B,ap}{A,a,}<br>(a) The system model where chiplets A and B write to shared memory<br>chiplet M.<br>Write<br>A cycle 0~100 stay in cycle 100 cycle 100~120<br>Write<br>GM does not permit<br>B cycle 0~50 cycle 50~70<br> A +  A = 120   B +  B = 70  Write of B is permitted first .<br>**----- End of picture text -----**<br>


**(a) The system model where chiplets A and B write to shared memory chiplet M.** 

- **(b) Timing diagram. Assume inter-chiplet transmission latency is 20 cycles for packets from both chiplets.** 

**Figure 6: Simlets A and B writing to shared memory chiplet M.** 

allowed to proceed, which preserves correct execution order and maintains causal consistency. 

## **3.3 Formal Analysis for Validation** 

The transmission latency from chiplets _𝑢𝑚_ to _𝑢𝑛_ consists of 1) zero load latency _𝑡𝑧𝑒𝑟𝑜_ ( _𝑢𝑚,𝑢𝑛_ ), which is related to the shortest path distance between the source and destination chiplets, and 2) queuing latency _𝑡𝑞𝑢𝑒𝑢𝑖𝑛𝑔_ ( _𝑢𝑚,𝑢𝑛_ ), which is modeled by queuing theory [41]. 

1) Zero load latency: Given the multi-chiplet system, and the communication flow between chiplets _𝑢𝑚_ to _𝑢𝑛_ , the zero load latency _𝑡𝑧𝑒𝑟𝑜_ ( _𝑢𝑚,𝑢𝑛_ ) is determined by the length of the shortest path Π( _𝑢𝑚,𝑢𝑛_ ) in NoI between them as follows: 

**==> picture [189 x 9] intentionally omitted <==**

where _𝑘_ is the router pipeline stage number, _𝑙_ ( _𝑢𝑚,𝑢𝑛_ ) is the length of the shortest path from chiplets _𝑢𝑚_ to _𝑢𝑛_ , and _𝑡𝑠𝑒𝑟𝑖𝑎𝑙_ is the serialization latency. 

2) Queuing latency _𝑡𝑞𝑢𝑒𝑢𝑖𝑛𝑔_ ( _𝑢𝑚,𝑢𝑛_ ): The queuing latency of two chiplets _𝑢𝑚_ and _𝑢𝑛_ is the summation of the queuing latency of each router in the path Π( _𝑢𝑚,𝑢𝑛_ ) in NoI, which is determined by the routing algorithm adopted. Given the flows traversing router _𝑥𝑖,𝑗_ , the queuing latency is modeled by the G/G/1 model, where router _𝑥𝑖,𝑗_ is considered as multiple input channels _𝐼𝐶𝛼[𝑥][𝑖,𝑗]_ ∈{ _𝐼𝐶_ 1 _[𝑥][𝑖,𝑗]_ , _𝐼𝐶_ 2 _[𝑥][𝑖,𝑗]_ ,..., _𝐼𝐶𝑝[𝑥][𝑖,𝑗]_ } competing for a single output channel _𝑂𝐶[𝑥][𝑖,𝑗]_ ∈ _𝑂𝐶[𝑥][𝑖,𝑗]_ . The average _𝛽_ queuing latency _𝜏𝛼[𝑥][𝑖,𝑗]_ → _𝛽_[in router] _[ 𝑥][𝑖,𝑗]_[is [41]:] 

**==> picture [243 x 151] intentionally omitted <==**

the coefficients of variation for the packet arrival rate and service rate that is obtained based on the Allen-Cunneen approximation equation [41]. 

The communication latency _𝑡_ ( _𝑢𝑚,𝑢𝑛_ ) from chiplets _𝑢𝑚_ to _𝑢𝑛_ is the sum of zero load latency _𝑡𝑧𝑒𝑟𝑜_ ( _𝑢𝑚,𝑢𝑛_ ) and queuing latency of the routers along the path Π( _𝑢𝑚,𝑢𝑛_ ): 

**==> picture [220 x 30] intentionally omitted <==**

where _𝜆_ is the NoI arrival rate. 

The error of the latency of a packet transmission between LEGOSim and golden reference (a sequential simulator like gem5) is defined as in Equation 4. The difference lies in the queuing latency caused 

1352 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

**==> picture [236 x 94] intentionally omitted <==**

**----- Start of picture text -----**<br>
4<br>4<br>2 2<br>0 0<br>10 100 200 400 600 800 10 100 200 400 600 800<br>Inter-chiplet Traffic Volume (MB) Inter-chiplet Traffic Volume (MB)<br>(a) Error of simulation. (b) Error of  𝜆<br>Error (%)  Error (%)<br>**----- End of picture text -----**<br>


**Figure 7: Errors of simulation and** _𝜆_ **of LEGOSim with respect to gem5 under varying inter-chiplet communication traffic volumes.** 

by errors in packet timing, which have different packet arrival rates. 

**==> picture [237 x 58] intentionally omitted <==**

where _𝜆_ and _𝜆_[′] are the packet arrival rates of NoI in gem5 and LEGOSim respectively. _𝑡_ ( _𝑢𝑚,𝑢𝑛_ ) and _𝑡_[′] ( _𝑢𝑚,𝑢𝑛_ ) are the NoI latencies from _𝑢𝑚_ to _𝑢𝑛_ in gem5 and LEGOSim respectively. Benchmarks were used to evaluate the error where chiplets communicate each other in a producer-consumer manner and the destinations follow uniform distribution, and both gem5 and LEGOSim are configured to be a 4 CPU-chiplet system connected by a 2 × 2 NoI. The simulation error is defined as follows, 

**==> picture [186 x 24] intentionally omitted <==**

where _𝑇𝑔𝑒𝑚_ 5 and _𝑇𝐿𝐸𝐺𝑂𝑆𝑖𝑚_ are simulated execution cycles of gem5 and LEGOSim, respectively. 

The difference in packet arrival rates for NoI between gem5 and LEGOSim is below 5%, as in Figure 7b. Figure 7 shows the error of LEGOSim with respect to gem5. From Figure 7a, one can see that when the inter-chiplet traffic volume varies from 10 to 800MB, LEGOSim’s error remains below 5%, validating the fidelity of the model. 

## **4 Unified System Integration** 

The Unified Integration Interface (UII) is a foundational component of the LEGOSim framework to support modular parallel simulation of heterogeneous multi-chiplet systems. It is designed to provide a standardized framework to integrate diverse simulators—whether they model CPUs, GPUs, DRAMs, or domain-specific accelerators (DSAs)— into a cohesive simulation platform. UII abstracts simulator-specific interfaces and harmonizes them under a unified API, and supports benchmark/application-level APIs, system call mapping, data transfer management, and clock synchronization. Figure 8 outlines its modules, which include three modules: 

1) Benchmark/Application-Level APIs and System Call Definition: The UII defines a standard set of benchmark-level APIs used by chiplets for inter-chiplet communication and synchronization: 

**==> picture [218 x 91] intentionally omitted <==**

**----- Start of picture text -----**<br>
Benchmarks ： API<br>System Calls<br>Global<br>Data Transfer Clock Adjustment Manager<br>UII<br>**----- End of picture text -----**<br>


**Figure 8: Modules of the UII.** 

_sendMessage_ () and _receiveMessage_ (). When integrating a new simlet, these APIs must be mapped to the internal mechanisms of the simulator as follows. 

- For system-call based simulators (e.g., gem5 [55], Sniper [30]), these APIs are implemented as custom syscalls (e.g., _SYSCALL_REMOTE_READ_ and _SYSCALL_REMOTE_WRITE_ ) and processed by the syscall handling routine. 

- For runtime-library-based simulators (e.g., GPGPU-Sim [45]), these APIs are mapped to existing functions (e.g., _cudaMemcpy_ ()). 

- For DSA simulators (e.g., Scale-sim [66]), these APIs are embedded as function calls or files within the simulation script. 

Each simlets have the following application/benchmark level APIs for the programmer to call to issue inter-chiplet events. 

- _sendMessage(dst_x, dst_y, src_x, src_y, addr, nbyte)_ is used to send _nbyte_ byte messages located at _addr_ from chiplet _(src_x, src_y)_ to chiplet _(dst_x, dst_y)_ . 

- _receiveMessage(dst_x, dst_y, src_x, src_y, addr, nbyte)_ is used to receive _nbyte_ byte messages from chiplet _(src_x, src_y)_ to chiplet _(dst_x, dst_y)_ . 

- _barrier(id_list)_ is used to synchronize execution among chiplets in _id_list_ . All participating chiplets must reach the barrier before any of them can continue execution. 

- _lock(lock_id)_ is used to acquire a lock identified by _lock_id_ across all chiplets. Only one chiplet can hold the lock at a time, enabling mutually exclusive access to shared resources. _unlock(lock_id)_ is used to release the lock identified by _lock_id_ , 

- _read(dst_x, dst_y, src_x, src_y, addr, nbyte)_ and _write(dst_x, dst_y, src_x, src_y, addr, nbyte)_ are used to read _nbyte_ bytes of data from address _addr_ or write _nbyte_ bytes to _addr_ on chiplet _(src_x, src_y)_ . 

2) Data Transfer Implementation: Data transfer between chiplets in the UII is managed by functions such as _sendSync_ (), _receiveSync_ (), _write_data_ (), and _read_data_ (). These functions coordinate data transfer protocols with the GM and enable data transmission through dedicated channels as follows. 

- For CPU simulators (e.g., gem5 [55], Sniper [30]) , _sendMessage_ () / _receiveMessage_ () are translated to be inter-simlet data transmission in the syscall handling routines by file exchange, pipes, or shared memory in the host machine. Data is transferred from and to this simlet’s internal simulated memory. 

1353 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

**Table 2: Configurations used in the experiments.** 

|**Confgurations Used in the Simulation**|**Confgurations Used in the Simulation**||
|---|---|---|
|**Sniper Confguration**|**GPGPU-Sim Confguration**|**MNSIM Confguration**|
|Cores<br>8 x86_64 ISA<br>L1 D Cache<br>32KB, 8-way, 64B line, 4cycles, 1port<br>L1 I Cache<br>32KB, 4-way, 64B line, 4cycles<br>L2 Cache<br>256KB, 8-way, 64B line, 8cycles, 1port<br>L3 Cache<br>8192KB, 16-way, 64B line, 30cycles, 4ports<br>memorysize<br>2 GB|# of SMs<br>80<br>Tensor Core<br>640<br>Architecture<br>NVIDIA Volta (Titan V)<br>L1 Cache<br>32KB<br>L2 Cache<br>4.5MB|Memristor Model<br>RRAM<br>Weight Bit<br>8<br>Crossbar Size<br>24|
|||**DSA**|
|||# of MACs<br>128<br>Global Bufer<br>64 KB(SRAM)|
|**Confgurations of chiplet interposer**|||
|**Interposer**||**Chiplet**|
|Heat Thermal<br>Capacity<br>1_._81×106 J/(_𝑚_3 ·K)<br>Conductivity<br>35/(m·K)<br>Inter-chiplet Transmission EnergyConsumption<br>1_._17PJ/bit|Area<br>2500mm2<br>Thickness<br>0.1 mm|Chiplet Pitch<br>10 mm<br>Capacitance Density<br>300nF/mm2|



- For GPU simulators (e.g., GPGPU-Sim [45]), additional memory copy operations (e.g., _cudaMemcpy_ ()) are inserted before/after calling _sendSync_ () and _receiveSync_ () to move data between this simlet and others. These wrappers ensure that the GPU’s memory space remains consistent with LEGOSim’s global model. 

- For DSA simulators (e.g., Scale-sim [66]), UII writes inputs to an interface file, executes the DSA script, then reads output. _sendMessage_ () is implemented by writing input data to this file, or passing arguments to the Python configuration function for the simlet. _receiveMessage_ () reads output data after simulation completes. 

3) Clock Control: Given the diversity of simulation timing models, UII supports a flexible synchronization model to ensure that heterogeneous simlets advance their respective local clock tick correctly as follows. 

- For cycle-accurate simulators (e.g., gem5 [55], GPGPU-Sim [45]), their clock cycles are controlled. For example, gem5 uses an event-driven model of clock tick granularity, and synchronization is managed by controlling _tick_ . In GPGPUSim, simulation progress is tracked using _gpu_sim_cycle_ and _gpu_tot_sim_cycle_ . Clock ticking is controlled by these variables in such simulators. 

- For non-cycle-driven simulators (e.g., Sniper [30]), UII inserts pseudo operations to artificially delay execution, such as _Sleep_ () to adjust the clock delay according to the synchronization events. 

- For DSA simulators (e.g., Scale-Sim [66]), which have no native clock or with simplified execution timeline: A block of operations/computations is performed to obtain the execution time, which is reported to the GM for synchronization. 

Below are examples of how it facilitates integration in Sniper [30] , GPGPU-Sim [45] and Scale-Sim [66]: 

**Integration of Sniper [30]** . Sniper, a CPU simulator, required additional adaptation due to its non-cycle-driven execution. Custom system calls are defined ( _SYSCALL_REMOTE_READ_ and _SYSCALL_ REMOTE_WRITE_ ) to map Sniper’s remote read/write operations to UII’s _sendMessage_ () and _receiveMessage_ () functions. In the functional model, these system call handling routine translates _receiveSync_ (), _read_data_ (), _sendSync_ (), and _write_data_ () into inter-simlet message passing. In the timing model, _readSync_ () and _writeSync_ () are used for synchronization. However, since Sniper does not advance by 

discrete clock cycles, a _Sleep_ () function is inserted to adjust its execution timing according to the target clock cycles to be advanced, ensuring accurate synchronization. 

**Integration of GPGPU-Sim [45]** . GPGPU-Sim is used to simulate NVIDIA GPU architectures and relies on the CUDA runtime environment. Within the LEGOSim framework, its _sendMessage_ () and _receiveMessage_ () functions are mapped to CUDA _cudaMemcpy_ (), facilitating data transfer between this simlet and others. In terms of timing synchronization, GPGPU-Sim records local clock by _gpu_sim_cycle_ and _gpu_tot_sim_cycle_ and updates them according to the target clock cycles to be advanced. 

**Integration of Scale-Sim [66]** . Scale-Sim is integrated into LEGOsim as simlet through executing the corresponding python script with designated chiplet identifiers, topology, the workload of NPU as input parameters. As Scale-Sim has only timing model, the functional model is implemented in a dedicated C++ model. It receives input through _receiveMessage_ () and transmits output via _sendMessage_ () as wrappers. Upon completion of the simulation, the wrapper proceeds reading the execution time from Scale-Sim’s output logs. This execution time will be added to the time get from _readSync_ () and sent to other chiplets through _writeSync_ (). Data is received using _receiveSync_ () and _read_data_ () and sent using _sendSync_ () and _write_data_ (). 

By standardizing APIs, inter-chiplet communication data management, and clock synchronization, the UII enables seamless interoperability between diverse simlets, reducing integration complexity. 

## **5 Evaluation** 

## **5.1 Experimental Setup** 

The experiments were performed on a 20 cores Intel(R) Xeon(R) Gold 6133 CPU with 2.50GHz and 512G main memory server. The benchmarks include parallel convolution (conv) [47], breadth-first search (BFS) [15], matrix multiplication (matmul) [13], MLP [81], ResNet [29] and Transformer [28]. 

Following architectures were configured in the experiments: CPU-4GPU-NPU-3CiM, CPU-20GPU-15NPU, CPU-3GPU, CPUDSA-CiM-7GPU, CPU-DSA-CiM-47GPU, CPU-DSA-CiM-97GPU and CPU-20GPU-15NPU. Sniper [30], GPGPU-Sim [45], a customdeveloped simulator mimicking the architecture of the Eyeriss NPU, SCALE-Sim, and MNSIM were used as simlets for the CPU, GPU, domain-specific accelerator (DSA), NPU, and compute-in-memory 

1354 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

**Table 3: Configurations of SIMBA and CIM-based Accelerator.** 

|**Multi-chiplet System Architecture**|**Multi-chiplet System Architecture**|
|---|---|
|**SIMBA**|**CiM-based Accelerator**|
|Number of PEs<br>16<br>Technology<br>16 nm FinFET<br>Voltage<br>0.42–1.2 V<br>PE Clock Frequency<br>0.16–2.0 GHz<br>Global PE<br>Bufer Size<br>64 KiB<br>Routers Per<br>Global PE<br>3<br>NoC Bandwidth<br>68 GB/s/PE<br>Microcontroller<br>RISC-V|Activation Bufer<br>150KB<br>CiM Array Size<br>144KB<br>Clock Frequency<br>100MHz<br>CiM Type<br>ReRAM<br>CiM Array<br>Performance<br>1024 MACs per cycle<br>Die-to-die<br>Connections<br>1.2Gbps/link|



**Table 4: Simulation accuracy validation.** 

|**SIMBA Multi-chiplet Architecture**|**SIMBA Multi-chiplet Architecture**|
|---|---|
|**Architecture**<br>_𝜀_(%)|4-chiplet<br>8-chiplet<br>32-chiplet<br>2.52<br>3.51<br>5.35|
|**CiM-based Multi-chiplet Accelerator**||
|**Architecture**<br>_𝜀𝑢_(%)|4-chiplet<br>5-chiplet<br>9-chiplet<br>18-chiplet<br>2.71<br>4.68<br>2.69<br>5.79|



**==> picture [163 x 25] intentionally omitted <==**

where _𝑈𝑠𝑖𝑚_ and _𝑈𝑟𝑒𝑓_ are simulated computing utilization and referenced [14] computing utilization receptively. 

(CiM), respectively. These heterogeneous multi-chiplet systems cannot be simulated by most of the existing simulators listed in Table 1, except for LEGOsim. Two memory protocols were configured in these experiments: HBM3 and DDR5, both with capacity of 24GB [1] [4]. The thermal parameters of the interposer, as well as the core area and pitch of chiplets, are listed in Table 2. 

The transmission delay between adjacent chiplets is composed of the following three parts: 1) packetization and depacketization times (the values are obtained from [68] and [52]); 2) the transceiver latency (the values are obtained from [26] and [80]); and 3) the interposer wire delay and power models adopted from [37]. 

The inter-chiplet network topologies used in the experiment are mesh, meshLL (mesh with nodes ( _𝑥_ , _𝑦_ ) to node ( _𝑥_ + 1, _𝑦_ + 1) connected by a long serial link) [25], NVL (a fat tree mimicking the NVlink structure), star, and torus. 

## **5.2 Validating Simulation Accuracy** 

To validate the fidelity of the simulator, the 4-chiplet, 8-chiplet, and 32-chiplet SIMBA [69] architectures, as well as the 4-chiplet, 5-chiplet, 9-chiplet, and 18-chiplet CiM-based accelerator [14], were simulated. In the CiM-based accelerator, each chiplet has CiM units using ReRAM, on-chip SRAM buffers, and high-speed interconnections. The chiplets’ configurations in SIMBA and the CiM-based accelerator are detailed in Table 3. 

The ResNet-50 benchmark runs on the 4-chiplet, 8-chiplet, and 32-chiplet SIMBA architecture, while the Tiny-Yolo [39] benchmark runs on the 4-chiplet, 5-chiplet, 9-chiplet, and 18-chiplet CiM-based accelerator to compare its performance with the reported data from these two references. 

1) To quantify the simulation error of SIMBA architecture, the error _𝜀_ is defined as follows, 

**==> picture [174 x 25] intentionally omitted <==**

where _𝑇𝑠𝑖𝑚_ and _𝑇𝑟𝑒𝑓_ are simulated execution cycles and referenced execution cycles in [69] respectively. 

The _𝜀_ were 2.52%, 3.51% and 5.35% for 4-chiplet, 8-chiplet,and 32chiplet systems respectively for the SIMBA simulation as illustrated in Table 4, which are quite low. 

2) To quantify the simulation error of the Tiny-Yolo model running on the CiM-based accelerator architecture [14], simulation error _𝜀𝑢_ is defined as follows, 

The _𝜀𝑢_ were 2.71%, 4.68% , 2.69% and 5.79% for 4-chiplet, 5-chiplet, 9-chiplet and 18-chiplet systems respectively for the CIM-based accelerator as illustrated in Table 4, which are quite low. The low errors validate the high fidelity of LEGOSim in accurately modeling system performance. 

## **5.3 Synchronization Time Comparison** 

Figure 9 compares the time of the proposed on-demand synchronization (OD) with per-cycle synchronization (PC) and time quantum synchronization (TQ) to simulate CPU-3GPU system running the MLP benchmark. In contrast to conventional chip multiprocessor (CMP) architectures, where inter-core communication occurs with short intervals (a few or a few dozens of cycles), our target architectures are heterogeneous multi-chiplet systems, where inter-chiplet communication intervals are higher, from dozens to hundreds cycles, to reduce the high inter-chiplet communication latency. The synchronization time of the nine synchronization algorithms is normalized to that of PC. The inter-chiplet interconnection network topology is shown in the Figure 10a. TQ- _𝑥_ refers to synchronization occurring every _𝑥_ cycles. The OD approach reduces synchronization time by 99.9%, 99.9%, 99.8%, 99.7%, 99.7%, 99.4%, 98.1%, 96.6%, and 66.1% compared to PC, TQ-2, TQ-4, TQ-8, TQ-10, TQ-16, TQ-32, TQ-100, and TQ-1000, respectively. Notably, TQ-1000 exhibits a high synchronization error, whereas OD achieves high accuracy. The synchronization error quantifies the error with different synchronization methods w.r.t. PC, which is defined as: 

**==> picture [237 x 137] intentionally omitted <==**

**----- Start of picture text -----**<br>
𝜀𝑠𝑦𝑛𝑐 = 𝑚𝑎𝑥 | 𝑇𝑛 { 𝑇 − 𝑛𝑇,𝑇𝑝𝑐𝑝𝑐 | } (8)<br>1.0 Norm. Sync Count sync [ (%)] 50<br>0.8 40<br>0.6 30<br>0.4 20<br>0.2 10<br>0.0 0 0 0 0<br>PC TQ-2 TQ-4 TQ-8TQ-10TQ-16TQ-32TQ-100TQ-1000On-demand<br> (%)<br>sync<br>Norm. Sync Time<br>**----- End of picture text -----**<br>


**Figure 9: Comparison of synchronization event counts of PC, TQ, and OD synchronization methods.** 

1355 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

|MICRO ’25, October 18–22, 2025, Seo<br>anan n, eng u, aoang|MICRO ’25, October 18–22, 2025, Seo<br>anan n, eng u, aoang|MICRO ’25, October 18–22, 2025, Seo<br>anan n, eng u, aoang|MICRO ’25, October 18–22, 2025, Seo<br>anan n, eng u, aoang|MICRO ’25, October 18–22, 2025, Seo<br>anan n, eng u, aoang|MICRO ’25, October 18–22, 2025, Seo<br>anan n, eng u, aoang|ang, ng ang, un eng, ngao Jang|ang, ng ang, un eng, ngao Jang|ang, ng ang, un eng, ngao Jang|ang, ng ang, un eng, ngao Jang|ang, ng ang, un eng, ngao Jang|ang, ng ang, un eng, ngao Jang|ang, ng ang, un eng, ngao Jang|, m umar ng, Jemng n, a u,|, m umar ng, Jemng n, a u,|, m umar ng, Jemng n, a u,|, m umar ng, Jemng n, a u,|, m umar ng, Jemng n, a u,|, m umar ng, Jemng n, a u,|, m umar ng, Jemng n, a u,|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|aoong , n ang, Je ong, ngze an<br>and Kui Re|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
||MICRO ’25, October 18–22, 2025, Seo|||||ul|, Republic of Korea|||||||||||||and Kui|||||||||||||
|**GPU**<br>**GPU**<br>**GPU**<br>**CPU**<br>**GPU**<br>**GPU**<br>**GP**~~**U**~~<br>**CPU**<br>**CI**~~**M**~~<br>~~**CIM**~~<br>**GPU**<br>**NPU**<br>**CIM**<br>**DRA**~~**M**~~<br>**DRA**~~**M**~~<br>**DRA**~~**M**~~<br>**DSA**<br>**(MC)**<br>~~**D**~~**RA**~~**M**~~<br>**DSA**<br>**(MC)**<br>**DSA**<br>~~**(MC)**~~<br>**CPU**<br>**DSA**<br>**(MC)**<br>**stage 0&1**<br>**stage 2**<br>**stage 3**<br>**stage 4**<br>**G**<br>**N**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**C**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**x**<br>**y**|||||||||||||||||||||||||||||||||
||||**G**|**PU**|**GPU**<br>**GPU**||||**GPU**|||**GPU**<br>**DRA**||~~**M**~~<br>**DRA**~~**M**~~<br>||**DSA**<br>~~**(MC)**~~<br>**CPU**<br>**DSA**<br>**(MC)**<br>**stage 0&1**<br>**stage 2**<br>**stage 3**<br>**stage 4**<br>**G**<br>**N**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**C**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**G**<br>**N**<br>**G**<br>**N**<br>**G**<br>**x**<br>**y**|||||||||||||||||
||||**G**|**PU**|**CPU**|||**GP**~~**U**~~<br>**CI**~~**M**~~||**CPU**<br>~~**CIM**~~||**NPU**<br>**CIM**<br>**DRA**<br>~~**D**~~**RA**||~~**M**~~<br><br>~~**M**~~<br>|**DSA**<br>**(MC)**<br>**DSA**<br>**(MC)**||**CP**<br>**DS**<br>**(M**|**U**<br>**A**<br>**C)**|||**N**<br>**G**<br>**G**|**G**<br>**N**<br>**G**||**C**<br>**G**<br>**N**||**G**<br>**N**<br>**G**|||**N**<br>**G**<br>**N**||**G**<br>**N**<br>**G**||
||||**(a) CPU-3GPU**<br>**(b) CPU-4GPU-NPU-3CIM**<br>**(c)**|||||||||||**CPU-4DSA-4DRAM**<br>**(d) CPU-20GPU-15NPU**|||||||||||||||||||



**Figure 10: Inter-chiplet network topologies of the multi-chiplet architectures in experiments.** 

where _𝑛_ ∈{ _𝑇𝑄_ − _𝑥,𝑂𝐷_ } _,𝑥_ ∈{2 _,_ 4 _,_ 8 _,_ 10 _,_ 16 _,_ 32 _,_ 100 _,_ 1000}. Here, _𝑇𝑛_ is total execution time with synchronization algorithm _𝑛_ . _𝑇𝑝𝑐_ is the total execution time in PC synchronization. _𝜀𝑠𝑦𝑛𝑐_ are 0% for OD, and 0%, 0.04%, 0.24%, 0.24%, 0.47%, 0.87%, 1.9%, 3.9%, and 38.4% for PC, TQ-2, TQ-4, TQ-8, TQ-10, TQ-16, TQ-32, TQ-100, and TQ-1000, respectively. These results indicate that as the synchronization interval in the TQ algorithm increases, _𝜀𝑠𝑦𝑛𝑐_ also increases. In contrast, on-demand synchronization exhibits the lowest overhead while maintaining high accuracy. 

Figure 11 shows the time breakdown of sequential simulation, PC, and OD. The time of the three synchronization methods is normalized to the total simulation time of sequential simulation. Sequential simulation exhibits the highest chiplet-simulation time. PC reduces simulation time but incurs both the highest synchronization time. In contrast, OD has the lowest synchronization overhead and the lowest total simulation time. For OD, the synchronization and chiplet simulation times of both Stages 1 and 3 are included in Figure 11. On average, the overhead of OD Stage 1 occupies 40% of the total simulation time. 

Compared to the chiplet-simulation time in sequential simulation and the synchronization time in PC, the chiplet-simulation and synchronization time with OD are reduced by 61.9% and 98.1%, respectively. Furthermore, the total simulation time of LEGOSim is reduced by 61.4% and 56.7% compared to sequential simulation and per-cycle synchronized parallel simulation, respectively. 

## **5.4 Scalability and Bottleneck Analysis** 

LEGOSim can be used to simulate large-scale multi-chiplet systems on a single server. Its simulation speed is primarily affected by the volume of inter-chiplet communication, due to overhead of 

**==> picture [232 x 95] intentionally omitted <==**

**----- Start of picture text -----**<br>
1.0<br>0.5<br>0.0<br>Total Simulation Time Chiplet-simulation Time<br>Sync Simulation Time NoI-simulation Time<br>Sequential SimulationPer-cycle Sync SimulationProposed Simulation<br>Norm. Time<br>**----- End of picture text -----**<br>


synchronization. As inter-chiplet traffic increases, so does the synchronization frequency, which slows down simulation. Figure 12 shows the simulation time comparison across a 100-chiplet system with varying inter-chiplet communication volumes, all running the same input-sized MLP benchmark. The 100-chiplet system configuration is CPU-DSA-CiM-97GPU and adopts a mesh inter-chiplet interconnection network topology. As one can see, when the interchiplet communication volume exceeds 100 MB, the simulation time increases faster and faster with the increasing of communication volume, indicating that the GM reaches synchronization bottleneck. To alleviate this bottleneck, the single GM scheme can be improved by a distributed management scheme, where there are _𝑚_ local managers, each controls _𝑛_ simlets, and a GM controls the _𝑚_ local managers and NoI. Figure 12 shows that this scheme decreases the simulating time by 56%, comparing to the centralized (single GM scheme) when the inter-chiplet communication volume is 800 MB. 

## **6 Case Studies** 

## **6.1 Exploring the Design Space of On-chip Buffer and Inter-chiplet Interconnection Network** 

In the first case study, we conducted a design space exploration (DSE) using LEGOsim. The experiment was configured on a CPU20GPU-15NPU architecture with a mesh topology as inter-chiplet interconnection network, as illustrated in Figure 10d, where “C”, “G” and “N” are CPU, GPU and NPU chiplets, respectively. The ResNet50 benchmark was the workload. In the baseline configuration, each GPU chiplet has 114 Streaming Multiprocessors. The NPU chiplet adopts the SIMBA architecture. Additional configuration details 

**==> picture [234 x 74] intentionally omitted <==**

**----- Start of picture text -----**<br>
100<br>original<br>distributed<br>50<br>0<br>10 100 200 400 600 800<br>Inter-chiplet Traffic Volume (MB)<br>Sim. Time (hours)<br>**----- End of picture text -----**<br>


**Figure 11: Simulation time comparison of three different methods.** 

**Figure 12: Simulation time comparison with different traffic volumes.** 

1356 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

**Table 5: Configurations of the CPU-20GPU multi-chiplet systems** 

|**GPU chiplet**<br> <br>|**GPU chiplet**<br> <br>|**CPU chiplet**<br> <br>|
|---|---|---|
|# of SMs<br>114<br>Technology<br>4nm FinFET<br>L1 Cache Size<br>128KB<br>Architecture<br>Nvidia Hopper<br>L2 Cache Size<br>50MB<br>Frequency<br>2GHz||# of Cores<br>8<br>Technology<br>7nm FinFET<br>L1 Cache Size<br>512KB<br>L2 Cache Size<br>4MB<br>L3 Cache Size<br>16MB<br>Base Frequency<br>3.2GHz|
||**Table 6: Performance comparison**<br>**Computation**<br>**Bufer access**<br>**NoI**<br>Norm. Time<br>0.34<br>0.72<br>1||



are provided in Table 5. The NoI bandwidth of this multi-chiplet architecture is 100 GB/s. 

In this setup, the 36 chiplets are divided into four groups, with each group computing one or two stages of ResNet-50. To identify the performance bottlenecks of this architecture when running ResNet-50, running the ResNet-50 benchmark to this multi-chiplet system involves following three steps: allocating tasks to different chiplets, inserting the inter-chiplet communication (using the API functions defined in Section 4) and synchronization. 

In the first step, tasks are assigned to different chiplets based on their computational workloads. Layer res2[a-c]_branch2c, res[25]a_branch1, res3[a-d]_branch2c, res4[a-f]_branch2c, and res5[ac]_branch2c of ResNet-50 are allocated to NPU chiplets. Other layers are allocated to GPU chiplets. In Figure 10d, res1 through res5 correspond to stages 0 through 4, respectively. The CPU chiplet is the manager, distributing computation tasks to other chiplets. 

In the second step, the tasks running on the GPU chiplets are programmed using CUDA. The tasks on the NPU chiplets are implemented by configuring a CSV topology file in SCALE-Sim. This topology file defines the layers of the workload. In SCALE-Sim, convolution layers and other operations that can be expressed in terms of equivalent GEMM operations are described using the _𝑀, 𝑁, 𝐾_ format in the workload topology. The tasks running on the CPU chiplets are programmed using C++. 

As shown in Table 6, the Network-on-Interposer (NoI) latency and on-chip buffer access time are identified as the performance bottlenecks in this case. The times of computation, buffer access, and NoI are normalized to that of NoI latency. For example, chiplet (0,0) spent 35.6% and 42.9% time in buffer access and waiting for the remote data access. The breakdowns of a few chiplets’ performances, which are normalized to the NoI latency of chiplet (3,0), are shown in Figure 13. In what follows, the on-chip buffer size and NoI bandwidth are selected as design variables to reduce the overall execution time. 

To model the impact of on-chip buffer size and NoI bandwidth w.r.t. execution time, LEGOsim is run with different configurations. The following performance model is obtained using the maximum likelihood method [57]: 

**==> picture [197 x 10] intentionally omitted <==**

**==> picture [242 x 105] intentionally omitted <==**

**----- Start of picture text -----**<br>
1.0<br>0.5<br>0.0<br>Chiplet #<br>Computation NoI Buffer access<br>(0,0) (1,1) (2,0) (3,1) (4,0) (5,0) (0,1) (1,0) (2,1) (3,0)<br>Norm. Time<br>**----- End of picture text -----**<br>


**Figure 13: Breakdown of performances for selected chiplets.** 

where _𝑎_ , _𝑏_ , _𝑐_ and _𝑑_ are regression coefficients and _𝐼_ , _𝑇_ , _𝐵_ are NoI bandwidth, total execution time, and buffer size of each chiplet. Equation 9 has a regression error of 8%. 

To explore the design space, an optimization problem is defined to minimize the execution time under power constraints with power models adopted as in [77]. NSGA-II [21] is used to solve this problem. For comparison, two reference architectures listed in Table 7 are used. The power budget in Table 7 is a user-defined constraint in our design space exploration framework, guiding the search for optimal architectures with minimum execution time. For the CPU20GPU-15NPU configuration, the power budget of each GPU is around 300 ∼ 350W [3] and we used an H100 server to measure power with workloads. The power consumption of each NPU is adopted from [22]. The power of D2D interface is adopted from [79]. Additional powers from CPU, SRAM buffers, and inter- and intrachiplet network are estimated using McPAT [50], CACTI [65], and DSENT [71], respectively. Based on these, power budgets of 6200W to 6700W were explored in increments of 100W. Figure 15 shows that, under different power budgets, the proposed solution achieves the lowest execution time. For example, it reduces execution time by 30% and 27% compared to reference configurations 1 and 2 under a power budget of 6200 W, respectively. Execution time of each configuration is normalized to that of the maximum execution time of reference configurations 1 and 2. This example shows that LEGOsim can be used to identify performance breakdowns and bottlenecks, generate datasets with different configurations for performance modeling, which is used in design space exploration (i.e., optimizing performance under power constraints). 

LEGOSim focuses on simulating application performance on specified system configurations. Chiplet repartitioning, on the contrary, is part of the DSE process. To support this, we provide 

**Table 7: Configurations of reference architectures** 

|**Power**<br>**budget (W)**|**Reference**<br>**confgurations 1**|**Reference**<br>**confgurations 2**|
|---|---|---|
||**Bufer**<br>**size (MB)**<br>**NoI**<br>**bandwidth**<br>**(GB/s)**|**Bufer**<br>**size (MB)**<br>**NoI**<br>**bandwidth**<br>**(GB/s)**|
|6200<br>6300<br>6400<br>6500<br>6600<br>6700|2<br>512<br>8<br>512<br>15<br>1024<br>23<br>1024<br>30<br>1024<br>40<br>2048|2<br>512<br>10<br>512<br>17<br>1024<br>24<br>1024<br>33<br>1024<br>45<br>2048|



1357 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

|**(1,1)**<br>**CPU**<br>**_τ_(1,1)=0.36**<br>**(0,0)**<br>**GPU**<br>**_τ_(0,0)=11.5,n=374917 cycle**<br>**(0,1)**<br>**GPU**<br>**_τ_(0,1)=5.8, n=374917 cycle**<br>**(1,0)**<br>**GPU**<br>**_τ_(1,0)=5.9,n=374917 cycle**<br>**(2,0)**<br>**CIM**<br>**_τ_(2,0)=0.38, n=153 cycle**<br>**(2,1)**<br>**CIM**<br>**_τ_(2,1)=0.42, n=145 cycle**<br>Start<br>**825 cycle**<br>**64199 cycle**<br>**820 cycle**<br>**64199 cycle**<br>**173 cycle**<br>**173 cycle**<br>**204 cycle**<br>**204 cycle**<br>**61762 cycle**<br>**808 cycle**|**(1,2)**<br>**NPU**<br>**_τ_(1,2)=1.36,n=2502 cycle**<br>**(0,2)**<br>**GPU**<br>**_τ_(0,2)=5.8,n=374917 cycle**<br>**(2,2)**<br>**CIM**<br>**_τ_(2,2)=0.39, n=160 cycle**<br>End<br>**814 cycle**<br>**63556 cycle**<br>**279 cycle**<br>~~**1279 cycle**~~<br>**208 cycle**<br>**206 cycle**<br>**206 cycle**|
|---|---|



**Figure 14: Chiplet level task graph of the parallel convolution benchmark with CPU-4GPU-NPU-CiM architecture.** 

a Python-based script in [7] that allows users to (1) input various chiplet partition configurations, (2) automatically generate LEGOSim configuration files, and (3) excute batch simulations across these configurations. This tool enables the evaluation of performance impacts under different chiplet arrangements and simplifies DSE workflows. 

## **6.2 Alleviating Computation Bottlenecks Using LEGOsim** 

In this case study, we demonstrate how LEGOSim can be used to flexibly and accurately compare various multi-chiplet architectures to identify and address computational performance bottlenecks and trade-offs inherent to these architectures. Initially, a baseline architecture CPU-4GPU-NPU-3CiM, connected via a 3 × 3 mesh inter-chiplet network, was configured. This setup, referred to as the CPU-4GPU-NPU-3CiM architecture, was tasked with running the parallel convolution benchmark with a convolution matrix of size 128 × 128 × 3, are shown in Figure 10b. 

To analyze performance, a key metric is defined, _𝜏_ ( _𝑥,𝑦_ ) (computation to communication latency ratio of chiplet ( _𝑥,𝑦_ )), as the ratio of each chiplet’s execution time to its communication latency. Figure 14 reveals that _𝜏_ (0 _,_ 0) , the computation to communication latency ratio of the GPU chiplet at (0,0), reaches the highest value of 11.5. Indicating that the GPU chiplet at (0,0) is the bottleneck in terms of computation. 

To address this issue, we reconfigured the system by adding two additional GPU chiplets and redistributing the workload previously handled by GPU (0,0). After this adjustment, _𝜏_ (0 _,_ 0) is reduced to 7, and the overall system execution time is decreased by 15%. 

**==> picture [242 x 94] intentionally omitted <==**

**----- Start of picture text -----**<br>
1.0<br>0.5<br>0.0<br>6200 6300 6400 6500 6600 6700<br>Power Limit (W)<br>Optimized results Ref. config. 1 Ref. config. 2<br>Norm. Exec. Time<br>**----- End of picture text -----**<br>


**Figure 15: Execution time comparison by varying power budgets.** 

This case study highlights the effectiveness of LEGOSim for evaluating the performance of different multi-chiplet architectures. 

## **6.3 Evaluating Different Inter-chiplet Network Topology Configurations** 

For our first case study, LEGOSim was used to evaluate the impact of different inter-chiplet network topologies on the multi-chiplet system. Using the CPU-4GPU-DSA-CiM architecture, LEGOSim was configured with various inter-chiplet network topologies, including mesh, meshLL, NVL, and torus. These configurations were evaluated using benchmarks such as matmul, MLP, and Transformer, with varying packet flit sizes. 

Figure 16 compares the normalized execution times with different inter-chiplet network configurations. With a flit size of 4 and the star topology, each benchmark achieves the shortest execution time. The execution times for the transformer, matmul, BFS, and MLP benchmarks were reduced by 12.56%, 43.14%, 25.16%, and 35.74%, respectively, when the flit size increases from 2 to 4. 

A visualization tool for inter-chiplet traffic distribution of each D2D interface is included in LEGOSim as shown in Figure 17. Through this tool, researchers can observe the traffic volume at each D2D interface and the number of packets transmitted between 

**==> picture [230 x 158] intentionally omitted <==**

**----- Start of picture text -----**<br>
Transformer Matmul<br>1.0<br>1.0<br>0.8<br>0.6<br>0.8 0.4<br>(a) (b)<br>BFS MLP<br>1.0 1.0<br>0.8<br>0.8<br>0.6<br>0.6 0.4<br>(c) flit=2 flit=4 (d)<br>meshmeshLL NVL star torus meshmeshLL NVL star torus<br>meshmeshLL NVL star torus meshmeshLL NVL star torus<br>Norm. Cycles Norm. Cycles<br>Norm. Cycles Norm. Cycles<br>**----- End of picture text -----**<br>


**Figure 16: The execution times of (a) Transformer, (b) Matmul, (c) BFS, (d) MLP with different inter-chiplet network configurations.** 

1358 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

chiplets, which can help researchers to find out the bottleneck of the multi-chiplet system more easily. 

## **6.4 Evaluating HBM3 vs. DDR5 in a CPU-4DSA-4DRAM Multi-chiplet System** 

For this case study, we examine the impact of different memory protocols (HBM3 versus DDR5) in the CPU-4DSA-4DRAM multichiplet system, using ResNet-50 as benchmark, where a DDR DRAM with 32 GB is connected to the memory controller in the CPU chiplets. The inter-chiplet interconnection topology is mesh as shown in Figure 10c where each DSA has a memory controller (MC) and UCIe is used as D2D communication protocol. 

Figure 18a shows that the total execution cycle of the system with HBM 3 is 39.1% lower than that of the system with DDR 5. The significant performance improvement demonstrates that HBM 3 is a superior choice for bandwidth-intensive workloads, particularly for deep learning inference tasks. These results, obtained through LEGOSim, reinforce its capability to accurately model memory hierarchy trade-offs in multi-chiplet architectures, making it an effective tool for guiding system design decisions. 

## **6.5 Evaluating UCIe vs. PCIe in a CPU-4DSA-4DRAM Multi-chiplet System** 

Beyond memory protocols, D2D interconnection technology plays a pivotal role in determining overall system performance. This case study evaluates the impact of adopting Universal Chiplet Interconnection Express (UCIe) [70] and Peripheral Component Interconnection Express (PCIe) [6] as the D2D communication protocol in a 1CPU-4DSA-4DRAM multi-chiplet architecture. The inter-chiplet network topology is shown in the Figure 10c. LEGOSim was used to model and analyze both configurations to assess their impact on execution time, focusing on inter-chiplet interconnection protocol and communication time within the multi-chiplet system. 

Figure 18 shows that the total execution time of the system with UCIe is 32.9% lower than that of the system with PCIe. These improvements highlight UCIe’s ability to minimize interconnection latency, making it a more efficient solution for chiplet-based architectures. 

The findings further validate LEGOSim’s ability to model interconnection trade-offs, demonstrating its effectiveness in evaluating chiplet design choices. By capturing the performance impact of 

**==> picture [221 x 104] intentionally omitted <==**

**----- Start of picture text -----**<br>
15000 15000<br>0 0<br>1 10000 1 10000<br>2 5000 2 5000<br>3 3<br>i 0 0<br>0 1 2 3 0 1 2 3<br>Y Y<br>(a) mesh (b) meshLL<br>X X<br>Traffic volume Traffic volume<br>**----- End of picture text -----**<br>


**Figure 17: Inter-chiplet network traffic distributions of the matmul benchmark with (a) mesh and (b) meshLL as interchiplet network topologies.** 

different interconnection technologies, LEGOSim proves to be a valuable tool for optimizing next-generation multi-chiplet systems. 

**==> picture [205 x 75] intentionally omitted <==**

**----- Start of picture text -----**<br>
1.0 1.0<br>0.5 0.5<br>0.0 0.0<br>DDR 5 HBM 3 PCIe UCIe<br>(a) HBM 3 vs DDR 5 (b) UCIe vs PCIe<br>Norm. cycles Norm. cycles<br>**----- End of picture text -----**<br>


**Figure 18: Performance comparision.** 

## **7 Conclusion** 

In this paper, we proposed LEGOSim, a modular and unified parallel simulation framework tailored for heterogeneous multi-chiplet systems. LEGOSim supports seamless integration of diverse simulators (simlets) as processes in parallel simulation, enabling accurate and flexible modeling. To address synchronization bottlenecks in parallel simulation, on-demand synchronization was proposed, where synchronization occur only upon inter-chiplet communication to reduce synchronization overhead in parallel simulatoin. A detailed NoI simulation is integrated to accurately simulate various NoI configurations. The Unified Integration Interface (UII) was proposed as a standard interface, allowing existing simulators like gem5, Sniper, and GPGPU-Sim to be integrated with minimal code changes to support parallel simulation. Experimental results shows that, LEGOSim has modeling errors of 3.79% and 3.94% when validating against SIMBA and a CiM-based accelerator, indicating high fidelity. LEGOSim also decreases synchronization overhead by 99.9% and 66.1% compared to per-cycle synchronization and time quantum, respectively. LEGOSim was showcased to analyze the performance bottleneck and perform design space exploration for various multi-chiplet systems. LEGOSim was open sourced, and hopefully can facilitate design space exploration for future large-scale multi-chiplet systems. 

## **Acknowledgments** 

This work was supported in part by the National Natural Science Foundation of China under Grants 92373205 and 62374146, in part by the National Key Research and Development Program of China No. 2023YFB4404404, in part by the Key Technologies R&D Program of Jiangsu (Prospective and Key Technologies for Industry) under Grant BE2023005-2, in part by the key R&D programme of Zhejiang Province No. 2024C01012, in part by the Ant Group through CCFAnt Research Fund, and in part by CIE-Smartchip research fund No. 2023-004. 

## **References** 

> [1] [n. d.]. HBM3 IP technical bulletin. https://www.synopsys.com/designwareip/technical-bulletin/hbm3-ip-dwtb.html 

- [2] [n. d.]. Intel Distribution of OpenVINO toolkit. https://software.intel.com/enus/openvino-toolkit 

> [3] [n. d.]. NVIDIA H100 parameter. https://www.nvidia.com/content/dam/enzz/Solutions/gtcs22/data-center/h100/PB-11133-001_v01.pdf 

> [4] [n. d.]. SK Hynix details its DDR5-6400 DRAM dhip. https://www.anandtech. com/show/13999/sk-hynix-details-its-ddr56400-dram-chip 

1359 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

- [5] [n. d.]. The SR-71 of computing: Intel Ponte Vecchio retires after five years. https://www.jonpeddie.com/news/the-sr-71-of-computing-intel-pontevecchio-retires-after-five-years/ 

- [6] 2022. PCI express base specification revision 6.0 version 1.0. [7] 2025. LEGOSim. https://github.com/FCAS-LAB/LEGOSIM_MICRO. [8] 2025. LEGOSim User Manual. https://github.com/FCASLAB/LEGOSIM_MICRO/blob/main/LEGOSim_Manual.pdf. 

- [9] Niket Agarwal, Tushar Krishna, Li-Shiuan Peh, and Niraj K Jha. 2009. GARNET: a detailed on-chip network model inside a full-system simulator. In _Proc. IEEE Int’l Symp. Perform. Anal. Syst. Softw._ 33–42. 

- [10] AMD. 2023. _Zen 5 architecture overview_ . Whitepaper. [11] Yehia Arafa, Abdel-Hameed A Badawy, Gopinath Chennupati, Nandakishore Santhi, and Stephan Eidenbenz. 2019. PPT-GPU: scalable GPU performance modeling. _IEEE Comput. Archit. Lett._ 18, 1 (2019), 55–58. 

- [12] Todd Austin, Eric Larson, and Dan Ernst. 2002. SimpleScalar: an infrastructure for computer system modeling. _Computer_ 35, 2 (2002), 59–67. 

- [13] Grey Ballard, Christopher Siefert, and Jonathan Hu. 2016. Reducing communication costs for sparse matrix multiplication within algebraic multigrid. _SIAM J. Sci. Comput._ 38, 3 (2016), 203–231. 

- [14] Jinshan Zhang Shunli Wang Xiaoyang Kang Lhua Zhang Mingyu Wang Bo Jiao, Haozhe Zhu and Chixiao Chen. 2021. Computing utilization enhancement for chiplet-based homogeneous processing-in-memory deep learning processors. In _Proc. Great Lakes Symp. VLSI_ . 241–246. 

- [15] A. Buluç and K. Madduri. 2011. Parallel breadth-first search on distributed memory systems. In _Proc. SC Conf._ 1–12. 

- [16] G. Carneiro. 2010. NS-3: Network simulator 3. In _UTM Lab Meeting_ . 4–5. [17] Vincenzo Catania, Andrea Mineo, Salvatore Monteleone, Maurizio Palesi, and Davide Patti. 2015. Noxim: an open, extensible and cycle-accurate network on chip simulator. In _Proc. IEEE Int’l Conf. Appl.-Specific Syst., Archit. Processors_ . 162–163. 

- [18] P. Y. Chen, X. Peng, and S. Yu. 2018. NeuroSim: a circuit-level macro model for benchmarking neuro-inspired architectures in online learning. _IEEE Trans. Comput.-Aided Design Integr. Circuits Syst._ 37, 12 (2018), 3067–3080. 

- [19] Toni Cortes and Jesús Labarta. 1999. HRaid: A Flexible Storage-system Simulator.. In _PDPTA_ . 772–778. 

- [20] J. Cubero-Cascante, N. Zurstraßen, and J. Nöller. 2023. parti-gem5: gem5’s Timing Mode Parallelised. In _Proc. Int’l Conf. Embedded Comput. Syst._ 177–192. 

- [21] K. Deb, A. Pratap, S. Agarwal, and T. Meyarivan. 2002. A fast and elitist multiobjective genetic algorithm: NSGA-II. _IEEE Trans. Evolutionary Computation_ 6, 2 (2002), 182–197. 

- [22] Yanchi Dong, Xueping Liu, Xiaochen Hao, Yun Liang, Ru Huang, Le Ye, and Tianyu Jia. 2024. Hierarchical power co-Optimization and management for LLM chiplet designs. _ICCAD ’24_ (2024), 1–9. 

- [23] Jan Edler. 1994. Dinero IV: trace-driven uniprocessor cache simulator. (1994). https://pages.cs.wisc.edu/~markhill/DineroIV/ 

- [24] Lieven Eeckhout. 2010. _Computer Architecture Performance Evaluation Methods_ . Morgan & Claypool Publishers. 

- [25] Yinxiao Feng, Yuchen Wei, Dong Xiang, and Kaisheng Ma. 2024. Evaluating chiplet-based large-scale interconnection networks via cycle-accurate packetparallel simulation. In _Proc. USENIX Annu. Tech. Conf._ 731–747. 

- [26] Yinxiao Feng, Dong Xiang, and Kaisheng Ma. 2023. Heterogeneous die-todie interfaces: enabling more flexible chiplet interconnection systems. In _Proc. IEEE/ACM Int’l Symp. Microarch._ 930–943. 

- [27] Richard M Fujimoto. 2001. Parallel and distributed simulation systems. In _Proc. 33rd Winter Simul. Conf._ , Vol. 1. 147–157. 

- [28] Chaoyang He, Shen Li, Mahdi Soltanolkotabi, and Salman Avestimehr. 2021. PipeTransformer: automated elastic pipelining for distributed training of transformers. _arXiv_ (2021). 

- [29] Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. 2016. Deep residual learning for image recognition. In _Proc. IEEE Conf. Computer Vision and Pattern Recognition_ . 

- [30] W. Heirman, T. Carlson, and L. Eeckhout. 2012. Sniper: scalable and accurate parallel multi-core simulation. In _Proc. Int’l Summer School Adv. Comput. Archit._ 91–94. 

- [31] Guseul Heo, Sangyeop Lee, Jaehong Cho, Hyunmin Choi, Sanghyeon Lee, Hyungkyu Ham, Gwangsun Kim, Divya Mahajan, and Jongse Park. 2024. Neupims: npu-pim heterogeneous acceleration for batched llm inferencing. In _ASPLOS ’24_ . 722–737. 

- [32] Intel. 2018. _OpenCL Beignet Project_ . Technical Report. Intel. 

- [33] C. Jiang, A. Jayarajan, and H. Lu. 2023. Arbitor: a numerically accurate hardware emulation tool for DNN accelerators. In _Proc. USENIX Technical Conference_ . 519– 536. 

- [34] H. Jiang. 2022. Intel’s Ponte Vecchio GPU: Architecture, Systems & Software. In _Proc. IEEE Hot Chips Symp._ 1–29. 

- [35] Nan Jiang, George Michelogiannakis, Daniel Becker, Brian Towles, and William J Dally. 2010. _BookSim 2.0 user’s guide_ . Technical Report. Stanford Univ. 

- [36] M. Jung, J. Zhang, and A. Abulila. 2017. SimpleSSD: modeling solid state drives for holistic system simulation. _IEEE Computer Architecture Letters_ 17, 1 (2017), 

- 37–41. 

- [37] MD Arafat Kabir and Yarui Peng. 2020. Chiplet-package co-design for 2.5D systems using standard ASIC CAD tools. In _Proc. Asia South Pac. Des. Autom. Conf._ 351–356. 

- [38] Mahmoud Khairy, Zhesheng Shen, Tor M Aamodt, and Timothy G Rogers. 2020. Accel-sim: an extensible simulation framework for validated GPU modeling. In _Proc. ACM/IEEE Int’l Symp. Comput. Archit._ 473–486. 

- [39] Ivan Khokhlov, Egor Davydenko, and Ilya Osokin. 2020. Tiny-YOLO object detection supplemented with geometrical data. _arXiv_ . 

- [40] K. Shafie Khorassani, J. Hashmi, and C. H. Chu. 2021. Designing a ROCmaware MPI library for AMD GPUs: early experiences. In _Proc. Int’l Conf. High Performance Computing_ . 118–136. 

- [41] Abbas Eslami Kiasari, Zhonghai Lu, and Axel Jantsch. 2013. An Analytical Latency Model for Networks-on-Chip. _IEEE Trans. VLSI Syst._ 21, 1 (2013), 113–123. 

- [42] Hyesoon Kim, Jaekyu Lee, Nagesh B Lakshminarayana, Jaewoong Sim, Jieun Lim, and Tri Pho. 2012. _Macsim: a CPU-GPU heterogeneous simulation framework user guide_ . Technical Report. Georgia Inst. Technol. 1–57 pages. 

- [43] Youngjae Kim, Brendan Tauras, Aayush Gupta, and Bhuvan Urgaonkar. 2009. Flashsim: a simulator for nand flash-based solid-state drives. In _SIMUL ’09_ . 125– 131. 

- [44] Y. Kim, W. Yang, and O. Mutlu. 2015. Ramulator: a fast and extensible DRAM simulator. _IEEE Computer Architecture Letters_ 15, 1 (2015), 45–49. 

- [45] Chao-Lin Lee, Min-Yih Hsu, Bing-Sung Lu, Ming-Yu Hung, and Jenq-Kuen Lee. 2020. Experiment and enabled flow for GPGPU-sim simulators with fixed-point instructions. _J. Syst. Archit._ 111 (2020), 101783. 

- [46] D. Lee, D. Hong, and W. Choi. 2022. MQSim-E: an enterprise SSD simulator. _IEEE Computer Architecture Letters_ 21, 1 (2022), 13–16. 

- [47] Sunwoo Lee, Dipendra Jha, Ankit Agrawal, Alok Choudhary, and Wei-keng Liao. 2017. Parallel deep convolutional neural network training by exploiting the overlapping of computation and communication. In _Proc. IEEE Int’l Conf. High Perform. Comput._ 183–192. 

- [48] M. Leinhauser, J. Young, and S. Bastrakov. 2021. _Performance analysis of PIConGPU: particle-in-cell on GPUs using NVIDIA’s NSight systems and NSight compute_ . Technical Report. Oak Ridge National Laboratory. 

- [49] H. Li, J. Li, and A. Kaufmann. 2022. Simbricks: end-to-end network system evaluation with modular simulation. In _Proc. ACM SIGCOMM Conf._ 380–396. 

- [50] Sheng Li, Jung Ho Ahn, Richard D. Strong, Jay B. Brockman, Dean M. Tullsen, and Norman P. Jouppi. 2009. McPAT: an integrated power, area, and timing modeling framework for multicore and manycore architectures. _MICRO ’09_ (2009), 469–480. 

- [51] Shang Li, Zhiyuan Yang, Dhiraj Reddy, Ankur Srivastava, and Bruce Jacob. 2020. DRAMSim3: a cycle-accurate, thermal-capable DRAM simulator. _IEEE Comput. Archit. Lett._ 19, 2 (2020), 106–109. 

- [52] Xiaoyan Li, Zizheng Dong, and Shuaipeng Li. 2023. MUG5: modeling of universal chiplet interconnect express (UCIe) standard based on gem5. _IEEE Int’l Conf. ASIC_ (2023), 1–4. 

- [53] Jian Liu, Yuxin Chen, and Hao Ding. 2025. CacheSim: a cache simulation framework for evaluating caching algorithms on resource-constrained edge devices. _SoftwareX_ 29 (2025), 102018. 

- [54] Q. Liu, M. Zapater, and D. Atienza. 2025. Gem5-acceSys: enabling system-level exploration of standard interconnects for novel accelerators. _arXiv_ (2025). 

- [55] Jason Lowe-Power, Abdul Mutaal Ahmad, Ayaz Akram, Mohammad Alian, Rico Amslinger, Matteo Andreozzi, Adrià Armejach, Nils Asmussen, Brad Beckmann, Srikant Bharadwaj, et al. 2020. The gem5 simulator: version 20.0+. _arXiv Preprint_ (2020). 

- [56] Jason E Miller, Harshad Kasture, George Kurian, Charles Gruenwald, Nathan Beckmann, Christopher Celio, Jonathan Eastep, and Anant Agarwal. 2010. Graphite: a distributed parallel simulator for multicores. In _Proc. Int’l Symp. High-Perform. Comput. Archit._ 1–12. 

- [57] In Jae Myung. 2003. Tutorial on maximum likelihood estimation. _J. Mathematical Psychology_ 47, 1 (2003), 90–100. 

- [58] J. Power, J. Hestness, and M. S. Orr. 2014. Gem5-gpu: a heterogeneous cpu-gpu simulator. _IEEE Computer Architecture Letters_ 14, 1 (2014), 34–36. 

- [59] Y. M. Qureshi, W. A. Simon, and M. Zapater. 2019. Gem5-x: a gem5-based system level simulation framework to optimize many-core platforms. In _Proc. Simulation Conf._ 1–12. 

- [60] Vishnu Ramadas, Matthew Poremba, Bradford Beckmann, and Matthew D Sinclair. 2024. Simulation support for fast and accurate large-scale GPGPU & accelerator workloads. In _OSCAR ’24_ . 

- [61] Saeed Rashidi, Srinivas Sridharan, Sudarshan Srinivasan, and Tushar Krishna. 2020. Astra-sim: enabling sw/hw co-design exploration for distributed dl training platforms. In _ISPASS ’20_ . 81–92. 

- [62] Steven K Reinhardt, Mark D Hill, James R Larus, Alvin R Lebeck, James C Lewis, and David A Wood. 1993. The wisconsin wind tunnel: Virtual prototyping of parallel computers. In _SIG METRICS ’93_ . 48–60. 

- [63] A. F. Rodrigues, K. S. Hemmert, and B. W. Barrett. 2011. The structural simulation toolkit. _ACM SIGMETRICS Performance Evaluation Review_ 38, 4 (2011), 37–42. 

1360 

MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea 

LEGOSim: A Unified Parallel Simulation Framework for Multi-chiplet Heterogeneous Integration 

- [64] S. Rogers, J. Slycord, and M. Baharani. 2020. Gem5-salam: a system architecture for LLVM-based accelerator modeling. In _Proc. Int’l Symp. Microarch._ 471–482. 

- [65] M. Monchiero J. B. Brockman S. Thoziyoor, J. H. Ahn and N. P. Jouppi. 2008. A comprehensive memory modeling tool and its application to the design and analysis of future memory hierarchies. (2008), 51–62. 

- [66] Ananda Samajdar, Yuhao Zhu, Paul Whatmough, Matthew Mattina, and Tushar Krishna. 2018. Scale-sim: systolic CNN accelerator simulator. _arXiv Preprint_ (2018). 

- [67] D. Sanchez and C. Kozyrakis. 2013. ZSim: fast and accurate microarchitectural simulation of thousand-core systems. _ACM SIGARCH Comput. Archit. News_ 41, 3 (2013), 475–486. 

- [68] Fabian Schätzle, Carlos Falquez, and Stefan Heinen. 2024. Modeling methodology for multi-die chip design based on gem5/SystemC co-simulation. In _Proc. Workshop on Rapid Simul. and Perform. Eval. for Design_ . 35–41. 

- [69] Yakun Sophia Shao, Jason Clemons, Rangharajan Venkatesan, Brian Zimmer, Matthew Fojtik, Nan Jiang, Ben Keller, Alicia Klinefelter, Nathaniel Pinckney, Priyanka Raina, et al. 2019. Simba: scaling deep-learning inference with multichip-module-based architecture. In _Proc. IEEE/ACM Int’l Symp. Microarchitecture_ . 14–27. 

- [70] Debendra Das Sharma, Gerald Pasdast, Zhiguo Qian, and Kemal Aygun. 2022. Universal Chiplet Interconnect Express (UCIe): an open industry standard for innovations with chiplets at package level. _IEEE Trans. Compon. Packag. Manuf. Technol._ 12, 9 (2022), 1423–1431. 

- [71] Chen Sun, Chia-Hsin Owen Chen, George Kurian, Lan Wei, Jason Miller, Anant Agarwal, Li-Shiuan Peh, Stojanovic, and Vladimir. 2012. DSENT - a tool connecting emerging photonics with electronics for opto-Electronic networks-on-Chip modeling. _NOCS ’12_ (2012), 201–210. 

- [72] Yifan Sun, Trinayan Baruah, Saiful A Mojumder, Shi Dong, Xiang Gong, Shane Treadway, Yuhui Bao, Spencer Hance, Carter McCardwell, Vincent Zhao, et al. 2019. MGPUSim: enabling multi-GPU performance modeling and optimization. In _Proc. Int’l Symp. Comput. Archit._ 197–209. 

- [73] Rafael Ubal, Byunghyun Jang, Perhaad Mistry, Dana Schaa, and David Kaeli. 2012. Multi2Sim: a simulation framework for CPU-GPU computing. In _Proc. Int’l Conf. Parallel Archit. Compil. Tech._ 335–344. 

- **Program:** C++, CUDA C++, python. 

- **Compilation:** GCC 7.5, CUDA 4 to 11, CMake 3.26.3. 

- **Run-time environment:** Ubuntu 18.04.6. 

- **Metrics:** Simulation Time, Simulation Cycle, Inter-chiplet Communication Traffic, Communication Cycle, Computation Cycle. 

- **Output:** Simulation log files, bottleneck analysis log files and interchiplet traffic heat map pictures. 

- **Experiments:** Generate experiments using supplied scripts. 

- **How much disk space required (approximately)?:** 16GB. 

- **How much time is needed to prepare workflow (approximately)?:** Two hours. 

- **How much time is needed to complete experiments (approximately)?:** 14 days. 

- **Publicly available?:** Yes 

- **Archived (provide DOI)?:** https://doi.org/10.5281/zenodo.16886879 

## **A.3 Description** 

_A.3.1 How to access._ The artifact is uploaded to GitHub [7] and Zenodo https://doi.org/10.5281/zenodo.16886879 

_A.3.2 Software dependencies._ CUDA 4 to 11, GCC 7.5, CMake 3.26.3, Python 3.11, libtorch 2.0.0+cpu, zlib1g-dev, libbz2-dev, libboostdev, libsqlite3-dev, xutils-dev, bison, flex, libgl1-mesa-dev, libglu1mesa-dev, libboost-all-dev. Other software dependencies depend on related simulators and benchmarks. 

- [74] A. Varga. 2010. _OMNeT++_ . Springer Berlin Heidelberg, 35–59. 

- [75] Jun Wang, Jesse Beu, Rishiraj Bheda, Tom Conte, Zhenjiang Dong, Chad Kersey, Mitchelle Rasquinha, George Riley, William Song, He Xiao, and other. 2014. Manifold: a parallel simulation framework for multicore systems. In _Proc. IEEE Int’l Symp. Perform. Anal. Syst. Softw._ 106–115. 

- [76] Xizheng Wang, Qingxu Li, Yichi Xu, Gang Lu, Dan Li, Li Chen, Heyang Zhou, Linkang Zheng, Sen Zhang, Yikai Zhu, et al. 2025. SimAI: unifying Architecture Design and Performance Tuning for Large-Scale Large Language Model Training with Scalability and Precision. In _NSDI ’25_ . 541–558. 

- [77] X. Wang, M. Xu, A. K. Singh, Y. Jiang, and M. Yang. 2025. On optimizing inter-and intra-chiplet interconnection topologies for robust multi-chiplet systems. _IEEE Trans. Computer-Aided Design of Integrated Circuits and Systems_ (2025). 

- [78] Sheng Xu, Xiaoming Chen, Ying Wang, Yinhe Han, Xuehai Qian, and Xiaowei Li. 2018. PIMSim: a flexible and detailed processing-in-memory simulator. _IEEE Computer Architecture Letters_ 18, 1 (2018), 6–9. 

- [79] Yinglin Yang, Yunzhengmao Wang, Tengyue Yi, Chixiao Chen, and Qi Liu. 2024. A 6.4-Gbps 0.41-pJ/b fully-digital die-to-die interconnect PHY for silicon interposer based 2.5D integration. _Integration_ (2024), 102170. 

- [80] Bingyi Ye, Kai Sheng, and Weixin Gai. 2023. A 2.29-pJ/b 112-Gb/s wireline transceiver with RX Four-Tap FFE for Medium-Reach applications in 28-nm CMOS. _IEEE J. Solid-State Circuits_ 58, 1 (2023), 19–29. 

- [81] H. Zhang. 2018. Distributed deep learning training with Horovod. _arXiv_ (2018). 

- [82] Zhenhua Zhu, Hanbo Sun, Tongxin Xie, Yu Zhu, Guohao Dai, Lixue Xia, Dimin Niu, Xiaoming Chen, Xiaobo Sharon Hu, Yu Cao, et al. 2023. MNSIM 2.0: a behavior-level modeling tool for processing-in-memory architectures. _IEEE Trans. Comput.-Aided Design Integr. Circuits Syst._ 42, 11 (2023), 4112–4125. 

- [83] L. Zuolo, C. Zambelli, and R. Micheloni. 2017. SSDexplorer: a virtual platform for SSD simulations. _Solid-State-Drives (SSDs) Modeling: Simulation Tools & Strategies_ (2017), 41–65. 

## **A Artifact Appendix** 

## **A.1 Abstract** 

The artifact comprises the source code for the unified parallel simulation framework for multi-chiplet heterogeneous integration along with necessary scripts and instructions to reproduce the key functions introduced in the case studies. 

## **A.2 Artifact check-list (meta-information)** 

- **Algorithm:** On-Demand Synchronization Mechanism. 

## **A.4 Installation** 

- (1) Clone the repository from GitHub. 

git clone https://github.com/FCAS-LAB/LEGOSIM _MICRO.git (2) Initialize and update submodules. git submodule init git submodule update (3) Run script to initialize environment variables. source setup_env.sh Success will show: setup_environment succeeded. (4) Apply modifications to snipersim, gpgpu-sim, Gem5 and popnet code. ./apply_patch.sh (5) Compile and install snipersim. cd snipersim make -j4 (6) Compile and install Gem5. Check Gem5 documentation for detailed installation guide. LegoSim can run X86 and ARM architecture simulations. cd gem5 scons build/X86/gem5.opt or cd gem5 scons build/ARM/gem5.opt 

(7) Compile and install GPGPUSim. 

1361 

Tiantian Lin, Cheng Qiu, Xiaohang Wang, Ling Wang, Zhulin Zheng, Yingtao Jiang, Amit Kumar Singh, Jieming Yin, Sihai Qiu, Xiaodong Li, Xin Tang, Jie Song, Mingzhe Zhang, MICRO ’25, October 18–22, 2025, Seoul, Republic of Korea and Kui Ren 

- cd gpgpu-sim make -j4 

- (8) Compile and install popnet. cd popnet_chiplet mkdir build cd build cmake .. make -j4 

- (9) Compile and install inter-chiplet communication program. cd interchiplet mkdir build cd build cmake .. make 

## **A.5 Experiment workflow** 

- (1) Run multi-chiplet system with different topologies and flit sizes. To run the multi-chiplet system with different topologies, you can use the provided script run.sh in the directory of each benchmark. This script will iterate through various topologies and flit sizes, applying necessary modifications to the configuration files. 

   - BFS: 

cd bfs_cuda bash run.sh 

- Matmul: cd matmul bash run.sh 

• MLP: cd mlp bash run.sh 

- Transformer: As the transformer benchmark was built with the libtorch library, libtorch 2.0.0+cpu and gcc/g++ 9.4.0 or higher are required. You can set the compiler in the CMakeLists.txt fle as follows: set(CMAKE_PREFIX_PATH "<LibTorch path>") # In CMakeLists.txt, change the compiler to # gcc-9 # and g++-9 set(CMAKE_C_COMPILER "<gcc-9.4.0 path>/bin/ gcc") 

set(CMAKE_CXX_COMPILER "<gcc-9.4.0 path>/bin/ g++") 

Then, compile the Transformer to test the environment: cd transformer mkdir build cd build cmake .. make 

To run the transformer benchmark with different topologies and flit sizes, use the following command: cd .. bash run.sh 

- (2) Run multi-chiplet system with different inter-chiplet communication protocols (PCIe, UCIe). To run the multi-chiplet system with different inter-chiplet communication protocols, you can enter the UCIe_PCIe directory and execute the run.sh script. This script will iterate through the different protocols and apply the necessary modifications to the configuration files. cd UCIe_PCIe bash run.sh 

- (3) Run multi-chiplet system with different storage configurations (DDR5, HBM3). To run the multi-chiplet system with different storage configurations, you can enter the HBM_DDR directory and execute the run.sh script. This script will iterate through the different storage configurations and apply the necessary modifications to the configuration fles. cd HBM_DDR bash run.sh 

- (4) Analyze synchronization overhead. python sync_overhead.py 

- (5) Exploring the Design Space of On-chip Buffer and Interchiplet Interconnection Network. cd DSE bash run.sh 

## **A.6 Evaluation and expected results** 

The output of each benchmark will be stored in the result_[topology] _flit_[flit_size].log files and the smulation cycle will be stored in the result_[topology]_flit_[flit_size].txt files. You can analyze these results to compare the performance of different configurations. In addition, every simulation will generate a heat map that visualizes the inter-chiplet traffic distributions of each benchmark. The computation or communication bottleneck of each chiplet will be stored in the bottleneck_[topology]_flit_[flit_size].log files. The thoexpected results are listed in the results directory. Figure 10 can be obtained through running the sync_overhead.py python file, and Figure 13 and 15 can be generated through running the run.sh in the DSE directory. 

## **A.7 Experiment customization** 

LEGOSim can simulate different kinds of heterogeneous multichiplet systems. Researchers can follow the methodology of LEGOSim in the user manual document [8], to add a new benchmark to the LEGOSim. 

1362 

