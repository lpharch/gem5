#include "msr.hh"

uint64_t my_rdmsr(uint64_t cpuId, uint64_t msr) {
    //assert(MSR_PER_CORE*cpuId + msr < allocated);
    return msr_array[MSR_PER_CORE*cpuId + msr]; 
}

void my_wrmsr(uint64_t cpuId, uint64_t msr, uint64_t value) {
    //assert(MSR_PER_CORE*cpuId + msr < allocated);
    
    if(msr == 0) {
		// Update the cache partition.
		if(msr_array[MSR_PER_CORE*cpuId] != 0) {
		    uint64_t dealloc = (msr_array[MSR_PER_CORE*cpuId] & (~value));
 	        for(int i=0; i<64; i++) {
				if((dealloc & 0x1) != 0) {
					for(int j=0; j<cache_handlers.size(); j++){
						cache_handlers[j]->invalidateWay(i);
					}
				}
				dealloc = (dealloc >> 1);
		    }
		}	
    }
    else if(msr > 0 && msr <=10) {
		//// Update the MITTS buckets.
		//for(int j=0; j<cache_handlers.size(); j++) {
		//    cache_handlers[j]->updateMitts(cpuId, msr-1);
		//}
    }

    msr_array[MSR_PER_CORE*cpuId + msr] = value;
    return; 
}

void register_cache(Cache* reg) {
    for(auto it=cache_handlers.begin(); it<cache_handlers.end(); it++) {
	if(*it == reg)
	    return;
    }
    cache_handlers.push_back(reg);
}
