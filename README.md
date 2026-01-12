# MetroMind

---

## Overview

MetroMind is a transit intelligence project that learns how long buses actually take, instead of relying on unreliable schedules. It begins with an initial data-collection period, during which it quietly observes live MTA bus data and records how long specific bus routes take to travel between exact pairs of stops across different days and times.

Once this foundation is built, MetroMind can start making predictions, but it never stops learning. As buses continue to run, the system continues to collect new data, constantly updating its understanding of real-world conditions and becoming more accurate over time. Rather than guessing, MetroMind improves with experience, using history to predict the future more reliably.

---

## The Problem

The MTA schedule is often wrong because:

* Traffic changes
* Traffic lights slow buses down
* Rush hour is different than late night
* Some stops are always slower than others

As a result, the same bus can take very different amounts of time to travel between the same two stops depending on the day and time.

---

## The Big Idea

MetroMind learns very specific patterns, such as:

* “When the M5 goes from Stop A → Stop B on Tuesdays at 5 PM, it usually takes about X minutes.”
* “When the M104 goes from Stop X → Stop Y on Wednesdays at 5 PM, it usually takes about Y minutes.”

Instead of guessing, MetroMind remembers what usually happens.

---

## How It Works (The Loop of Learning)

MetroMind works in three simple steps:

### 1. Watch (Collect Live Bus Info)

MetroMind constantly checks the MTA’s live bus data to see:

* Where each bus is
* What route it’s on
* What stop it’s going to next

### 2. Remember (Save What Really Happened)

Instead of throwing data away, MetroMind saves it. It records:

* Bus route (M5, M104, etc.)
* The stop the bus just left
* The stop it reached next
* The day
* The time
* How long it took to travel between those two stops

After weeks of collection, MetroMind builds a large “memory” of real bus behavior. This data collection never stops — the memory keeps growing forever.

### 3. Predict (Use Memory to Estimate the Future)

When asked:

> How long until the bus gets to my stop?

MetroMind looks at:

* The bus route
* The exact stop-to-stop segment
* The current day and time

It then responds:

> Based on what usually happens at this time, it will probably take about X minutes.

The more data it collects, the more accurate it becomes.

---

## What the MVP (First Version) Will Do

To stay small and focused, the first version is not a full app. It is a proof of concept.

### The MVP does:

* Collect data citywide for approximately ~2 months before producing predictions
* Learn stop-to-stop travel times for every bus route
* After data collection, generate predictions such as:

  * “M5, Stop A → Stop B, Tuesday 5 PM: usually 2.8 minutes”

### The MVP does NOT include:

* A polished mobile app
* Maps
* Subway data
* Trip planning
* Notifications

---

## Why This Is Different

Most transit apps only react after a delay is happening.

MetroMind learns patterns like:

* “This segment is always slow at rush hour”
* “Friday afternoons are worse than Tuesdays”
* “This stop pair is unpredictable during school dismissal time”

Because of this, MetroMind can anticipate delays before they fully appear.

---

## System Architecture

```
MTA Live Bus Data
  |
  v
MetroMind Collector
  |
  v
MetroMind Database (Memory)
  |
  v
MetroMind Predictor
```

* **Collector**: Watches buses and records what happens
* **Database**: Stores historical data
* **Predictor**: Uses past data to make better arrival estimates

---

## Tools

* **Language**: Python (fast to build, strong data ecosystem)
* **Database**: PostgreSQL (reliable, scalable, queryable)
* **Runtime**: Single server / VPS or always-on home machine
* **Scheduler**: systemd service + timer, or a simple always-running loop
