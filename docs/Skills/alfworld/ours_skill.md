# ALFWorld Embodied Agent Skill

## Overview
Complete household tasks in the ALFWorld text environment by navigating
rooms, interacting with objects, and using appliances. Choose actions only
from the admissible list each step.

**Output format**: `<think>...</think>` for reasoning, then
`<action>...</action>` for the chosen action, every turn.

## Task Types

| Type | Key Steps |
|------|-----------|
| Pick & Place | find X -> take X -> go to Y -> put X in/on Y |
| Pick Two & Place | two instances of X into one chosen receptacle instance |
| Examine in Light | take X -> find desklamp -> use desklamp (don't place X on the lamp) |
| Clean & Place | take X -> clean with sinkbasin -> go to Y -> put X |
| Heat & Place | take X -> heat with microwave -> go to Y -> put X |
| Cool & Place | take X -> cool with fridge -> go to Y -> put X |

## Core Operating Rules

1. Decompose the goal into ordered sub-goals — locate, acquire, transform,
   deliver — and complete each before the next.
2. Search systematically: check each surface and container exactly once;
   open closed containers (drawers, cabinets, fridge) before judging them
   empty. Keep a persistent searched set of exact instances (`drawer 1`,
   `shelf 3`); never revisit an instance already observed to lack the target
   while still searching — the searched set is global for the episode.
3. Prioritize semantically likely locations first (food in fridges, on
   countertops, dining tables; dishes/cookware on counters, tables,
   stoveburners, cabinets, drawers; desk items on desks, shelves, dressers,
   sidetables; newspapers on coffeetables, sidetables, sofas), then broaden
   to any unvisited admissible `go to` location after 3-4 misses in one
   class. For kitchen items, check broad exposed surfaces early before
   opening many cabinets; for office/bedroom items, alternate drawers with
   open surfaces.
4. Grab immediately when the target is visible and reachable. Take only the
   exact requested object type — a cup is not a mug, a pot is not a pan;
   similar objects are distractors.
5. Transform before placing: clean/heat/cool at the appliance before heading
   to the destination. Use direct commands (`clean X with sinkbasin`, `heat X
   with microwave`, `cool X with fridge`, `use desklamp`) as soon as they are
   admissible; don't toggle, open, or examine appliances unnecessarily.
6. Direct delivery: navigate straight to the remembered destination
   receptacle instance and place. If the object starts at the destination but
   needs a state change, take it out, transform it, and place it back in the
   same instance.
7. Never repeat the same action more than twice in a row; if stuck, move to
   a different unexplored location.
8. Track the remaining-object count; stop only when it reaches zero and
   every goal condition is verified (placed, right receptacle, right state).

## Search-Loop Recovery

- Exact-instance lockout: a searched instance stays locked out of search
  until you are holding the object or ready to deliver. Appliance and
  destination locations are tools, not search targets — don't revisit the
  sink, microwave, fridge, or destination while empty-handed.
- Finite-class exhaustion: once every visible instance of a small class
  (stoveburners, diningtables, countertops) is checked, mark the class
  exhausted; search different classes instead of a second pass.
- Unvisited beats likely-but-searched: prefer any unvisited admissible
  location over a semantically likely, already-searched one. Recency is not
  a reset — a location doesn't become unsearched because it left the recent
  observations.
- Destination-as-source: if the destination type is also a plausible source,
  inspect each destination instance once early (the target may already be
  there); after it lacks the target, remember one instance as the final
  destination and stop using it as a search target until delivery.

## Pick-Two Discipline

Choose one destination receptacle instance and place both objects there.
After the first placement, don't start a fresh search: return directly to
the remembered source of the second instance if seen, otherwise continue
from the unsearched-location ledger. If the objects end up split across
receptacles, consolidate into the chosen target.

## Search-Loop Hard Rules

- Fast broadening: after 3–4 misses in the same receptacle class, switch to
  a different likely class or any unvisited admissible location instead of
  continuing or restarting that class, unless the target has already been
  seen there.
- Finite-class exhaustion: if all visible instances of a small class have
  been checked once — all stoveburners, diningtables, countertops, or
  shelves — mark that class exhausted for object search and do not start a
  second pass. Remember a usable destination instance, then search different
  receptacle classes.
- Before every empty-handed search action, apply this hard filter: (1) if a
  required target object is visible, take it immediately; (2) otherwise
  choose an exact receptacle/surface/container instance whose contents have
  not yet been observed in the current object-search phase; (3) reject any
  `go to`, `examine`, or `open` action for an instance already observed to
  lack the target, even if it is semantically likely, nearby, recently
  mentioned, or the final destination type; (4) if all likely instances are
  rejected by the ledger, broaden to any unvisited admissible location.
- The searched ledger survives inventory checks, appliance visits, placing
  the first object in a pick-two task, and putting down an irrelevant
  inspected object. These events are not permission to rescan.

## Task-Specific Search Orders

- Pan-to-stoveburner: one quick pass over stoveburners only to find a pan
  or remember an empty destination, then leave burners until delivery; next
  check countertops and sinkbasins; then cabinets in numeric order before
  low-yield drawers. Do not abandon cabinet search to revisit searched
  burners, countertops, or drawers.
- Kettle/teapot clean-and-place: after checking obvious countertops, check
  stoveburners and sinkbasins once, then cabinets in numeric order; if
  several cabinets are empty, continue to the next unsearched cabinet or
  broaden to unvisited shelves/carts/dining tables. Remember one open/empty
  cabinet as the final destination.
- Dishsponge clean-and-place: check sinkbasin and nearby countertops once,
  then unvisited cabinets, drawers, shelves, carts. The sink is needed for
  cleaning — remember it after the first visit and do not go back while
  empty-handed; the shelf destination is remembered after one inspection and
  locked out of search until delivery.

## Appliance Specifics

- Sinkbasin is the cleaning station: `clean mug 1 with sinkbasin 1`. If the
  object is already clean and the task doesn't ask for cleaning, skip the
  sink entirely.
- Microwave is heating only; if `heat X with microwave` is admissible, use it
  directly — do not open it first just to heat.
- Fridge serves two roles: cooling station and the most common food source.
  Open it while searching for food; do not open it just to cool something
  unless the task says cool.
- Desklamp: `use desklamp 1` while holding the object. The lamp is not a
  container; nothing goes in or on it.

## Step Budget

Rough budget per task family: 5–10 steps for object search, 2–4 for the
appliance, 2–4 for delivery, slack for one wrong turn. If search exceeds 30
steps, treat it as looping regardless of how reasonable the plan feels, and
switch to any unvisited location. Never re-check a "likely" location out of
politeness — the environment rewards novel locations, not re-verification.

## Termination

Verify every goal condition before stopping: object(s) placed in the right
receptacle, in the right state (clean, hot, or cool), remaining-object count
at zero. Episodes ended one step early — with the second egg unfound or the
object delivered uncleaned — are complete failures, not partial successes.

## Recap of the Discipline

1. Parse the goal; hold object type, required state change, and destination
   fixed for the episode.
2. Search each instance once, ledger it, and never rescan.
3. Take the exact object the moment it is visible.
4. Transform before placing, at the remembered appliance.
5. Deliver directly to the remembered destination instance.
6. Count remaining objects and verify all goal conditions before ending.

<!-- SLOW_UPDATE_START -->
Preserve the successful pattern: when the exact requested object is visible,
take it immediately; perform the required clean/heat/cool/use action as soon
as the correct command is admissible; then deliver directly to the
remembered destination instance.

Use a next-unsearched-instance pointer for every numbered class (cabinets,
drawers, shelves, countertops, stoveburners): resume at the lowest unobserved
instance, never restart at instance 1, never revisit an instance already
observed to lack the target. When the step budget is running low and you are
still empty-handed, prefer any unvisited admissible location over any
searched likely location.

The searched-instance ledger, the state-change checklist, and the
remaining-object count together cover every observed failure mode: search
loops (revisiting searched instances, class restarts, appliance camping),
skipped clean/heat/cool steps, and stopping one object short on a pick-two
task. Maintain all three and the episode resolves without additional
planning.
<!-- SLOW_UPDATE_END -->

## Observation Discipline

- Scan each observation once in a fixed order: target object present?
  needed appliance present? closed container worth noting? Register all
  three and move on.
- Mark a container searched the moment you observe its contents, even if
  it held only distractors.
- Register appliance locations during object search even when not
  immediately needed; return trips after acquisition should be direct.

## Object-Category Search Order

- Cold food: fridge first. Pans/pots: one pass over stoveburners, then
  countertops, then cabinets in numeric order.
- Sponges/soap: near the sinkbasin once, then cabinets and shelves — never
  return to the sink while empty-handed.
- Newspapers/magazines: coffeetable and sofa first. Small flat objects
  (cards, CDs): drawers before open surfaces.

## Failure Modes

Nearly every failed episode is one of three bookkeeping failures:
revisiting searched locations, skipping a required clean/heat/cool step,
or stopping one object short on a pick-two. The searched ledger, the
state-change checklist, and the remaining-object count fix all three.
