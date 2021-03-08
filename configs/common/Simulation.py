# Copyright (c) 2011-2013 ARM Limited
# All rights reserved
#
# The license below extends only to copyright in the software and shall
# not be construed as granting a license to any other intellectual
# property including but not limited to intellectual property relating
# to a hardware implementation of the functionality of the software
# licensed hereunder.  You may use the software subject to the license
# terms below provided that you ensure that this notice is replicated
# unmodified and in its entirety in all distributions of the software,
# modified or unmodified, in source code or in binary form.
#
# Copyright (c) 2006-2008 The Regents of The University of Michigan
# Copyright (c) 2010 Advanced Micro Devices, Inc.
# All rights reserved.
#
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

from __future__ import print_function
from __future__ import absolute_import

import six
import sys
from os import getcwd
from os.path import join as joinpath

from common import CpuConfig
from common import ObjectList

import m5
from m5.defines import buildEnv
from m5.objects import *
from m5.util import *

import ipdb

if six.PY3:
    long = int

addToPath('../common')

def getCPUClass(cpu_type):
    """Returns the required cpu class and the mode of operation."""
    cls = ObjectList.cpu_list.get(cpu_type)
    return cls, cls.memory_mode()

def setCPUClass(options):
    """Returns two cpu classes and the initial mode of operation.

       Restoring from a checkpoint or fast forwarding through a benchmark
       can be done using one type of cpu, and then the actual
       simulation can be carried out using another type. This function
       returns these two types of cpus and the initial mode of operation
       depending on the options provided.
    """

    TmpClass, test_mem_mode = getCPUClass(options.cpu_type)
    CPUClass = None
    if TmpClass.require_caches() and \
            not options.caches and not options.ruby:
        fatal("%s must be used with caches" % options.cpu_type)

    if options.checkpoint_restore != None:
        if options.restore_with_cpu != options.cpu_type:
            CPUClass = TmpClass
            TmpClass, test_mem_mode = getCPUClass(options.restore_with_cpu)
    elif options.fast_forward:
        CPUClass = TmpClass
        #TmpClass = AtomicSimpleCPU
        test_mem_mode = 'atomic_noncaching'
        TmpClass = X86KvmCPU

    # Ruby only supports atomic accesses in noncaching mode
    if test_mem_mode == 'atomic' and options.ruby:
        warn("Memory mode will be changed to atomic_noncaching")
        test_mem_mode = 'atomic_noncaching'

    return (TmpClass, test_mem_mode, CPUClass)

def setMemClass(options):
    """Returns a memory controller class."""

    return ObjectList.mem_list.get(options.mem_type)

def setWorkCountOptions(system, options):
    if options.work_item_id != None:
        system.work_item_id = options.work_item_id
    if options.num_work_ids != None:
        system.num_work_ids = options.num_work_ids
    if options.work_begin_cpu_id_exit != None:
        system.work_begin_cpu_id_exit = options.work_begin_cpu_id_exit
    if options.work_end_exit_count != None:
        system.work_end_exit_count = options.work_end_exit_count
    if options.work_end_checkpoint_count != None:
        system.work_end_ckpt_count = options.work_end_checkpoint_count
    if options.work_begin_exit_count != None:
        system.work_begin_exit_count = options.work_begin_exit_count
    if options.work_begin_checkpoint_count != None:
        system.work_begin_ckpt_count = options.work_begin_checkpoint_count
    if options.work_cpus_checkpoint_count != None:
        system.work_cpus_ckpt_count = options.work_cpus_checkpoint_count

def findCptDir(options, cptdir, testsys):
    """Figures out the directory from which the checkpointed state is read.

    There are two different ways in which the directories holding checkpoints
    can be named --
    1. cpt.<benchmark name>.<instruction count when the checkpoint was taken>
    2. cpt.<some number, usually the tick value when the checkpoint was taken>

    This function parses through the options to figure out which one of the
    above should be used for selecting the checkpoint, and then figures out
    the appropriate directory.
    """

    from os.path import isdir, exists
    from os import listdir
    import re
    #ipdb.set_trace()
    if not isdir(cptdir):
        fatal("checkpoint dir %s does not exist!", cptdir)

    cpt_starttick = 0
    if options.at_instruction or options.simpoint:
        inst = options.checkpoint_restore
        if options.simpoint:
            # assume workload 0 has the simpoint
            if testsys.cpu[0].workload[0].simpoint == 0:
                fatal('Unable to find simpoint')
            inst += int(testsys.cpu[0].workload[0].simpoint)

        checkpoint_dir = joinpath(cptdir, "cpt.%s.%s" % (options.bench, inst))
        if not exists(checkpoint_dir):
            fatal("Unable to find checkpoint directory %s", checkpoint_dir)

    elif options.restore_simpoint_checkpoint:
        # Restore from SimPoint checkpoints
        # Assumes that the checkpoint dir names are formatted as follows:
        dirs = listdir(cptdir)
        expr = re.compile('cpt\.simpoint_(\d+)_inst_(\d+)' +
                    '_weight_([\d\.e\-]+)_interval_(\d+)_warmup_(\d+)')
        cpts = []
        for dir in dirs:
            match = expr.match(dir)
            if match:
                cpts.append(dir)
        cpts.sort()

        cpt_num = options.checkpoint_restore
        if cpt_num > len(cpts):
            fatal('Checkpoint %d not found', cpt_num)
        checkpoint_dir = joinpath(cptdir, cpts[cpt_num - 1])
        match = expr.match(cpts[cpt_num - 1])
        if match:
            index = int(match.group(1))
            start_inst = int(match.group(2))
            weight_inst = float(match.group(3))
            interval_length = int(match.group(4))
            warmup_length = int(match.group(5))
        print("Resuming from", checkpoint_dir)
        simpoint_start_insts = []
        simpoint_start_insts.append(warmup_length)
        simpoint_start_insts.append(warmup_length + interval_length)
        #testsys.cpu[0].simpoint_start_insts = simpoint_start_insts
        #if testsys.switch_cpus != None:
        #    testsys.switch_cpus[0].simpoint_start_insts = simpoint_start_insts

        print("Resuming from SimPoint", end=' ')
        print("#%d, start_inst:%d, weight:%f, interval:%d, warmup:%d" %
            (index, start_inst, weight_inst, interval_length, warmup_length))

    else:
        dirs = listdir(cptdir)
        expr = re.compile('cpt\.([0-9]+)')
        cpts = []
        for dir in dirs:
            match = expr.match(dir)
            if match:
                cpts.append(match.group(1))

        cpts.sort(key = lambda a: long(a))

        cpt_num = 1 if options.restore_manual else options.checkpoint_restore

        if cpt_num > len(cpts):
            fatal('Checkpoint %d not found', cpt_num)

        cpt_starttick = int(cpts[cpt_num - 1])
        checkpoint_dir = joinpath(cptdir, "cpt.%s" % cpts[cpt_num - 1])

    return cpt_starttick, checkpoint_dir

def scriptCheckpoints(options, maxtick, cptdir):
    if options.at_instruction or options.simpoint:
        checkpoint_inst = int(options.take_checkpoints)

        # maintain correct offset if we restored from some instruction
        if options.checkpoint_restore != None:
            checkpoint_inst += options.checkpoint_restore

        print("Creating checkpoint at inst:%d" % (checkpoint_inst))
        exit_event = m5.simulate()
        exit_cause = exit_event.getCause()
        print("exit cause = %s" % exit_cause)

        # skip checkpoint instructions should they exist
        while exit_cause == "checkpoint":
            exit_event = m5.simulate()
            exit_cause = exit_event.getCause()

        if exit_cause == "a thread reached the max instruction count":
            m5.checkpoint(joinpath(cptdir, "cpt.%s.%d" % \
                    (options.bench, checkpoint_inst)))
            print("Checkpoint written.")

    else:
        when, period = options.take_checkpoints.split(",", 1)
        when = int(when)
        period = int(period)
        num_checkpoints = 0

        exit_event = m5.simulate(when - m5.curTick())
        exit_cause = exit_event.getCause()
        while exit_cause == "checkpoint":
            exit_event = m5.simulate(when - m5.curTick())
            exit_cause = exit_event.getCause()

        if exit_cause == "simulate() limit reached":
            m5.checkpoint(joinpath(cptdir, "cpt.%d"))
            num_checkpoints += 1

        sim_ticks = when
        max_checkpoints = options.max_checkpoints

        while num_checkpoints < max_checkpoints and \
                exit_cause == "simulate() limit reached":
            if (sim_ticks + period) > maxtick:
                exit_event = m5.simulate(maxtick - sim_ticks)
                exit_cause = exit_event.getCause()
                break
            else:
                exit_event = m5.simulate(period)
                exit_cause = exit_event.getCause()
                sim_ticks += period
                while exit_event.getCause() == "checkpoint":
                    exit_event = m5.simulate(sim_ticks - m5.curTick())
                if exit_event.getCause() == "simulate() limit reached":
                    m5.checkpoint(joinpath(cptdir, "cpt.%d"))
                    num_checkpoints += 1

    return exit_event

def benchCheckpoints(options, maxtick, cptdir):
    exit_event = m5.simulate(maxtick - m5.curTick())
    exit_cause = exit_event.getCause()

    num_checkpoints = 0
    max_checkpoints = options.max_checkpoints

    while exit_cause == "checkpoint":
        m5.checkpoint(joinpath(cptdir, "cpt.%d"))
        num_checkpoints += 1
        if num_checkpoints == max_checkpoints:
            exit_cause = "maximum %d checkpoints dropped" % max_checkpoints
            break

        exit_event = m5.simulate(maxtick - m5.curTick())
        exit_cause = exit_event.getCause()

    return exit_event

# Set up environment for taking SimPoint checkpoints
# Expecting SimPoint files generated by SimPoint 3.2
def parseSimpointAnalysisFile(options, testsys):
    import re

    simpoint_filename, weight_filename, interval_length, warmup_length = \
        options.take_simpoint_checkpoints.split(",", 3)
    print("simpoint analysis file:", simpoint_filename)
    print("simpoint weight file:", weight_filename)
    print("interval length:", interval_length)
    print("warmup length:", warmup_length)

    interval_length = int(interval_length)
    warmup_length = int(warmup_length)

    # Simpoint analysis output starts interval counts with 0.
    simpoints = []
    simpoint_start_insts = []

    # Read in SimPoint analysis files
    simpoint_file = open(simpoint_filename)
    weight_file = open(weight_filename)
    while True:
        line = simpoint_file.readline()
        if not line:
            break
        m = re.match("(\d+)\s+(\d+)", line)
        if m:
            interval = int(m.group(1))
        else:
            fatal('unrecognized line in simpoint file!')

        line = weight_file.readline()
        if not line:
            fatal('not enough lines in simpoint weight file!')
        m = re.match("([0-9\.e\-]+)\s+(\d+)", line)
        if m:
            weight = float(m.group(1))
        else:
            fatal('unrecognized line in simpoint weight file!')

        if (interval * interval_length - warmup_length > 0):
            starting_inst_count = \
                interval * interval_length - warmup_length
            actual_warmup_length = warmup_length
        else:
            # Not enough room for proper warmup
            # Just starting from the beginning
            starting_inst_count = 0
            actual_warmup_length = interval * interval_length

        simpoints.append((interval, weight, starting_inst_count,
            actual_warmup_length))

    # Sort SimPoints by starting inst count
    simpoints.sort(key=lambda obj: obj[2])
    for s in simpoints:
        interval, weight, starting_inst_count, actual_warmup_length = s
        print(str(interval), str(weight), starting_inst_count,
            actual_warmup_length)
        simpoint_start_insts.append(starting_inst_count)

    print("Total # of simpoints:", len(simpoints))
    testsys.cpu[0].simpoint_start_insts = simpoint_start_insts

    return (simpoints, interval_length)

def takeSimpointCheckpoints(simpoints, interval_length, cptdir, testsys):
    num_checkpoints = 0
    index = 0
    last_chkpnt_inst_count = -1
    for simpoint in simpoints:
        interval, weight, starting_inst_count, actual_warmup_length = simpoint
        if starting_inst_count == last_chkpnt_inst_count:
            # checkpoint starting point same as last time
            # (when warmup period longer than starting point)
            exit_cause = "simpoint starting point found"
            code = 0
        else:
            #exit_event = m5.simulate()
            if index == 0:
                runCPU(starting_inst_count,testsys.cpu)
            else:
                runCPU(starting_inst_count-last_chkpnt_inst_count,
                testsys.cpu)
            print(starting_inst_count - last_chkpnt_inst_count)
            # skip checkpoint instructions should they exist
            m5.checkpoint(joinpath(cptdir,
                "cpt.simpoint_%02d_inst_%d_weight_%f_interval_%d_warmup_%d"
                % (index, starting_inst_count, weight, interval_length,
                actual_warmup_length)))
            print("Checkpoint #%d written. start inst:%d weight:%f" %
                (num_checkpoints, starting_inst_count, weight))
            num_checkpoints += 1
            last_chkpnt_inst_count = starting_inst_count
        index += 1

    print('Exiting @ tick %i because %s' % (m5.curTick(), exit_cause))
    print("%d checkpoints taken" % num_checkpoints)
    sys.exit(code)

def restoreSimpointCheckpoint(testsys):
    runCPU(10000000,testsys.switch_cpus,-1)
    print("Warmed up, reset")
    m5.stats.reset()
    runCPU(100000000,testsys.switch_cpus,-1)
    print("DUMP stats")
    m5.stats.dump()
    sys.exit()
    #exit_event = m5.simulate()
    #exit_cause = exit_event.getCause()

    #if exit_cause == "simpoint starting point found":
    #    print("Warmed up! Dumping and resetting stats!")
    #    m5.stats.dump()
    #    m5.stats.reset()

    #    exit_event = m5.simulate()
    #    exit_cause = exit_event.getCause()

    #    if exit_cause == "simpoint starting point found":
    #        print("Done running SimPoint!")
    #        sys.exit(exit_event.getCode())

    #print('Exiting @ tick %i because %s' % (m5.curTick(), exit_cause))
    #sys.exit(exit_event.getCode())

def repeatSwitch(testsys, repeat_switch_cpu_list, maxtick, switch_freq):
    print("starting switch loop")
    while True:
        exit_event = m5.simulate(switch_freq)
        exit_cause = exit_event.getCause()

        if exit_cause != "simulate() limit reached":
            return exit_event

        m5.switchCpus(testsys, repeat_switch_cpu_list)

        tmp_cpu_list = []
        for old_cpu, new_cpu in repeat_switch_cpu_list:
            tmp_cpu_list.append((new_cpu, old_cpu))
        repeat_switch_cpu_list = tmp_cpu_list

        if (maxtick - m5.curTick()) <= switch_freq:
            exit_event = m5.simulate(maxtick - m5.curTick())
            return exit_event

def run(options, root, testsys, cpu_class):
    if options.checkpoint_dir:
        cptdir = options.checkpoint_dir
    elif m5.options.outdir:
        cptdir = m5.options.outdir
    else:
        cptdir = getcwd()

    if options.kernel_starting and options.warmup_insts :
        fatal("Please use warmup_aftkernel to use with kernel_starting")

    if options.warmup_aftkernel and not options.kernel_starting:
        fatal("Must specify --kernel-starting when using --warmup-aftkernel")

    if options.fast_forward and options.checkpoint_restore != None:
        fatal("Can't specify both --fast-forward and --checkpoint-restore")

    if options.standard_switch and not options.caches:
        fatal("Must specify --caches when using --standard-switch")

    if options.standard_switch and options.repeat_switch:
        fatal("Can't specify both --standard-switch and --repeat-switch")

    if options.repeat_switch and options.take_checkpoints:
        fatal("Can't specify both --repeat-switch and --take-checkpoints")
    #ipdb.set_trace()
    # Setup global stat filtering.
    stat_root_simobjs = []
    for stat_root_str in options.stats_root:
        stat_root_simobjs.extend(root.get_simobj(stat_root_str))
    m5.stats.global_dump_roots = stat_root_simobjs

    np = options.num_cpus
    switch_cpus = None

    if options.prog_interval:
        for i in range(np):
            testsys.cpu[i].progress_interval = options.prog_interval

    if options.maxinsts:
        if options.repeat:
            mainrepeat = options.maxinsts
        else:
            for i in range(np):
                testsys.cpu[i].max_insts_any_thread = options.maxinsts
    #ipdb.set_trace()
    if cpu_class:
        switch_cpus = [cpu_class(switched_out=True, cpu_id=(i))
                       for i in range(np)]

        for i in range(np):
            if options.fast_forward:
                #ipdb.set_trace()
                if options.repeat:
                    fast_repeat = options.fast_forward
                elif options.take_simpoint_checkpoints:
                    switch_cpus[i].max_insts_any_thread \
                        = int(options.fast_forward)
                else:
                    testsys.cpu[i].max_insts_any_thread \
                        = int(options.fast_forward)
            switch_cpus[i].system = testsys
            switch_cpus[i].workload = testsys.cpu[i].workload
            switch_cpus[i].clk_domain = testsys.cpu[i].clk_domain
            switch_cpus[i].progress_interval = \
                testsys.cpu[i].progress_interval
            switch_cpus[i].isa = testsys.cpu[i].isa
            # simulation period
            if options.maxinsts:
                if options.repeat:
                    mainrepeat = options.maxinsts
                else:
                    switch_cpus[i].max_insts_any_thread = options.maxinsts
            # Add checker cpu if selected
            if options.checker:
                switch_cpus[i].addCheckerCpu()
            if options.bp_type:
                bpClass = ObjectList.bp_list.get(options.bp_type)
                switch_cpus[i].branchPred = bpClass()
            if options.indirect_bp_type:
                IndirectBPClass = ObjectList.indirect_bp_list.get(
                    options.indirect_bp_type)
                switch_cpus[i].branchPred.indirectBranchPred = \
                    IndirectBPClass()

        # If elastic tracing is enabled attach the elastic trace probe
        # to the switch CPUs
        if options.elastic_trace_en:
            CpuConfig.config_etrace(cpu_class, switch_cpus, options)

        testsys.switch_cpus = switch_cpus
        switch_cpu_list = [(testsys.cpu[i], switch_cpus[i]) for i in range(np)]
        switch_cpu_list_inv = [(switch_cpus[i],testsys.cpu[i]) \
        for i in range(np)]

    if options.repeat_switch:
        switch_class = getCPUClass(options.cpu_type)[0]
        if switch_class.require_caches() and \
                not options.caches:
            print("%s: Must be used with caches" % str(switch_class))
            sys.exit(1)
        if not switch_class.support_take_over():
            print("%s: CPU switching not supported" % str(switch_class))
            sys.exit(1)

        repeat_switch_cpus = [switch_class(switched_out=True, \
                                               cpu_id=(i)) for i in range(np)]

        for i in range(np):
            repeat_switch_cpus[i].system = testsys
            repeat_switch_cpus[i].workload = testsys.cpu[i].workload
            repeat_switch_cpus[i].clk_domain = testsys.cpu[i].clk_domain
            repeat_switch_cpus[i].isa = testsys.cpu[i].isa

            if options.maxinsts:
                repeat_switch_cpus[i].max_insts_any_thread = options.maxinsts

            if options.checker:
                repeat_switch_cpus[i].addCheckerCpu()

        testsys.repeat_switch_cpus = repeat_switch_cpus

        if cpu_class:
            repeat_switch_cpu_list = [(switch_cpus[i], repeat_switch_cpus[i])
                                      for i in range(np)]
        else:
            repeat_switch_cpu_list = [(testsys.cpu[i], repeat_switch_cpus[i])
                                      for i in range(np)]


#-----------------Added----------------------------------------

    for i,cpu in enumerate(testsys.cpu):
        for obj in cpu.descendants():
            obj.eventq_index = 0
        cpu.eventq_index = i+1
    if options.kernel_starting:
        progkvm_cpu = [X86KvmCPU(switched_out=True, cpu_id=(i))
                       for i in range(np)]

        for i in range(np):
            progkvm_cpu[i].system =  testsys
            progkvm_cpu[i].workload = testsys.cpu[i].workload
            progkvm_cpu[i].clk_domain = testsys.cpu[i].clk_domain
            progkvm_cpu[i].isa = testsys.cpu[i].isa

            # warmup period

            if options.repeat and options.fast_forward:
                progrepeat = int(options.fast_forward)
            elif options.fast_forward:
                progkvm_cpu[i].max_insts_any_thread \
                    =  int(options.fast_forward)
            else:
                progkvm_cpu[i].max_insts_any_thread = 1
            testsys.cpu[i].max_insts_any_thread  =  0#100000000000000000
            #want it to be inf
        testsys.progkvm_cpu = progkvm_cpu
        for i,cpu in enumerate(testsys.progkvm_cpu):
            for obj in cpu.descendants():
                obj.eventq_index = 0
            cpu.eventq_index = i+1

        for i,cpu in enumerate(testsys.cpu):
            for obj in cpu.descendants():
                obj.eventq_index = 0
            cpu.eventq_index = i+1

        #warm cpu is for warmup
        if options.repeat:
        #want to change cpu from program kvm to detailed for initialization
            init_cpu_list =\
        [(testsys.progkvm_cpu[i],testsys.switch_cpus[i]) for i in range(np)]
        #from detailed, change it to program kvm to fastforward
            repeat_cpu_list =\
        [(testsys.switch_cpus[i],testsys.progkvm_cpu[i]) for i in range(np)]


        progswitch_cpu_list =\
            [(testsys.cpu[i],testsys.progkvm_cpu[i]) for i in range(np)]
        switch_cpu_list =\
        [(testsys.progkvm_cpu[i],testsys.switch_cpus[i]) for i in range(np)]

    if options.warmup_aftkernel:
        warmup_cpus = [TimingSimpleCPU(switched_out=True, cpu_id=(i))
                       for i in range(np)]

        for i in range(np):
            warmup_cpus[i].system =  testsys
            warmup_cpus[i].workload = testsys.cpu[i].workload
            warmup_cpus[i].clk_domain = testsys.cpu[i].clk_domain
            warmup_cpus[i].isa = testsys.cpu[i].isa

            # warmup period
            if options.repeat:
                warmrepeat = options.warmup_aftkernel
            else:
                warmup_cpus[i].max_insts_any_thread\
                        = int(options.warmup_aftkernel)

        testsys.warmup_cpu = warmup_cpus
        #warm cpu is for warmup
        switch_cpu_list =\
         [(testsys.progkvm_cpu[i],testsys.warmup_cpu[i]) for i in range(np)]
        #switch cpu is for real
        switch_cpu_list1 =\
         [(testsys.warmup_cpu[i], testsys.switch_cpus[i]) for i in range(np)]

    if options.restore_manual:
        restore_cpus = [TimingSimpleCPU(switched_out=True, cpu_id=(i))
                       for i in range(np)]

        for i in range(np):
            restore_cpus[i].system =  testsys
            restore_cpus[i].workload = testsys.cpu[i].workload
            restore_cpus[i].clk_domain = testsys.cpu[i].clk_domain
            restore_cpus[i].isa = testsys.cpu[i].isa

            restore_cpus[i].max_insts_any_thread\
                        = int(1)

        testsys.restore_cpu = restore_cpus
        restore_cpu_list1=\
         [(testsys.cpu[i] ,testsys.restore_cpu[i]) for i in range(np)]
        if not options.simpoint_profile:
            restore_cpu_list =\
             [(testsys.cpu[i],testsys.progkvm_cpu[i]) for i in range(np)]
#-----------------------------Added end-------------------------


    if options.standard_switch:
        switch_cpus = [TimingSimpleCPU(switched_out=True, cpu_id=(i))
                       for i in range(np)]
        switch_cpus_1 = [DerivO3CPU(switched_out=True, cpu_id=(i))
                        for i in range(np)]

        for i in range(np):
            switch_cpus[i].system =  testsys
            switch_cpus_1[i].system =  testsys
            switch_cpus[i].workload = testsys.cpu[i].workload
            switch_cpus_1[i].workload = testsys.cpu[i].workload
            switch_cpus[i].clk_domain = testsys.cpu[i].clk_domain
            switch_cpus_1[i].clk_domain = testsys.cpu[i].clk_domain
            switch_cpus[i].isa = testsys.cpu[i].isa
            switch_cpus_1[i].isa = testsys.cpu[i].isa

            # if restoring, make atomic cpu simulate only a few instructions
            if options.checkpoint_restore != None:
                testsys.cpu[i].max_insts_any_thread = 1
            # Fast forward to specified location if we are not restoring
            elif options.fast_forward:
                testsys.cpu[i].max_insts_any_thread = int(options.fast_forward)
            # Fast forward to a simpoint (warning: time consuming)
            elif options.simpoint:
                if testsys.cpu[i].workload[0].simpoint == 0:
                    fatal('simpoint not found')
                testsys.cpu[i].max_insts_any_thread = \
                    testsys.cpu[i].workload[0].simpoint
            # No distance specified, just switch
            else:
                testsys.cpu[i].max_insts_any_thread = 1

            # warmup period
            if options.warmup_insts:
                switch_cpus[i].max_insts_any_thread =  options.warmup_insts

            # simulation period
            if options.maxinsts:
                switch_cpus_1[i].max_insts_any_thread = options.maxinsts

            # attach the checker cpu if selected
            if options.checker:
                switch_cpus[i].addCheckerCpu()
                switch_cpus_1[i].addCheckerCpu()

        testsys.switch_cpus = switch_cpus
        testsys.switch_cpus_1 = switch_cpus_1
        switch_cpu_list = [
            (testsys.cpu[i], switch_cpus[i]) for i in range(np)
        ]
        switch_cpu_list1 = [
            (switch_cpus[i], switch_cpus_1[i]) for i in range(np)
        ]

    # set the checkpoint in the cpu before m5.instantiate is called
    if options.take_checkpoints != None and \
           (options.simpoint or options.at_instruction):
        offset = int(options.take_checkpoints)
        # Set an instruction break point
        if options.simpoint:
            for i in range(np):
                if testsys.cpu[i].workload[0].simpoint == 0:
                    fatal('no simpoint for testsys.cpu[%d].workload[0]', i)
                checkpoint_inst = int(testsys.cpu[i].workload[0].simpoint) + offset
                testsys.cpu[i].max_insts_any_thread = checkpoint_inst
                # used for output below
                options.take_checkpoints = checkpoint_inst
        else:
            options.take_checkpoints = offset
            # Set all test cpus with the right number of instructions
            # for the upcoming simulation
            for i in range(np):
                testsys.cpu[i].max_insts_any_thread = offset

    if options.take_simpoint_checkpoints != None:
        simpoints, interval_length = parseSimpointAnalysisFile(options, testsys)

    checkpoint_dir = None
    #ipdb.set_trace()
    if options.checkpoint_restore:
        cpt_starttick, checkpoint_dir = findCptDir(options, cptdir, testsys)
    elif options.restore_manual:
        cpt_starttick, checkpoint_dir = findCptDir(options, cptdir, testsys)
    root.apply_config(options.param)
    #ipdb.set_trace()
    m5.instantiate(checkpoint_dir)
    if options.take_simpoint_checkpoints:
        m5.simulate(1)
    # Initialization is complete.  If we're not in control of simulation
    # (that is, if we're a slave simulator acting as a component in another
    #  'master' simulator) then we're done here.  The other simulator will
    # call simulate() directly. --initialize-only is used to indicate this.
    if options.initialize_only:
        return

    # Handle the max tick settings now that tick frequency was resolved
    # during system instantiation
    # NOTE: the maxtick variable here is in absolute ticks, so it must
    # include any simulated ticks before a checkpoint
    explicit_maxticks = 0
    maxtick_from_abs = m5.MaxTick
    maxtick_from_rel = m5.MaxTick
    maxtick_from_maxtime = m5.MaxTick
    if options.abs_max_tick:
        maxtick_from_abs = options.abs_max_tick
        explicit_maxticks += 1
    if options.rel_max_tick:
        maxtick_from_rel = options.rel_max_tick
        if options.checkpoint_restore:
            # NOTE: this may need to be updated if checkpoints ever store
            # the ticks per simulated second
            maxtick_from_rel += cpt_starttick
            if options.at_instruction or options.simpoint:
                warn("Relative max tick specified with --at-instruction or" \
                     " --simpoint\n      These options don't specify the " \
                     "checkpoint start tick, so assuming\n      you mean " \
                     "absolute max tick")
        explicit_maxticks += 1
    if options.maxtime:
        maxtick_from_maxtime = m5.ticks.fromSeconds(options.maxtime)
        explicit_maxticks += 1
    if explicit_maxticks > 1:
        warn("Specified multiple of --abs-max-tick, --rel-max-tick, --maxtime."\
             " Using least")
    maxtick = min([maxtick_from_abs, maxtick_from_rel, maxtick_from_maxtime])

    if options.checkpoint_restore != None and maxtick < cpt_starttick:
        fatal("Bad maxtick (%d) specified: " \
              "Checkpoint starts starts from tick: %d", maxtick, cpt_starttick)
    #ipdb.set_trace()
    if options.standard_switch or cpu_class:
        if options.kernel_starting:
            print("START kernel with testsys.cpu[0] cpu")
            exit_event = m5.simulate() #Do the kernel start
            exit_cause = exit_event.getCause()
            success = exit_cause == "m5_exit instruction encountered"
            success = True
            if not success:
                print("Error while booting linux: {}".format(exit_cause))
                exit(1)
            print("Booting Done")
            print("Switch to progkvmcpu instruction count:%s" %
                    str(testsys.cpu[0].max_insts_any_thread))
            if options.checkpt_manual:
                m5.checkpoint(joinpath(cptdir,"cpt.%d"%(1)))
                exit_event = m5.simulate() #Do the kernel start
                exit_cause = exit_event.getCause()

            if options.restore_manual and not options.checkpoint_repeat:
                m5.switchCpus(testsys, restore_cpu_list) #change to kvmprog cpu
            elif options.checkpoint_repeat:
                pass
            else:
                m5.switchCpus(testsys, progswitch_cpu_list)
                #Now it has kvm prog CPU

        #precondtion : kvm program CPU
        if options.checkpoint_repeat:
            for trial in range(options.checkpoint_repeat):
                print("Start trial :%d"%(trial+1))
                success, exit_cause = runCPU(progrepeat,testsys.cpu)
                if not success:
                    print("ERROR fail for FF between samples: {}"\
                    .format(exit_cause))
                    exit(1)
                m5.checkpoint(joinpath(cptdir,"cpt.%d"%(trial+2)))

        if options.repeat:
            #pre condition : kvm program cpu
            m5.switchCpus(testsys,init_cpu_list)
            #pre condition :  detailed cpu
            for trial in range(options.repeat):
                print("Start FF:Repeat %d"%trial)
                m5.switchCpus(testsys,repeat_cpu_list)
                success, exit_cause = runCPU(progrepeat,testsys.progkvm_cpu)
                if not success:
                    print("ERROR fail for FF between samples: {}"\
                    .format(exit_cause))
                    exit(1)
                m5.switchCpus(testsys,switch_cpu_list)
                #when warmup, it's warmup else, switch_cpus
                if options.warmup_aftkernel:
                    #ipdb.set_trace()
                    print("Start Warmup:Repeat %d"%trial)
                    success, exit_cause = runCPU(warmrepeat,testsys.warmup_cpu)
                else:
                    m5.stats.reset()
                    print("Start detailed cpu:Repeat %d"%trial)
                    success, exit_cause \
                        = runCPU(mainrepeat,testsys.switch_cpus)
                    if success:
                        m5.stats.dump()
                if not success:
                    print("ERROR fail for detail or warm between samples: {}"\
                    .format(exit_cause))
                    exit(1)
               #when warmup, it's switch CPU
                if options.warmup_aftkernel:
                    m5.switchCpus(testsys,switch_cpu_list1)
                    m5.stats.reset()
                    print("Start detailed cpu:Repeat %d"%trial)
                    success, exit_cause \
                        = runCPU(mainrepeat,testsys.switch_cpus)
                    if not success:
                        print("ERROR fail for detailed between samples: {}"\
                        .format(exit_cause))
                        exit(1)
                    m5.stats.dump()



        #ipdb.set_trace()
        if options.standard_switch:
            print("Switch at instruction count:%s" %
                    str(testsys.cpu[0].max_insts_any_thread))
            #exit_event = m5.simulate()
            #This one is temporal patch need to think about it later
            #if you really want other restore
        elif cpu_class and options.fast_forward:
            print("Switch at instruction count:%s" %
                    str(testsys.cpu[0].max_insts_any_thread))
            print("Start FF")
            flagT = True
            while flagT:
                exit_event = m5.simulate()
                flagT = (exit_event.getCause()!=\
                        "m5_exit instruction encountered")
        else:
            print("Switch at curTick count:%s" % str(10000))
            exit_event = m5.simulate(10000)
        print("Switched CPUS @ tick %s" % (m5.curTick()))


        m5.switchCpus(testsys, switch_cpu_list)
        # for kernel start with instrucion warmup, now warmup else,usual O3

        if options.standard_switch or options.warmup_aftkernel:
            print("Switch at instruction count:%d" %
                    (testsys.switch_cpus[0].max_insts_any_thread))

            #warmup instruction count may have already been set
            if options.warmup_aftkernel:
                print("Start warmup")
                exit_event = m5.simulate()
                print("Switching CPUS @ tick %s" % (m5.curTick()))
                print("Simulation ends instruction count:%d" %
                        (testsys.warmup_cpu[0].max_insts_any_thread))
            else:
                exit_event = m5.simulate(options.standard_switch)
                print("Switching CPUS @ tick %s" % (m5.curTick()))
                print("Simulation ends instruction count:%d" %
                        (testsys.switch_cpus_1[0].max_insts_any_thread))
            m5.switchCpus(testsys, switch_cpu_list1)

    # If we're taking and restoring checkpoints, use checkpoint_dir
    # option only for finding the checkpoints to restore from.  This
    # lets us test checkpointing by restoring from one set of
    # checkpoints, generating a second set, and then comparing them.
    if (options.take_checkpoints or options.take_simpoint_checkpoints) \
        and options.checkpoint_restore:

        if m5.options.outdir:
            cptdir = m5.options.outdir
        else:
            cptdir = getcwd()

    if options.take_checkpoints != None :
        # Checkpoints being taken via the command line at <when> and at
        # subsequent periods of <period>.  Checkpoint instructions
        # received from the benchmark running are ignored and skipped in
        # favor of command line checkpoint instructions.
        exit_event = scriptCheckpoints(options, maxtick, cptdir)

    # Take SimPoint checkpoints
    elif options.take_simpoint_checkpoints != None:
        m5.switchCpus(testsys,switch_cpu_list_inv)
        takeSimpointCheckpoints(simpoints, interval_length, cptdir, testsys)

    # Restore from SimPoint checkpoints
    elif options.restore_simpoint_checkpoint != None:
        restoreSimpointCheckpoint(testsys)

    else:
        if options.fast_forward or options.kernel_starting:
            m5.stats.reset()
        print("**** REAL SIMULATION ****")

        # If checkpoints are being taken, then the checkpoint instruction
        # will occur in the benchmark code it self.
        if options.repeat_switch and maxtick > options.repeat_switch:
            exit_event = repeatSwitch(testsys, repeat_switch_cpu_list,
                                      maxtick, options.repeat_switch)
        elif options.checkpoint_restore:
            exit_event = runCPU
            m5.stats.reset()

            success, exit_cause \
                = runCPU(options.maxinsts,testsys.switch_cpus_1)
            if not success:
                print("ERROR fail for detailed between samples: {}"\
                .format(exit_cause))
                exit(1)
            m5.stats.dump()
        else:
            exit_event = benchCheckpoints(options, maxtick, cptdir)

    print('Exiting @ tick %i because %s' %
          (m5.curTick(), exit_event.getCause()))
    if options.checkpoint_at_end:
        m5.checkpoint(joinpath(cptdir, "cpt.%d"))

    if exit_event.getCode() != 0:
        print("Simulated exit code not 0! Exit code is", exit_event.getCode())


def runCPU(period, currentCPU, ctrl_cpu_index=0):
    if ctrl_cpu_index == -1:
        _size = len(currentCPU)
        insts = []
        setflag = False
        for i in range(_size):
            insts.append(currentCPU[i].totalInsts())
            if not setflag :
                currentCPU[i].scheduleInstStop(0,period,
                       "Max Insts readed CPU %d"%(i))
                setflag = True
            else:
                currentCPU[i].setMaxInstStop(0,period)
        cnt = 0
        #ipdb.set_trace()
        while cnt < _size:
            setflag = False
            exit_event = m5.simulate()
            exit_cause = exit_event.getCause()
            print(exit_cause)
            success = exit_cause.startswith("Max Insts")
            if not success : continue
            cnt = 0
            for i in range(_size):
                remainder = period -(currentCPU[i].totalInsts()-insts[i])
                if remainder <= 0:
                    cnt+=1
                elif not setflag:
                    currentCPU[i].scheduleInstStop(0,remainder,
                       "Max Insts readed CPU %d"%(i))
                    setflag = True

                print("DEBUG: cpu %d: insts simed this interval %d"%\
                (i,currentCPU[i].totalInsts()-insts[i]))

        for  i in range(_size):
            print("DEBUG: insts simed this interval %d"%\
            (currentCPU[i].totalInsts()-insts[i]))
        return success, exit_cause

    currentCPU[ctrl_cpu_index].scheduleInstStop(0,period,
            "Max Insts readed CPU %d"%(ctrl_cpu_index))
    pri_count = currentCPU[0].totalInsts()
    exit_event = m5.simulate()
    exit_cause = exit_event.getCause()
    print(exit_cause)
    success = exit_cause.startswith("Max Insts")
    while not success:
        exit_event = m5.simulate()
        exit_cause = exit_event.getCause()
        print(exit_cause)
        success = exit_cause.startswith("Max Insts")
    post_count = currentCPU[0].totalInsts()
    print("DEBUG: insts simed this interval %d"%(post_count - pri_count))
    return success, exit_cause
