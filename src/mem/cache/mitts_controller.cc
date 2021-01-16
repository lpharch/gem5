/**
 * @file
 * Mitts Controller definitions.
 */

#include "mem/cache/mitts_controller.hh"

MittsController::MittsController(const MittsControllerParams &p) :
        SimObject(p),
        bin_num(p.numBin), core_num(p.numCPU),
        relinquish_period(p.relinq_period),
        initCredits(p.initCredit),
        bin_interval(p.bin_interval),
        event([this]{processEvent();}, name())
{
    // linear bin range distribution
    for (int i=0; i< bin_num; i++){
        binIndex.push_back((i+1)*bin_interval);
    }

    // evenly distributed credits in bins
    for (int i=0; i< core_num; i++){
        defaults.push_back(std::vector<uint32_t>(bin_num, initCredits));
    }
}

void
MittsController::showBins(uint32_t coreId)
{
    for (int i=0; i< bin_num; i++){
        DPRINTF(MITTS, "Bin %d [<%llu]: %u credits\n",
        i, binIndex[i], credits[coreId][i]);
    }
}


void
MittsController::relinquishBins()
{
    DPRINTF(MITTS, "Recurrent Scheduling Detected\n");
    credits = defaults;
}

void
MittsController::fetchNewConfig(){
    //TODO: fetch config variables from m5 registers
}

Tick
MittsController::modSendTime(uint32_t coreId, Tick cur){
    //cur < lastAccess indicates alreay queuing up
    DPRINTF(MITTS, "========== New Pkt from Core %d ============\n", coreId);
    DPRINTF(MITTS, "Orig send time %llu, last send time %llu\n",
                    cur, lastAccessTick[coreId]);
    DPRINTF(MITTS, "Interval since last sent: %lld\n",
         (int64_t)cur - (int64_t)lastAccessTick[coreId]);
    showBins(coreId);

    Tick interval = (cur < lastAccessTick[coreId])? 0 :
                                                  cur - lastAccessTick[coreId];

    //scan from small bin to bigger, relies on the property binIndex stores 
    //upper bound for each bin
    for (int i=0; i < bin_num; i++){
        DPRINTF(MITTS, "interval: %llu, bin: %llu\n",interval, binIndex[i]);
        if (interval < binIndex[i] && credits[coreId][i] > 0){
            DPRINTF(MITTS, "Hit bin %d, add delay %lld\n",
                    i, (interval +lastAccessTick[coreId]-cur));
            credits[coreId][i] -= 1;
            Tick ret = lastAccessTick[coreId] + interval;
            lastAccessTick[coreId] = ret;
            return ret;
        }
        else{
            interval = interval < binIndex[i]? binIndex[i]:interval;
        }
    }

    if (interval > binIndex[bin_num-1]){
        DPRINTF(MITTS, "Request send tick exceed bin range, unmodified\n");
        lastAccessTick[coreId] = cur;
        return cur;
    }
    else{
        DPRINTF(MITTS, "No Credits left, schedule at next relinq tick\n");
        DPRINTF(MITTS, "add delay %lld\n", nextRelinqTick - cur);
        lastAccessTick[coreId] = nextRelinqTick;
        return nextRelinqTick;
    }
}

void
MittsController::processEvent()
{
    fetchNewConfig();
    relinquishBins();
    for (auto& it: lastAccessTick){
        it = curTick();
    }
    nextRelinqTick = curTick() + relinquish_period;
    schedule(event, curTick() + relinquish_period);
}

void
MittsController::startup()
{
    for (int i=0; i< core_num; i++){
        lastAccessTick.push_back(curTick());
    }
    DPRINTF(MITTS, "Initial Refill Scheduled\n");
    processEvent();
}
