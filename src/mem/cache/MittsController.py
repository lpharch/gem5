from m5.params import *
from m5.SimObject import SimObject


class MittsController(SimObject):
    type = 'MittsController'
    cxx_header = "mem/cache/mitts_controller.hh"

    numCPU = Param.Unsigned("Number of cores in System")
    numBin = Param.Unsigned("Number of bins used by controller")
    initCredit = Param.Unsigned(200, "Initial Credits in each bucket")
    #make sure bin_inter * num_bin = relinq_period
    relinq_period = Param.Tick(2000000000,"Relinquish Period in ticks")
    bin_interval  = Param.Tick(200000000, "Latency of each bin")
