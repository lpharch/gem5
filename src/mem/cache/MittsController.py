from m5.params import *
from m5.SimObject import SimObject


class MittsController(SimObject):
    type = 'MittsController'
    cxx_header = "mem/cache/mitts_controller.hh"

    numCPU = Param.Unsigned("Number of cores in System")
    numBin = Param.Unsigned("Number of bins used by controller")
    relinq_period = Param.Unsigned(10000000,"Relinquish Period in ticks")
