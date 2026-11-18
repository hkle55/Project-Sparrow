# Sparrow

A pocket-sized, real-time SEPTA bus companion. At a glance it answers:

1. Which bus should I take?
2. When is it arriving?
3. When do I need to leave?

It was built for one daily Philadelphia commute, where buses running *early* kept
causing missed buses. Sparrow uses SEPTA's live stop-level predictions plus walking time
and a safety buffer to say "leave in 5 min" instead of making you do the math. It also
tells you clearly when the data isn't live.

## Status

Software prototype (backend and web device simulator). The ESP32 hardware comes later.
See [PROJECT_PLAN.md](PROJECT_PLAN.md).
