# ALFWorld Agent Playbook

For text-based household tasks: find objects, move them, apply appliances,
deliver to receptacles. The environment gives you an admissible action list
every step — never invent actions outside it.

Output `<think>...</think>` then `<action>...</action>` each turn.

## The six task shapes

| Task | Sequence |
|------|----------|
| Put X in/on Y | find X → take X → go to Y → put X in/on Y |
| Two X in/on Y | find X₁ → take → place in Y → find X₂ → take → place in same Y |
| Examine X with lamp | find X → take X → find desklamp → use desklamp |
| Clean & place | find X → take → clean at sinkbasin → go to Y → put |
| Heat & place | find X → take → heat at microwave → go to Y → put |
| Cool & place | find X → take → cool at fridge → go to Y → put |

Two rules follow directly:

- **Transform before delivery.** If the task says clean/heat/cool, do it at
  the appliance *before* heading to the destination. Never place an uncleaned
  object and call it done.
- **One receptacle for pick-two.** Pick the destination instance once, place
  both objects there. Don't split them across two drawers.

## Searching without wasting steps

You will spend most of your steps finding objects. Do it like you mean it.

- Check semantically likely spots first: food in the fridge or on
  countertops; dishes and cookware on counters, dining tables, stoveburners,
  cabinets, drawers; desk items on desks, shelves, dressers, sidetables;
  newspapers on coffeetables and sofas.
- Open closed containers before judging them empty — drawers and cabinets
  hide things.
- **Keep a searched list.** Once you've seen `drawer 1` and it had no mug,
  `drawer 1` is done. Never go back "just to check" — that's how episodes
  die. The searched list is global for the whole episode; a location doesn't
  become unsearched because you walked away.
- Miss three or four times in one receptacle class? Switch classes. Try any
  unvisited location before re-walking the likely ones. An unvisited cabinet
  beats a re-visited countertop every time.
- If the object is visible, take it. Now. Don't explore "one more room"
  first.
- Take the *exact* object type. Task says mug, you see a cup — that's a
  distractor. Leave it.
- If the destination is also a likely source (spoon goes in a drawer, and
  drawers hold spoons), check the destination instance once early — the
  object may already be there.

## Appliances and tools

- The appliance commands are direct: `clean X with sinkbasin`, `heat X with
  microwave`, `cool X with fridge`, `use desklamp`. Use them the moment
  they're admissible and you're holding the object.
- Don't burn steps toggling, opening, or examining appliances you don't need
  to open. A microwave you're only heating with doesn't need to be opened.
- Found the appliance early? Remember where it is, then go back to searching
  for the object. Don't camp there.

## Bookkeeping

- Count what's left. Pick-two tasks need two placements — stop when the count
  hits zero, not when it feels done.
- Remember where you saw things. If you passed the second egg on your way to
  the first, you already know where to go back.
- The desklamp task: hold the object, be where the lamp is, `use desklamp`.
  Don't put the object on or in the lamp.

## Loop avoidance

Never repeat the same action twice in a row. If the same observation comes
back twice, you're in a loop — go somewhere new. The recovery is always:
pick an unvisited receptacle or location and go there.

## Termination

Verify every goal condition before stopping: object(s) placed, in the right
receptacle, in the right state (clean/hot/cool). If anything is missing, the
episode isn't over.

## Appliance specifics

- **Sinkbasin**: the cleaning station. `clean mug 1 with sinkbasin 1`. If
  the object is already clean and the task doesn't ask for cleaning, skip
  the sink entirely.
- **Microwave**: heating only. Closed is fine — you don't open a microwave
  to heat something in this world; if `heat X with microwave` is in the
  admissible list, use it directly.
- **Fridge**: cooling, but also the most common food source. Open it when
  searching for food; don't open it just to cool something unless the task
  says cool.
- **Desklamp**: `use desklamp 1` while holding the object. The lamp is not
  a container; nothing goes in or on it.

## Object-specific search notes (from experience)

- **Pans and pots**: stoveburners first (often sitting right there), then
  countertops, then cabinets. One quick pass over the burners; don't camp.
- **Kettles and teapots**: countertops and stoveburners, then cabinets in
  numeric order.
- **Sponges and soap**: near the sinkbasin and on bathroom counters — but
  check the basin area once, then move on; sponges hide in cabinets more
  than you'd think.
- **Food items**: fridge, then countertop, then dining table. Cold items
  (lettuce, tomato) strongly favor the fridge.
- **Newspapers and magazines**: coffeetable and sofa, almost always. Sidetable
  as backup.
- **Credit cards, CDs, small electronics**: desk drawers, sidetable drawers,
  then shelves. Small flat objects live in drawers.
- **Towels**: bathroom — toilet, bathtub, shelf. Sometimes drawer.

## Reading observations efficiently

Each observation dumps everything visible in the location. Scan it in this
order: (1) is my target object here? (2) is an appliance here I'll need
later? (3) any closed container I should note? Register all three in one
pass and move on. Agents that re-read the same observation three times are
agents that run out of steps.

## A note on failure

Nearly every failed episode I've seen comes from one of three things:
revisiting searched locations, skipping a required clean/heat/cool step, or
stopping one object short on a pick-two. All three are bookkeeping failures,
not intelligence failures. Keep the searched list, keep the state-change
checklist, keep the count — the rest of the game is easy.

## Step budget intuition

Episodes give you a generous but finite number of actions. Rough budget
for a typical task: 5–10 steps to find the object, 2–4 for the appliance,
2–4 for delivery, slack for one wrong turn. If you're at 30 steps and still
searching, you're looping — stop, pick any unvisited location, and go. The
single worst pattern is polite re-checking of "likely" spots; the
environment doesn't reward politeness, it rewards novelty.

## A last word on confidence

The environment is deterministic — the same action in the same state always
does the same thing. Which means: if something didn't work, it will not
work on retry. Change the action or change the target. The agents that
finish reliably are the ones that treat every failed action as information
("this door doesn't open / this location doesn't have it") and update their
map immediately, not the ones that hope harder.

## Putting it together

A complete episode, start to finish: parse the goal; note the object type
and the destination; search the likely class once through; on a miss,
broaden immediately; take the object the moment it appears; detour to the
appliance only if a state change is required; walk straight to the
remembered destination; place; count what's left; repeat if needed; verify
and stop. Ten to twenty actions, no wasted motion, no revisited shelves.
That's the whole game.
