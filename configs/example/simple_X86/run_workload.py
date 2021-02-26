# -*- coding: utf-8 -*-
# Copyright (c) 2019 The Regents of the University of California.
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met: redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer;
# redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution;
# neither the name of the copyright holders nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Authors: Jason Lowe-Power, Ayaz Akram, Hoa Nguyen
# Modified by Wenqi Yin

""" Script to run a Custom workloads and sample performance in full system
    mode with gem5.

    The script control the simulation to boot linux, fast-forward initial
    ticks/instruction specified by user and taking samples. For each sample,
    it warmUp the test system with configurable tick/inst with atomic CPU,
    then switch to o3 and collect stats. After it use kvm to FF the period
    between two samples and collect the next sample.

    Inputs:
    * This script expects the following as arguments:
        ** kernel:
                  This is a positional argument specifying the path to
                  vmlinux.
        ** disk:
                  This is a positional argument specifying the path to the
                  disk image containing the installed benchmarks.
        ** cpuNum:
                  This is a positional argument specifying the name of the
                  detailed CPU model.
        ** skip_period:
                  This is a positional argument specifying the number of
                  initial tick/inst before taking samples
        ** warm_period:
                  This is a positional argument specifying the number of
                  warming up tick/inst with atomic CPU
        ** sim_period:
                  This is a positional argument specifying number of tick/inst
                  to simulate with o3 cpu
        ** sampleInterval:
                  number of ticks/inst between samples
        ** numSamples:
                  The number of samples to take
        ** --time_in_inst:
                  This is an optional argument, if given, all the number
                  specified above are in unit of instructions,
                  otherwise in ticks

"""

import os
import sys

import m5
import m5.ticks
from m5.objects import *

import argparse
import pdb
#import ipdb

from system import MySystem

def parse_arguments():
    parser = argparse.ArgumentParser(description=
                                "gem5 config file to run custom workloads")
    parser.add_argument("kernel", type = str, help = "Path to vmlinux")
    parser.add_argument("disk", type = str,
                  help = "Path to the disk image containing SPEC benchmarks")
    parser.add_argument("cpuNum", type = int, help = "Number of CPU cores")
    parser.add_argument("skip_period", type = int,
            help = "Number of initial tick/insts to skip before sampling")
    parser.add_argument("warmup_period", type = int,
            help = "Number of ticks/insts for warming up before detailed sim")
    parser.add_argument("sim_period", type = int,
            help = "Number of ticks/insts for detailed simulation")
    parser.add_argument("sampleInterval", type = int,
            help = "Number of ticks/insts between two samples")
    parser.add_argument("numSamples", type = int,
            help = "total number of samples")
    parser.add_argument("--time_in_inst", default = False,
            action = "store_true",
            help = "Use insts as unit of time, default is tick")

    #parser.add_argument("-d", "--ckpt-dir", type = str,
    #                    default = "checkpoints",
    #                    help = "Path for storing checkpoints")
    #parser.add_argument("-l", "--no-copy-logs", default = False,
    #                    action = "store_true",
    #                    help = "Not copy SPEC run logs to the host system;"
    #                           "Logs are copied by default")
    #parser.add_argument("-z", "--allow-listeners", default = False,
    #                    action = "store_true",
    #                    help = "Turn on ports;"
    #                           "The ports are off by default")

    return parser.parse_args()

def getDetailedCPUModel(cpu_name):
    '''
    Return the CPU model corresponding to the cpu_name.
    '''
    available_models = {"kvm": X86KvmCPU,
                        "o3": DerivO3CPU,
                        "atomic": AtomicSimpleCPU,
                        "timing": TimingSimpleCPU
                       }
    try:
        available_models["FlexCPU"] = FlexCPU
    except NameError:
        # FlexCPU is not defined
        pass
    # https://docs.python.org/3/library/stdtypes.html#dict.get
    # dict.get() returns None if the key does not exist
    return available_models.get(cpu_name)


def create_system(linux_kernel_path, disk_image_path,
        detailed_cpu_model, cpu_num):
    # create the system we are going to simulate
    system = MySystem(kernel = linux_kernel_path,
                      disk = disk_image_path,
                      num_cpus = cpu_num,
                      no_kvm = False,
                      TimingCPUModel = detailed_cpu_model)

    # For workitems to work correctly
    # This will cause the simulator to exit simulation when the first work
    # item is reached and when the first work item is finished.
    system.work_begin_exit_count = 1
    system.work_end_exit_count = 1

    # set up the root SimObject and start the simulation
    root = Root(full_system = True, system = system)

    if system.getHostParallel():
        # Required for running kvm on multiple host cores.
        # Uses gem5's parallel event queue feature
        # Note: The simulator is quite picky about this number!
        root.sim_quantum = int(1e9) # 1 ms

    return root, system



def runCpu(period, tick_mode, currentCPU, ctrl_cpu_index=0):
    #unit of period is tick
    if tick_mode:
        exit_event = m5.simulate(period)
        exit_cause = exit_event.getCause()
        success = exit_cause == "simulate() limit reached"
    #unit of period is inst
    else:
        currentCPU[ctrl_cpu_index].scheduleInstStop(0, period,
                "Max Insts reached CPU %d" %(ctrl_cpu_index))
        pri_count = currentCPU[ctrl_cpu_index].totalInsts()
        exit_event = m5.simulate()
        exit_cause = exit_event.getCause()
        #success = exit_cause == "a thread reached the max instruction count"
        success = exit_cause.startswith("Max Insts")
        post_count = currentCPU[ctrl_cpu_index].totalInsts()
        print("DEBUG: insts simed this interval %d" %(post_count - pri_count))

    return success, exit_cause


if __name__ == "__m5_main__":
    args = parse_arguments()

    #cpu_name = args.cpuType
    cpu_name = "o3"
    cpu_num = args.cpuNum
    linux_kernel_path = args.kernel
    disk_image_path = args.disk
    #no_copy_logs = args.no_copy_logs
    #allow_listeners = args.allow_listeners
    skip_period = args.skip_period
    sample_interval = args.sampleInterval
    warmUp_period = args.warmup_period
    sim_period = args.sim_period
    num_sample = args.numSamples
    #cptdir = args.ckpt_dir
    tick_mode = not args.time_in_inst

    output_dir = os.path.join(m5.options.outdir, "ckptCollection")

    print("===============================================")
    print("Simulation Configuration:")
    if tick_mode:
        print("Number unit in ticks")
    else:
        print("Number unit in instructions")
    print("Skip initial: %d" %(skip_period))
    print("Number of samples: %d" %(num_sample))
    print("Warmup period for each sample: %d" %(warmUp_period))
    print("Detailed period for each sample: %d" %(sim_period))
    print("Period between samples: %d" %(sample_interval))
    print("===============================================")

    #force to use o3 now
    detailed_cpu = DerivO3CPU

    root, system = create_system(linux_kernel_path, disk_image_path,
                                 detailed_cpu, cpu_num)

    # needed for long running jobs
    #if not allow_listeners:
    #    m5.disableAllListeners()

    # instantiate all of the objects we've created above
    m5.instantiate()
    pdb.set_trace()
    # booting linux. Precond: kvmcpu
    exit_event = m5.simulate()
    exit_cause = exit_event.getCause()
    success = exit_cause == "m5_exit instruction encountered"
    if not success:
        print("Error while booting linux: {}".format(exit_cause))
        exit(1)
    print("Booting done")

    #skip initial . Precond: kvmcpu
    success, exit_cause = runCpu(skip_period, tick_mode, system.cpu)
    if not success:
        print("Error while skipping initial cycles: {}".format(exit_cause))
        exit(1)
    print("Initial skip done")


    ## reset stats
    #print("Reset stats")
    #m5.stats.reset()

#    # switch from KVM to detailed CPU
#    if not cpu_name == "kvm":
#        print("Switching to detailed CPU: " + cpu_name)
#        system.switchCpus(system.cpu, system.detailed_cpu)
#        print("Switching done")

    # Main Sampling Loop, precond: kvmcpu
    for i in range(num_sample):
        system.switchCpus(system.cpu, system.atomicCpu)
        print("Start sample " + str(i) +", warming up")
        success,exit_cause = runCpu(warmUp_period, tick_mode, system.atomicCpu)
        if not success:
            print("Error while warmup simulation: {}".format(exit_cause))
            exit(1)


        print("warmup done, entering detailed sim")

        system.switchCpus(system.atomicCpu, system.detailed_cpu)
        m5.stats.reset()
        success, exit_cause = runCpu(sim_period, tick_mode,
                                     system.detailed_cpu)
        if not success:
            print("Error in detailed simulation: {}".format(exit_cause))
            exit(1)
        m5.stats.dump()

        print("Detailed sim done")

        system.switchCpus(system.detailed_cpu, system.cpu)
        success, exit_cause = runCpu(sample_interval, tick_mode, system.cpu)
        if not success:
            print("Error while FF between samples: {}".format(exit_cause))
            exit(1)

    print("Simulation Done, Exiting")




    #success, exit_cause = run_spec_benchmark(sample_period)

    #num_ckpt = 0
    #while True:
    #    success, exit_cause = nextInterval()
    #    if exit_cause == "m5_exit instruction encountered":
    #        break
    #    else:
    #        #dump checkpoint
    #        m5.checkpoint(os.path.join(cptdir, "ckpt.", str(num_ckpt)))
    #        num_ckpt += 1

    # running benchmark
    #print("Benchmark: {}; Size: {}".format(benchmark_name, benchmark_size))
    #success, exit_cause = run_spec_benchmark()

    # output the stats after the benchmark is complete
    #print("Output stats")
    #m5.stats.dump()

    #if not no_copy_logs:
    #    # create the output folder
    #    os.makedirs(output_dir)

    #    # switch from detailed CPU to KVM
    #    if not cpu_name == "kvm":
    #        print("Switching to KVM")
    #        system.switchCpus(system.detailed_cpu, system.cpu)
    #        print("Switching done")
    #
    #    # copying logs
    #    success, exit_cause = copy_spec_logs()
