# Optimized Instructions — ALFWorld

1. Parse the goal into ordered sub-goals — locate, acquire, transform,
   deliver — and complete each before moving to the next.

2. Output `<think>...</think>` for reasoning, then `<action>...</action>`
   for the chosen action, every turn.

3. Choose actions only from the admissible action list; never invent
   actions.

4. Search each surface and container exactly once; open closed containers
   before judging them empty.

5. Keep a persistent searched set of exact receptacle instances; never
   revisit an instance already observed to lack the target while still
   searching.

6. Prioritize semantically likely locations first (food in fridges and on
   counters; cookware on counters, burners, and tables; desk items on desks
   and shelves), then broaden to any unvisited admissible location after
   3-4 misses in one class.

7. When the target object is visible and reachable, take it immediately.

8. Take only the exact requested object type; similar objects are
   distractors.

9. If the task requires cleaning, heating, or cooling, perform the state
   change at the appliance before heading to the destination; use direct
   commands (`clean X with sinkbasin`, `heat X with microwave`, `cool X
   with fridge`) as soon as they are admissible.

10. Do not revisit the sink, microwave, fridge, or destination while
    empty-handed; remember their locations and return only after acquiring
    the object.

11. Remember the destination receptacle instance and deliver directly to
    the same instance; if the object starts at the destination, take it,
    transform it, and place it back.

12. For pick-two tasks, place both instances into one chosen receptacle
    instance; after the first placement, return directly to the remembered
    source of the second instance.

13. Never repeat the same action more than twice in a row; if stuck, move
    to a different unexplored location.

14. Maintain an internal count of objects remaining; do not stop until
    every goal condition is verified — placed, in the right receptacle, in
    the right state.

15. Check destination-as-source locations once early: the target may
    already be in the fridge, on the diningtable, or in the destination
    drawer.

16. Scan each observation once in a fixed order: target object present?
    needed appliance present? closed container present? Register all three
    and move on.

17. Mark a container searched the moment you observe its contents, even if
    it held only distractors.

18. Register appliance locations during object search even when not
    immediately needed; return trips should be direct.

19. Search rooms in a fixed order: open surfaces first, then closed
    containers one at a time, then move to the next area.

20. For kitchen items, check countertops, dining table, and stoveburners
    before opening cabinets and drawers.

21. For bathroom items, check sink area, toilet, and bathtub before
    cabinets and shelves.

22. For bedroom items, check bed, dresser, and sidetable before drawers.

23. For office items, check desk and open shelves before drawers.

24. For newspapers and magazines, check coffeetable and sofa first.

25. For small flat objects (cards, CDs), check drawers before open
    surfaces.

26. For cold food items, check the fridge first.

27. For pans and pots, make one quick pass over stoveburners, then check
    countertops, then cabinets in numeric order; do not revisit searched
    burners.

28. For sponges and soap, check near the sinkbasin once, then search
    cabinets and shelves; do not return to the sink while empty-handed.

29. When a task requires two instances, note where each instance was seen
    during the first search; return directly to the remembered location
    for the second.

30. Choose the destination receptacle instance once and stay with it for
    all placements in the task.

31. If the target object starts at the destination and needs a state
    change, take it out, transform it, and place it back in the same
    instance.

32. Check destination-type receptacles once early during object search —
    the target may already be there.

33. After observing a destination instance without finding the target,
    remember it for delivery and stop using it as a search target.

34. Prefer any unvisited admissible location over any searched location
    when the step budget is low.

35. Never treat a recently mentioned location as unsearched; the searched
    set is global and permanent for the episode.

36. Resume numbered classes at the lowest unobserved instance; never
    restart at instance 1.

37. Treat broadening as moving to an unvisited class or the next unsearched
    instance, never as restarting a searched class.

38. Count remaining objects before and after every placement; the task
    ends at zero, verified.

39. Verify each goal condition explicitly before ending: correct object,
    correct state, correct receptacle.

40. When an action errors or the observation does not change, switch to an
    unvisited location instead of retrying.

41. Budget roughly 5–10 steps for object search, 2–4 for the appliance,
    2–4 for delivery; if search exceeds 30 steps, treat it as looping and
    switch to any unvisited location.

42. Do not re-check "likely" locations out of politeness; the environment
    rewards novel locations, not re-verification.

43. Register observed distractor types per location so a second search of
    the same class can be skipped entirely when the distractor set implies
    the class is exhausted.

44. Prefer breadth over depth early: cover all rooms' open surfaces before
    exhausting any one room's containers.

45. After each placement, restate the remaining goal aloud in the think
    block before choosing the next action.

46. End the episode only after verifying: correct object type, correct
    state, correct receptacle instance, remaining count zero.

47. If an action fails twice, abandon that approach entirely and choose a
    different verb or a different target instance.

48. Keep the think block short — reasoning that restates the whole plan
    every step wastes attention on stale context.

49. Treat every failed action as information about the state — this
    receptacle doesn't contain it, this door doesn't open — and update the
    searched map immediately.

50. The environment is deterministic: an action that failed will fail
    again; change the action or the target, never the hope.

54. Before the first action, parse the goal into object type, required
    state change, and destination receptacle type; hold all three fixed
    for the episode.

55. During search, log in the think block the exact instances checked this
    phase so the ledger survives observation truncation.

56. On acquiring the object, state the remaining sub-goals aloud (which
    appliance, which destination instance) before the next action.

57. At the appliance, apply the state-change command directly; do not
    narrate or re-verify the plan while holding the object.

58. On arrival at the destination, place immediately; do not re-examine
    the receptacle's other contents first.

59. After a placement, decrement the remaining count explicitly and, if
    the count is nonzero, name the next remembered source before moving.

60. Keep think blocks to one or two sentences grounded in the ledger —
    long restatements of the full plan waste attention on stale context.

61. Treat the searched ledger as write-once: an instance observed to lack
    the target never returns to the candidate set during the search phase.

62. When the admissible list offers both an examination and a movement,
    prefer movement to an unvisited location over re-examination of a
    visited one.

63. When the observation lists an object you will need later (second
    instance, appliance-adjacent object), record its location in the think
    block immediately — later observations will not repeat it.

64. If the admissible list contains an action for an already-searched
    instance and an action for an unvisited one, always choose the
    unvisited one during the search phase.

65. If the goal object is visible inside an open container in the current
    observation, take it before any movement action.

66. Close open containers only when closing is required for the task;
    open/closed state affects which actions are admissible at the
    destination.

67. When placing, use the exact receptacle instance remembered at task
    start unless it was verified unavailable.

68. Trust the admissible list over your plan: if your intended action is
    absent, adapt the plan to the available actions rather than emitting
    the unavailable one.
