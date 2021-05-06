""" Pickup the ckpt dumped before and run detailed simulation

    This script is to use with pre-dumped checkpoints, see dump_ckpt.py
    to see how to generate checkpoints

    Inputs:
    * This script expects the following as arguments:
        ** kernel:
                  This is a positional argument specifying the path to
                  vmlinux.
        ** disk:
                  This is a positional argument specifying the path to the
                  disk image containing the installed benchmarks.
        ** cpuNum:
                  This is a positional argument specifying the number of the
                  detailed CPU model. WARNING: need to be consistent with
                  the model used to generate checkpoints
        ** warmup_period:
                  This is a positional argument specifying the number of
                  warming up tick/inst with atomic CPU
        ** sim_period:
                  This is a positional argument specifying number of tick/inst
                  to simulate with o3 cpu
        ** --period_in_tick:
                  This is an optional argument, if given, all the number
                  specified above are in unit of tick. By default the unit
                  is instruction

"""

import os
import sys

import m5
import m5.ticks
from m5.objects import *

import argparse
import pdb

from system import MySystem

def parse_arguments():
    parser = argparse.ArgumentParser(description=
                                "gem5 config file to run custom workloads")
    parser.add_argument("ckpt_dir", type = str,
                        help = "Path to find checkpoints")
    parser.add_argument("kernel", type = str, help = "Path to vmlinux")
    parser.add_argument("disk", type = str,
                  help = "Path to the disk image containing SPEC benchmarks")
    parser.add_argument("cpuNum", type = int, help = "Number of CPU cores")
    parser.add_argument("warmup_period", type = int,
            help = "Number of ticks/insts for warming up before detailed sim")
    parser.add_argument("sim_period", type = int,
            help = "Number of ticks/insts for detailed simulation")
    parser.add_argument("--period_in_tick", default = False,
            action = "store_true",
            help = "Use insts as unit of time, default is tick")
    parser.add_argument("--detailed_warmup", default = False,
            action = "store_true",
            help = "Use O3CPU for warming up, instead of atomic CPU")
    parser.add_argument("--l3size", type = str, help = "L3 size in MB")
    parser.add_argument("--l3assoc", type = int, help = "L3 associativity")

    return parser.parse_args()



def create_system(linux_kernel_path, disk_image_path,
        detailed_cpu_model, cpu_num, args):
    # create the system we are going to simulate
    system = MySystem(kernel = linux_kernel_path,
                      disk = disk_image_path,
                      num_cpus = cpu_num,
                      no_kvm = False,
                      TimingCPUModel = detailed_cpu_model,
                      config_args = args)

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

    cpu_num = args.cpuNum
    linux_kernel_path = args.kernel
    disk_image_path = args.disk
    #no_copy_logs = args.no_copy_logs
    #allow_listeners = args.allow_listeners
    warmUp_period = args.warmup_period
    sim_period = args.sim_period
    cptdir = args.ckpt_dir
    tick_mode = args.period_in_tick
    detailed_warmup = args.detailed_warmup

    output_dir = os.path.join(m5.options.outdir, "ckptCollection")

    print("===============================================")
    print("Simulation Configuration:")
    if tick_mode:
        print("Number unit in ticks")
    else:
        print("Number unit in instructions")
    print("Warmup period for each sample: %d" %(warmUp_period))
    print("Detailed period for each sample: %d" %(sim_period))
    print("===============================================")


    root, system = create_system(linux_kernel_path, disk_image_path,
                                 DerivO3CPU, cpu_num, args)

    #for rsC
    system.readfile = "test.rcS"
    # needed for long running jobs
    #if not allow_listeners:
    #    m5.disableAllListeners()

    # instantiate all of the objects we've created above
    m5.instantiate(cptdir)


    print('\033[32m' + "Start Warming Up" + '\033[m')
    if detailed_warmup:
        system.switchCpus(system.cpu, system.detailed_cpu)
        success,exit_cause = runCpu(warmUp_period,
                                    tick_mode,
                                    system.detailed_cpu)
    else:
        system.switchCpus(system.cpu, system.atomicCpu)
        success,exit_cause = runCpu(warmUp_period, tick_mode,
                                    system.atomicCpu)

    if not success:
        print("Error while warmup simulation: {}".format(exit_cause))
        exit(1)
    print('\033[32m' + "warmup done, entering detailed sim" + '\033[m')

    if not detailed_warmup:
        system.switchCpus(system.atomicCpu, system.detailed_cpu)

    m5.stats.reset()
    success, exit_cause = runCpu(sim_period, tick_mode,
                                 system.detailed_cpu)
    if not success:
        print("Error in detailed simulation: {}".format(exit_cause))
        exit(1)
    m5.stats.dump()
    print('\033[32m' + "Detailed sim done" + '\033[m')

    print('\033[33m' + "Simulation Done, Exiting" + '\033[m')

