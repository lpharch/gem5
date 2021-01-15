#include "mem/cache/mitts_controller.hh"

MittsController::MittsController(const MittsControllerParams &p) :
        SimObject(p), bin_num(p.numBin), core_num(p.numCPU),
        event([this]{processEvent();}, name())
{
    for (int i=0; i< core_num; i++){
        lastAccessTick.push_back(curTick());
    }

    //hardcoded parameter for now, fix interval bucket
    for (int i=0; i< bin_num; i++){
        Tick interval = 100000;
        binIndex.push_back((i+1)*interval);
    }

    //even distributed credits in bins
    for (int i=0; i< core_num; i++){
        uint32_t initCredits = 1000;
        defaults.push_back(std::vector<uint32_t>(bin_num, initCredits));
    }
    credits = defaults;
    relinquish_period = 1000000000;
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
    Tick interval = (cur < lastAccessTick[coreId])? 0 :
                     cur - lastAccessTick[coreId];
    for (int i=0; i < bin_num; i++){
        if (interval < binIndex[i] && credits[coreId][i] > 0){
            //find the right bucket
            credits[coreId][i] -= 1;
            Tick ret = lastAccessTick[coreId] + interval;
            lastAccessTick[coreId] = ret;
            return ret;
        }
        else{
            interval = binIndex[i];
        }
    }

    DPRINTF(MITTS, "No availble credits in any bin\n");
    //TODO: add more enhance logic here, now simply send at relinquish time
    return cur + relinquish_period;
}

void
MittsController::processEvent()
{
    fetchNewConfig();
    relinquishBins();
    schedule(event, curTick() + relinquish_period);
}

void
MittsController::startup()
{
    DPRINTF(MITTS, "Initial Refill Scheduled\n");
    schedule(event, curTick() + relinquish_period);
}
