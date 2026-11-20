import type { Component } from 'vue'
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconBan,
  IconCircleCheck,
  IconCircleDashed,
  IconCircleX,
  IconEyeOff,
  IconFileText,
  IconFlag,
  IconGavel,
  IconHistory,
  IconInfoCircle,
  IconLock,
  IconMenu2,
  IconPlayerStop,
  IconQuote,
  IconRobot,
  IconSearch,
  IconShieldCheck,
  IconUserCheck,
  IconUserEdit,
  IconUserX,
  IconWorld,
} from '@tabler/icons-vue'

/**
 * Every icon the UI draws, named by what it MEANS: one meaning has one drawing everywhere, and a wrong name is a type
 * error rather than an empty square. `status-*` is a state that is always said in words as well. The drawings are Tabler
 * Icons (MIT), stroke 2, in the colour of the element they sit in.
 */
export const ICONS = {
  'status-error': IconAlertCircle,
  'status-ok': IconCircleCheck,
  'status-unjudged': IconCircleDashed,
  'status-issue': IconCircleX,
  'status-blocked': IconBan,
  'status-stopped': IconPlayerStop,
  'status-unknown': IconAlertTriangle,
  // a page a person settled (211.a): counted apart from the issues, never as fine, a decision's drawing
  'status-decided': IconGavel,
  // a page an automated review settled (Q.a, 18 Nov): apart from a person's, a machine's drawing
  'status-reviewed': IconRobot,
  // a PDF page no reader has read yet (V1.b): quiet, since nothing is wrong with it, a page not looked at
  'status-not-read': IconEyeOff,
  // a finding of the judge, beside its kind and severity
  'finding': IconFlag,
  // the text the search and the chat quote for a page, beside the reading as parsed and as stored
  'quoted': IconQuote,
  // the knowledge base a row belongs to, beside its name: open to all, or licensed and kept on this machine
  'kb-free': IconWorld,
  'kb-licensed': IconLock,
  // a hint on demand, such as what a dashed line means; its button is named for a screen reader
  'hint': IconInfoCircle,
  // a route served by a fallback in the reading's place, the PDF's text layer or a licensed work's legacy Markdown (H2.a),
  // beside the word "fallback"
  'route-fallback': IconFileText,
  // the frame's menu of every view, beside the tool's name; its button is named for a screen reader
  'menu': IconMenu2,
  // a person's standing verdict on a page's reading (166.a), beside the judge's state and always said in words too
  'person-accepted': IconUserCheck,
  'person-rejected': IconUserX,
  'person-noted': IconUserEdit,
  // an automated review's standing verdict, never a person's (the operator's 2.a, 18 Nov), always said in words too
  'review': IconRobot,
  // the view shows a recalled judgement, not the standing state (181.a), always with the words "Recalled:"
  'recalled': IconHistory,
  // a person checked the page and no re-read happens without a reason (191.a), always said in words too
  'protected': IconShieldCheck,
  // a facet bar's search folded into its button (Y1.a), named for a screen reader
  'action-search': IconSearch,
} satisfies Record<string, Component>

export type IconName = keyof typeof ICONS
