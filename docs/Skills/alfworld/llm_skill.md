# Guide to Embodied Household Tasks (ALFWorld)

## Overview
You are operating in a simulated household environment. Your goal is to
complete household tasks by navigating rooms, finding objects, and
interacting with appliances and furniture. At each step, the environment
provides a list of admissible actions — you must choose your action from
this list.

Output format: reason inside `<think>...</think>`, then state your chosen
action inside `<action>...</action>`.

## Task Types

ALFWorld tasks come in a small number of patterns:

1. **Pick and Place**: Move an object to a receptacle.
   Find the object, take it, go to the destination, put it down.
2. **Pick Two and Place**: Move two instances of an object to a receptacle.
   Repeat the pick-and-place cycle twice, using the same destination.
3. **Examine in Light**: Examine an object under a desk lamp.
   Find the object, take it, locate a desklamp, and use it.
4. **Clean and Place**: Clean an object with soap/sink and place it.
   Take the object to a sinkbasin, clean it, then deliver it.
5. **Heat and Place**: Heat an object in the microwave and place it.
   Take the object to the microwave, heat it, then deliver it.
6. **Cool and Place**: Cool an object in the fridge and place it.
   Take the object to the fridge, cool it, then deliver it.

## General Strategy

**Step 1: Understand the goal.** Identify the target object, the required
state change (if any), and the destination receptacle.

**Step 2: Search systematically.** Objects are located on surfaces and
inside containers. Useful locations by object type:

- Food items: fridge, countertop, dining table, sinkbasin.
- Dishes and cookware: countertop, dining table, stoveburner, cabinet,
  drawer, sinkbasin.
- Towels and linens: bathtub, toilet, shelf, cabinet, dresser.
- Office and desk items: desk, shelf, drawer, sidetable, dresser.
- Newspapers and magazines: coffeetable, sidetable, sofa, tvstand.
- Lamps: desklamp, sidetable, shelf, drawer.

Explore the environment methodically. Check each location once. Open closed
containers (cabinets, drawers, fridges) to inspect their contents before
moving on. Keep a mental map of where you have been and what you have seen.

**Step 3: Take the object.** When you find the target object, take it
immediately. Do not continue exploring.

**Step 4: Apply the required transformation.** If the task requires
cleaning, heating, or cooling, go to the appropriate appliance:

- Cleaning: go to a sinkbasin and `clean` the object.
- Heating: go to the microwave and `heat` the object.
- Cooling: go to the fridge and `cool` the object.

**Step 5: Deliver.** Go to the destination receptacle and put the object
in or on it.

## Important Rules

- **Only use admissible actions.** The environment lists valid actions each
  step. Never guess an action that is not listed.
- **Complete the transformation before delivery.** If a task says heat the
  object, the object must be hot when placed.
- **Use the same destination for two-object tasks.** Both instances go to
  the same receptacle.
- **Avoid repeating actions.** If the same action fails twice, change your
  approach and try a different location.
- **Track your progress.** Count how many objects still need to be found and
  placed. The task is complete only when all requirements are satisfied.
- **Check visible objects first.** If the target object is already visible
  in the current observation, take it rather than searching elsewhere.

## Example Reasoning Flow

```
Observation: You are in the kitchen. You see a countertop, a fridge,
and a cabinet.
Task: Put a clean mug on the coffeetable.

Think: I need a mug. Mugs are often on countertops or in cabinets.
I'll check the countertop first.
Action: go to countertop 1

... (search until mug found) ...

Think: I found the mug. Take it.
Action: take mug from countertop 1

Think: The task requires cleaning. I'll go to the sink.
Action: go to sinkbasin 1

Think: Clean the mug.
Action: clean mug with sinkbasin 1

Think: The mug is clean. Deliver it to the coffeetable.
Action: go to coffeetable 1

Think: Place the mug.
Action: put mug in/on coffeetable 1
```

## Common Mistakes to Avoid

- Searching the same location repeatedly.
- Forgetting to clean/heat/cool the object before placing it.
- Taking a similar but incorrect object (e.g., a cup when a mug is
  requested).
- Ending the episode before all objects are placed.
- Wasting steps on irrelevant actions like opening containers you have
  already checked.

Follow this guide and complete tasks efficiently.

## Detailed Search Strategies

### Systematic Room Coverage

Rooms contain multiple receptacle types. A practical order for most
searches:

1. Check all visible open surfaces (countertops, tables, shelves) in the
   current location.
2. Open and check closed containers (cabinets, drawers, fridge) one at a
   time, marking each as searched.
3. Move to the next room or area and repeat.

### Finding Specific Object Categories

- **Kitchen items** (mugs, plates, pots, utensils): kitchen countertops,
  dining table, stoveburners, then cabinets and drawers.
- **Bathroom items** (towels, soap, sponges): near sinks, on toilet or
  bathtub, in bathroom cabinets and shelves.
- **Bedroom items** (clothes, pillows, personal items): bed, dresser,
  nightstand/sidetable, wardrobe.
- **Living room items** (remote controls, magazines, decorations):
  coffeetable, sofa, tvstand, shelves.
- **Office items** (pens, papers, electronics): desk, desk drawers,
  shelves, sidetable.

### Handling Multiple Instances

When a task requires two instances of an object, remember where you saw
each one during your first search. If you saw two eggs while collecting the
first, you already know where the second is — go directly there instead of
searching again.

### Managing Your Memory

Keep track of:
- Locations you have fully searched (and found empty of your target).
- Where you saw target objects.
- Where useful appliances are (sinkbasin, microwave, fridge, desklamp).
- The chosen destination receptacle (for multi-object tasks).

This mental map is the difference between finishing in twenty steps and
running out of steps entirely.

## Efficiency Checklist

- Are you moving with purpose (toward a known target) rather than
  wandering?
- Have you opened every closed container in the current room?
- Are you marking searched locations so you never re-check them?
- Are you doing transformations (clean/heat/cool) at the right time?
- Do you know exactly how many objects remain before the task is complete?

Efficient agents finish tasks; inefficient agents run out of steps. Follow
this guide and you will be an efficient agent.
