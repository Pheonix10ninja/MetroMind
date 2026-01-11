# MetroMind

## Purpose
MetroMind is a transit intelligence project that learns how long NYC buses *actually* take to travel between specific stops.  
Instead of trusting unreliable schedules, it observes real MTA bus data over time and builds a memory of how long each exact stop-to-stop segment usually takes at different days and times.  
The goal is to use past behavior to make more accurate predictions in the future.

## How to Run
1. Set up a script or service that connects to the MTA live bus data feed.
2. Run the data collector continuously (24/7).
3. For each bus, record:
   - route ID
   - previous stop
   - next stop
   - day of week
   - time of day
   - time taken to travel between the two stops
4. Store all records in a database.
5. Let the system collect data for an extended period (about 2 months minimum).

At this stage, the project runs quietly in the background and does not require a user interface.

## What “Done” Means (for the MVP)
The MVP is considered **done** when:
- The system successfully collects live bus data for the entire city
- Stop-to-stop travel times are reliably recorded for all routes
- At least ~2 months of historical data exists
- The system can output statements like:  
  > “M5, Stop A → Stop B, Tuesday at 5 PM usually takes ~2.8 minutes”
- Data collection continues automatically after predictions begin

A mobile app, maps, or trip planning are **not** part of the MVP.
