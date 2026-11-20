/**
 * How long the pointer rests on a host before its card opens (the operator's C1.b, 20 Nov: "die Tooltips bitte mit etwas mehr
 * Delay"): 500 ms, so a pointer crossing a table on its way opens nothing, while the keyboard's focus opens the card at once.
 * One value for every card. The unit tests set it to 0 (`tests/setup.ts`), so a card there opens on the pointer as before, and
 * one test holds the delay itself.
 */
export const HOVER_DELAY = { pointerMs: 500 }
