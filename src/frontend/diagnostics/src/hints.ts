/**
 * Every explanation the views give, in one registry (decision 179, from the operator's viewer's rules): what a control does, or
 * what a part of a view means, said once, by its name, through `HintToggle` and `HintPanel` and no other way. A hint that
 * needs the API's own figures, such as the route levels' words or the splitter's sizes, gives them through its panel's
 * slot; its lead sentence stands here.
 */
export interface Hint {
  // what the toggle says to a screen reader and in its hover
  label: string
  // the hint's first sentence, before any figures its view adds
  lead: string
}

export const HINTS = {
  routes: {
    label: 'What the route levels mean',
    lead: 'How each page\'s text is served: its reading as checked, its reading with a note, or the PDF\'s text layer in its place.',
  },
  overlap: {
    label: 'What the dashed line means',
    lead: 'Text a chunk shares with the chunk before it, repeated so a sentence cut at the border stays findable in both.',
  },
} satisfies Record<string, Hint>

export type HintId = keyof typeof HINTS
