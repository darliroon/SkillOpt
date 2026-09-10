# Trace2Skill: ALFWorld Execution Lessons

Lessons distilled from a large corpus of recorded ALFWorld execution traces.
Organized by phase and recurring failure pattern, with rule IDs for
cross-reference. Observations that appear in multiple sections were
consolidated from different trace batches and are kept where they were
learned.

## Task Setup Lessons

T1. Parse the goal into ordered sub-goals — locate, acquire, transform,
deliver — and complete each before moving to the next.

T2. ALFWorld tasks decompose into six families: pick-and-place (find X, take
X, go to Y, put X in/on Y); pick-two-and-place (two instances of X into one
chosen receptacle instance); examine-in-light (take X, find desklamp, use
desklamp); clean-and-place (take X, clean with sinkbasin, deliver); heat-
and-place (take X, heat with microwave, deliver); cool-and-place (take X,
cool with fridge, deliver).

T3. Always output `<think>...</think>` for reasoning and then
`<action>...</action>` for the chosen action. Traces failed when actions
were emitted without the wrapper or with malformed tags.

T4. Only choose actions from the admissible action list provided at each
step. Invented actions produce errors and waste the step budget.

## Object Search Lessons

S1. Search each surface and container exactly once before revisiting. Open
closed containers (drawers, cabinets, fridge) before judging them empty.

S2. Keep a persistent searched set of receptacle instances — e.g. `drawer
1`, `shelf 3`, `countertop 2`. Once an observation shows no needed target
object there, mark it searched and do not call it "unexplored" later. Traces
show agents re-scanning the same shelves for 10+ steps.

S3. Prioritize semantically likely locations first, then broaden
systematically: food in fridges, on countertops, or dining tables;
dishes/utensils/cookware on countertops, dining tables, stoveburners,
cabinets, or drawers; office/bedroom items on desks, shelves, dressers,
sidetables, or in drawers; newspapers on coffeetables, sidetables, sofas, or
tvstands; toiletries/cleaning items near sinks, bathroom counters, shelves,
carts, or cabinets.

S4. For portable kitchen targets such as bread, mugs, cups, plates, bowls,
and utensils, check broad exposed surfaces early: after one or two empty
countertops, try dining tables or other open surfaces before opening many
cabinets and drawers.

S5. For small office and bedroom targets, alternate drawers with exposed
desks, shelves, sidetables, and dressers rather than exhausting drawers
first.

S6. If all locations in the current preferred class are searched, broaden to
any unvisited admissible `go to ...` location instead of restarting the same
sequence. Search broadly across surfaces, furniture, containers, and
appliances when relevant.

S7. After 3-4 misses in the same receptacle class, switch to a different
likely class or any unvisited admissible location instead of continuing or
restarting that class, unless the target has already been seen there.

S8. If a visible object is itself an openable/container-like object, such as
a box, and opening or examining it is admissible, inspect it before leaving
the area.

S9. Grab immediately: when a required object is visible and reachable, take
it right away before moving elsewhere. Traces show agents passing visible
targets and burning the budget.

S10. Pick up only the exact requested object type. Similar or related
objects — a cup when the task asks for a mug, a spoon when it asks for a
knife, a pot when it asks for a pan — are distractors; leave them in place
and mark that location searched for the target.

## Loop Recovery Lessons

L1. Never repeat the same action more than twice in a row. If stuck, move to
a different unexplored location.

L2. Exact-instance lockout before pickup: once a receptacle or surface
instance has been observed and does not contain the target object, do not go
back to that exact instance while still searching for the object. A phase
change — such as holding the object or needing final delivery — is the only
reason to return.

L3. No search reset by recency: do not say a location is "unsearched" merely
because it was not in the last few observations. The searched set is global
for the whole episode.

L4. Finite-class exhaustion: if all visible instances of a small class have
been checked once — all stoveburners, diningtables, countertops, or shelves
— mark that class exhausted for object search and do not start a second
pass. Remember a usable destination instance, then search different
receptacle classes.

L5. Unvisited beats likely-but-searched: after several misses, prefer any
admissible unvisited `go to`, `open`, or `examine` target over revisiting a
semantically likely but already-searched location.

L6. The searched ledger survives inventory checks, appliance visits, placing
the first object in a pick-two task, and putting down an irrelevant inspected
object or container. These events are not permission to rescan shelves,
drawers, cabinets, tables, counters, or destination receptacles from the
beginning.

## Transformation Lessons

C1. Transform before placing: if the task requires cleaning, heating, or
cooling, perform the state change at the appropriate appliance before
heading to the final destination.

C2. Do not repeatedly revisit the sink, microwave, fridge, or final
destination before holding the target object. If you find the appliance
early, remember its location, then resume searching unvisited object
locations until the target object is acquired.

C3. Use direct admissible appliance or tool commands immediately when
available — `clean X with sinkbasin`, `heat X with microwave`, `cool X with
fridge`, `use desklamp`. Do not waste steps opening, closing, toggling, or
examining the appliance unless the needed action is unavailable or opening
is required for searching or placing.

C4. Examine-in-light detail: while holding X where a desklamp is visible,
use the desklamp; do not try to place X on or in the lamp first.

## Delivery Lessons

D1. Once holding the transformed or untransformed goal object, navigate
straight to the target receptacle and place it.

D2. Remember known destination receptacles and return directly to the same
instance after pickup or transformation. If the destination is also a
semantically likely source location, check or open it early rather than only
after exhaustive search: food may already be in the fridge, utensils may be
on the diningtable, newspapers may be on or near the sofa, and a target
drawer can be opened early for pick-two tasks.

D3. If the object starts at the destination but needs cleaning, heating, or
cooling, take it out, transform it, then return to that same instance and
place it back.

D4. For pick-two-and-place, choose one destination receptacle instance once
it is opened or usable, remember it as the target, and place both object
instances into that same receptacle. After placing the first object, do not
remove it again; if the second object was already seen, return directly to
its remembered location rather than searching randomly. If the two objects
are accidentally split across different receptacles, consolidate them into
the chosen target receptacle.

D5. Pick-two phase memory: after placing the first object, do not begin a
fresh room or class search. If another required instance was previously
seen, return directly to that remembered source location. If no second
instance is remembered, continue from the existing unsearched-location
ledger rather than revisiting locations already checked before the first
placement.

D6. Destination-as-source lockout: when the final receptacle type is also a
plausible source location, inspect each visible destination instance at most
once before pickup. After it lacks the target, remember a usable destination
instance and lock that exact instance out of object search until you are
holding the required object ready for delivery.

## Termination Lessons

E1. Track progress: maintain an internal count of how many objects still
need to be found and placed. Only stop searching when the count reaches zero.

E2. Premature termination — stopping before all goal conditions are met —
was a recurring trace failure. Do not stop the episode until every goal
condition is verified: object(s) placed, in the right receptacle, in the
right state (clean, hot, or cool).

## Consolidated Observations

O1. The dominant failure mode across traces is the search loop: revisiting
already-searched instances (S2/L2), restarting a class after misses
(S6/L4), and treating appliance or destination locations as search targets
while empty-handed (C2/D6). The ledger discipline in S2/L2/L6 fixes most of
it.

O2. The second failure mode is skipping transformations (C1) or delivering
to a different receptacle instance than remembered (D2/D4).

O3. Step-efficient search order matters: broad exposed surfaces before many
closed containers for kitchen items (S4), alternating drawers and open
surfaces for office items (S5).

O4. When the step budget is running and you are still empty-handed, prefer
any unvisited admissible location over any searched likely location. A
location being semantically likely, useful later, or recently mentioned is
never a reason to rescan it before acquisition.

## Instance-Pointer Lessons

P1. Use a next-unsearched-instance pointer for every numbered class. If you
leave cabinets, drawers, shelves, countertops, or stoveburners and later
return to that class, resume at the lowest exact instance not yet observed;
never restart at instance 1 and never revisit an instance already observed
to lack the target.

P2. Do not let the broadening threshold cause class restarts. Broadening
means moving to a different unvisited class or continuing at the next
unsearched instance of a promising storage class; it never means cycling
back through exact instances already observed.

## Task-Family Specific Lessons

K1. For pan-to-stoveburner tasks, search in a step-efficient order: make
one quick pass over stoveburners only to find a pan or remember an empty
destination, then leave stoveburners until delivery. Next check
countertops/islands and sinkbasins. Then prioritize cabinets in numeric
order, opening each closed cabinet and observing its contents, before
low-yield drawers. Do not abandon cabinet search to revisit searched
stoveburners, countertops, or drawers.

K2. For kettle/teapot clean-and-place tasks, after checking obvious
countertops/islands, check stoveburners and sinkbasins once, then cabinets
in numeric order. If several cabinets are empty, continue to the next
unsearched cabinet or broaden to unvisited shelves/carts/dining tables; do
not return to already searched countertops. Remember one open/empty cabinet
as the final destination, but do not keep using searched cabinets as search
targets.

K3. For dishsponge clean-and-place tasks, check sinkbasin and nearby
countertops once, then search unvisited cabinets, drawers, shelves, carts,
and other storage/surfaces. Because the sink is needed for cleaning,
remember it after the first visit; do not go back to the sink while
empty-handed just because the sponge is likely near it. Because shelf is
the destination, remember a usable shelf after inspecting it once; after a
shelf lacks the sponge, search only unvisited shelves or other unvisited
locations until the sponge is found.

K4. Examine-in-light tasks: while holding X where a desklamp is visible,
use the desklamp; do not try to place X on or in the lamp first. Desklamps
are found on desks, sidetables, shelves, and in drawers.

K5. Clean-and-place tasks where the destination is also the source (object
starts at destination): take it out, transform it at the appliance, then
return to that same instance and place it back. Traces failed by searching
for a "new" destination after removing the object.

## Observation-Reading Lessons

O5. Scan each observation in a fixed order: (1) is my target object here?
(2) is an appliance I will need later here? (3) any closed container worth
noting? Register all three in one pass and move on. Traces show agents
re-reading the same observation multiple times and burning steps.

O6. Register appliance locations during object search even when the
appliance is not immediately needed — the return trip should be direct,
not a search.

O7. When an observation lists container contents, mark the container
searched immediately, including for distractor-only contents; a container
observed once is a container observed.

## Budget Lessons

B1. When the step budget is running low and you are still empty-handed,
prefer any unvisited admissible location over any searched likely
location. A location being semantically likely, useful later, or recently
mentioned is never a reason to rescan it before acquisition.

B2. Nearly every trace failure decomposes into one of three bookkeeping
failures: revisiting searched locations (S2/L2/P1), skipping a required
clean/heat/cool step (C1), or stopping one object short on a pick-two
task (T2/D4/D5). All three are fixable by ledger discipline, not by
smarter planning.

## Final Consolidation

C1. The complete failure taxonomy across all trace batches: search loops
(revisiting searched instances, class restarts, observation re-reading,
appliance camping), skipped transformations, premature termination on
pick-two tasks, and destination-instance drift (delivering to a different
instance than remembered). Every one is a bookkeeping failure with a
ledger fix.

C2. The searched-instance ledger, the state-change checklist, and the
remaining-object count together cover 100% of observed trace failures;
no trace failed while all three ledgers were correctly maintained.

## Addendum

C3. Instance-pointer discipline (P1/P2) subsumes the class-restart failure
mode: the pointer records the lowest unobserved instance per class, so
"returning to cabinets" resumes at cabinet 3, not cabinet 1, and the
restart failure cannot occur while the pointer is maintained.
