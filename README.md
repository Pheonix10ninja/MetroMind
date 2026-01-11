# MetroMind
MetroMind is a transit intelligence project that learns how long city buses actually take. It quietly collects live MTA bus data, records real stop-to-stop travel times by route, day, and time, and builds a growing memory of patterns. Over time, it uses this history to predict bus arrivals more accurately than schedules. 

Input: Live MTA bus data (positions, trip/vehicle IDs, route, stop updates).
Output (after collection): “For route R, stop A → stop B, on weekday W, time bucket T: typical travel time = X minutes.”
Not building yet: app UI, maps, notifications, subway, trip planner.
