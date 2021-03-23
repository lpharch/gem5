""" Script to use kvm dumpping checkpoints

    The script control the simulation to boot linux, fast-forward to the
    user-specified location (in 100M inst, usually come from simpoint file),
    and dump checkpoints.

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
        ** rcS:
                  Startup script to run after booting, usually do m5 exit
                  and then run the workload (pinned on core 0)
        ** ckpt_pos:
                  checkpoint postion in unit of 100M instructions. Passed
                  in as a string: "pos0 pos1 pos2 ...."
        ** -d:
                  Optional specify a directory for output checkpoint, if
                  not specified, the checkpoints will be dumpped at the
                  location where gem5 output the stats.
"""

import os
import sys

import m5
import m5.ticks
from m5.objects import *

import argparse

from system import MySystem

def parse_arguments():
    parser = argparse.ArgumentParser(description=
                                "gem5 config file to dump checkpoints")
    parser.add_argument("kernel", type = str, help = "Path to vmlinux")
    parser.add_argument("disk", type = str,
                  help = "Path to the disk image containing workloads")
    parser.add_argument("cpuNum", type = int, help = "Number of CPU cores")
    parser.add_argument("rcS", type = str, help = "path to rcs file")
    parser.add_argument("ckpt_pos", type = str,
                  help = "Instruction postions to take ckpt, in 100M Inst")
    parser.add_argument("-d", "--ckpt_dir", type = str,
                        help = "Path for storing checkpoints")

    return parser.parse_args()


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

    cpu_num = args.cpuNum
    linux_kernel_path = args.kernel
    disk_image_path = args.disk
    launch_script = args.rcS
    cptdir = args.ckpt_dir
    ckpt_string = args.ckpt_pos


    ckpt_pos = [int(p) for p in ckpt_string.split()]
    ckpt_pos.sort()
    num_ckpts = len(ckpt_pos)
    ckpt_index = 0
    ckpt_unit = 100000000

    if not cptdir:
        if m5.options.outdir:
            cptdir = m5.options.outdir
        else:
            cptdir = getcwd()


    detailed_cpu = DerivO3CPU
    root, system = create_system(linux_kernel_path, disk_image_path,
                                 detailed_cpu, cpu_num)
    system.readfile = launch_script

    # Necessary for startup script to run successfully, otherwise the
    # gem5.service may fail
    m5.disableAllListeners()


    # instantiate all of the objects we've created above
    m5.instantiate()

    # booting linux. Precond: kvmcpu
    exit_event = m5.simulate()
    exit_cause = exit_event.getCause()
    success = exit_cause == "m5_exit instruction encountered"
    if not success:
        print("Error while booting linux: {}".format(exit_cause))
        exit(1)
    print('\033[32m' + "Booting done" + '\033[m')


    #Start to collect ckpts
    simed_inst = 0
    for i in range(num_ckpts):
        success, exit_cause = runCpu((ckpt_pos[i] - simed_inst)*ckpt_unit,
                                     False, system.cpu)
        if not success:
            print("error")
            exit(-1)
        simed_inst = ckpt_pos[i]
        print("\033[32m" + "Dump ckpt " + str(i) + " at " +
              str(system.totalInsts())+"\033[m")
        ckpt_name = os.path.join(cptdir, "ckpt_"+str(i))
        m5.checkpoint(ckpt_name)

