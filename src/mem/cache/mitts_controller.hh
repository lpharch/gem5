/**
 * @file
 * Memory Inter-arrival Time Traffic Shaping (MITTS) 
 * Controller (MSHR) declaration.
 */

#ifndef __MEM__CACHE__MITTS_HH__
#define __MEM__CACHE__MITTS_HH__


#include <cassert>
#include <iosfwd>
#include <string>
#include <vector>

#include "base/printable.hh"
#include "base/types.hh"
//#include "mem/cache/queue_entry.hh"
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
#include "sim/core.hh"
#include "sim/eventq.hh"
#include "sim/probe/probe.hh"
#include "sim/serialize.hh"
#include "sim/sim_exit.hh"
#include "sim/sim_object.hh"
#include "sim/system.hh"

//class System;
class BaseCache;

/**
 * MITTS Controller. Controls the extra delay introduced for
 * each packet leaving cache
 * @sa \ref MITTS Module Design
 */ 
class MittsController : public SimObject
{
  private:
    /**
     * Number of bins mitts controller maintain. Control the resolution
     * of modifying the delay
     */
    unsigned bin_num;

    /**
     * Number of cores in system. 
     * @TODO currently passed in throught config script, and user need to
     * guarantee the passed in value reflect the number of CPUs in system. 
     * ideally this should not be exposed to user
     */
    unsigned core_num;

    /**
     * Period to relinquish the bins in unit of ticks
     */
    Tick relinquish_period;

    /**
     * Initial credits in bins
     * @TODO deprecate this once advanced mechanism added to init bin
     */ 
    uint32_t initCredits;

    /**
     * Number of ticks each bin represent
     */
    Tick bin_interval;

    /**
     * Modle the HW reg tracks the next relinquish tick
     */
    Tick nextRelinqTick;

    std::vector<std::vector<uint32_t>> credits;
    std::vector<std::vector<uint32_t>> defaults;
    std::vector<Tick> lastAccessTick;
    //store the upper bound of that bin. shared by all cores

    /**
     * @brief Store the upper bound delay of that bin
     * 
     */
    std::vector<Tick> binIndex;

    //System *system;
    void processEvent();
    EventFunctionWrapper event;


  public:

    /**
     * @brief Refill the bins according to pre-defined profile
     * 
     */
    void relinquishBins();

    /**
     * @brief Fetch new shaping profiles
     * This is useful when the shaping profile can be dynamically configured
     * e.g. the MSRs accessible from SW
     * 
     */
    void fetchNewConfig();

    /**
     * @brief Print the bin status for a specific core
     * Most used during debugging
     * 
     * @param coreId 
     */
    void showBins(uint32_t coreId);

    /**
     * Modifying the forward time of a packet to meet the inter sending
     * time distribtion requirement
     * @param coreId the cpu id own this packt
     * @param cur    current tick
     * @return the new forwarding time (in unit of tick)
     */
    Tick modSendTime(uint coreId, Tick cur);

    //Note seems add de-constructor will cause the build to fail
    //~MittsController();


    MittsController(const MittsControllerParams &p);

    void
    init() override {}

    /**
     * @brief Kickoff the recurrent refill event
     * 
     */
    void
    startup() override;

};

#endif // __MEM__CACHE__MITTS_HH__