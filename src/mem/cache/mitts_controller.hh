#ifndef __MEM__CACHE__MITTS_HH__
#define __MEM__CACHE__MITTS_HH__


/*
#include "params/MittsController.hh"
#include "sim/sim_object.hh"

class BaseCache;

class MittsController : public SimObject
{
  private:
    Tick relinquish_period;
    unsigned bin_num;
    unsigned core_num;

  public:
    MittsController(const MittsControllerParams &p);

};
*/




#include <cassert>
#include <iosfwd>
#include <list>
#include <string>
#include <vector>

//#include "base/printable.hh"
//#include "base/types.hh"
//#include "mem/cache/queue_entry.hh"
//#include "mem/packet.hh"
//#include "mem/request.hh"
#include "base/addr_range.hh"
#include "base/statistics.hh"
#include "base/trace.hh"
#include "base/types.hh"
#include "debug/Cache.hh"
#include "debug/CachePort.hh"
#include "debug/MITTS.hh"
#include "enums/Clusivity.hh"
#include "mem/cache/cache_blk.hh"
#include "mem/cache/compressors/base.hh"
#include "mem/cache/mitts_controller.hh"
#include "mem/cache/mshr_queue.hh"
#include "mem/cache/tags/base.hh"
#include "mem/cache/write_queue.hh"
#include "mem/cache/write_queue_entry.hh"
#include "mem/packet.hh"
#include "mem/packet_queue.hh"
#include "mem/qport.hh"
#include "mem/request.hh"
#include "params/MittsController.hh"
#include "params/WriteAllocator.hh"
#include "sim/clocked_object.hh"
#include "sim/core.hh"
#include "sim/eventq.hh"
#include "sim/probe/probe.hh"
#include "sim/serialize.hh"
#include "sim/sim_exit.hh"
#include "sim/sim_object.hh"
#include "sim/system.hh"

//class System;
class BaseCache;


class MittsController : public SimObject
{
  private:
    Tick relinquish_period;
    unsigned bin_num;
    unsigned core_num;

    std::vector<std::vector<uint32_t>> credits;
    std::vector<std::vector<uint32_t>> defaults;
    std::vector<Tick> lastAccessTick;
    //store the upper bound of that bin. shared by all cores
    std::vector<Tick> binIndex;

    //System *system;

  public:
    void processEvent();
    EventFunctionWrapper event;


    void relinquishBins();
    void fetchNewConfig();

    /**
     * Modifying the send time of a packet to meet the inter sending
     * time distribtion requirement
     * @param coreId the cpu id own this packt
     * @param cur    current tick
     * @return the new send time in tick
     */
    Tick modSendTime(uint coreId, Tick cur);



    //Note seems add de-constructor will cause the build to fail
    //~MittsController();
  public:
    MittsController(const MittsControllerParams &p);

    void
    init() override {}

    void
    startup() override;

};


#endif
