# MetroMind — Full Project Steps (No Code)

This document outlines **everything to do**, in order, to build the MetroMind MVP from scratch.  
It is **process-only**: no code, no syntax, just actions and decisions.

---

## Phase 0 — Understand & Lock the Idea

1. Read the project proposal completely.
   - Understand the problem: bus schedules are unreliable.
   - Understand the goal: learn *real* stop-to-stop travel times.
   - Understand the limits: buses only, no app, no maps, no UI.

2. Define the single success goal.
   - Write and commit to this statement:
     > After collecting data for ~2 months, MetroMind can estimate how long a specific bus usually takes between two specific stops at a specific day and time.

3. Decide what “done” means for the MVP.
   - Data collection runs continuously.
   - Stop-to-stop travel times exist for all routes.
   - The system can output a prediction based on historical data.

---

## Phase 1 — Plan the System (No Building Yet)

4. Write the system flow in plain language.
   - MTA Live Bus Data → Collector → Database (Memory) → Predictor

5. Decide exactly what data must be stored.
   - Bus route
   - From stop
   - To stop
   - Date
   - Time (day of week + hour)
   - Actual travel time

6. Decide what is explicitly **out of scope**.
   - No mobile app
   - No maps
   - No subway
   - No trip planning
   - No alerts or notifications

7. Choose where the system will run.
   - One always-on machine (server or home computer).
   - This decision must be final before continuing.

---

## Phase 2 — Prepare for Data Collection

8. Identify the official MTA live bus data source.
   - Confirm update frequency.
   - Confirm available identifiers (bus, route, stop).

9. Understand how a bus moves between stops.
   - How a bus is marked as leaving a stop.
   - How arrival at the next stop is detected.

10. Design the “memory” conceptually.
    - One record = one stop-to-stop movement.
    - Must scale to very large amounts of data.

---

## Phase 3 — Build the Collector (Watching Phase)

11. Create a process that runs continuously.
    - It checks live bus data repeatedly.
    - It restarts or survives minor failures.

12. Track each bus individually.
    - Follow its progress from stop to stop.

13. Measure real travel times.
    - Record departure time from Stop A.
    - Record arrival time at Stop B.
    - Calculate the difference.

14. Save every valid result immediately.
    - No predictions.
    - No filtering yet.
    - Pure observation.

15. Handle bad data safely.
    - Skip incomplete or broken data.
    - Never stop the system because of one error.

---

## Phase 4 — Silent Data Collection Period

16. Start the long-term collection phase.
    - Run continuously for ~2 months.
    - The system only watches and remembers.

17. Monitor system health.
    - Ensure data is still flowing.
    - Ensure storage is not failing.
    - Ensure the process is still alive.

18. Do **not** analyze yet.
    - No predictions.
    - No tuning.
    - Let patterns form naturally.

---

## Phase 5 — Organize & Clean the Memory

19. Group data into meaningful time buckets.
    - Day of week
    - Hour of day
    - Weekday vs weekend

20. Remove obvious outliers.
    - GPS glitches
    - Impossible travel times
    - Clearly broken records

21. Verify coverage.
    - All routes present.
    - Most stop pairs have multiple samples.

---

## Phase 6 — Build the Predictor (Thinking Phase)

22. Define how predictions work.
    - Input:
      - Route
      - From stop
      - To stop
      - Day and time
    - Output:
      - Typical travel time

23. Choose a simple prediction rule.
    - Start with averages or medians.
    - Avoid complex ML at first.

24. Make predictions explainable.
    - Always know how many past trips were used.

---

## Phase 7 — Validate the Results

25. Test real-world scenarios.
    - Busy times vs quiet times.
    - Compare predictions to reality.

26. Check consistency.
    - Same conditions → similar results.
    - Different conditions → different results.

27. Confirm learning behavior.
    - Predictions slowly adjust as new data arrives.

---

## Phase 8 — Lock the MVP

28. Freeze features.
    - No UI.
    - No maps.
    - No expansion.

29. Document the system.
    - What it does.
    - How it learns.
    - Why it’s better than schedules.

30. Declare MVP complete.
    - Continuous collection.
    - Growing memory.
    - History-based predictions.

---

## Phase 9 — Optional Future Expansion (After MVP)

31. Possible next steps.
    - Smarter prediction models.
    - Confidence ranges.
    - Web or mobile interface.
    - Subway support.

---

## One-Sentence Summary

MetroMind works by **watching buses quietly**, **remembering what actually happens**, and **using real experience—not guesses—to predict the future**.
