#ifndef __CACHE_MSR__
#define __CACHE_MSR__

#define MSR_PER_CORE 16

#include <cstdint>
#include <climits>
#include <cstdio>
#include <vector>

#include "cache.hh"

//static int allocated = 0;
static std::vector<uint64_t> msr_array;
static std::vector<Cache*> cache_handlers;

uint64_t my_rdmsr(uint64_t cpuId, uint64_t msr);
void my_wrmsr(uint64_t cpuId, uint64_t msr, uint64_t value);
void register_cache(Cache* reg_cache);

// The msr layout is decided here. Currently, the layout I'm using is msr[0] for cache mask, and msr[1-10] for MITTS. This can be changed in any way by changing up the switch case inside the wrmsr function.
// wrmsr() invokes various function handlers depending on which slot has been changed. For example, if the cache partition changes, this calls a different function within the cache than if the mitts buckets change. 
// The function handlers registered with wrmsr() have to be part of the baseCache class atm, as it only stores the msr array is allocated by the cache and no exchange of object pointers takes place.

#endif
