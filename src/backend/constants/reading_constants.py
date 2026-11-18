"""How a reading off the default reader names itself, shared by the module that stores it and the ones that show it."""

# A page read in a Claude Code session (decision 280.a, route `direct reading`): the deviation its record carries, which the
# served route and the diagnostics view recognise it by.
DIRECT_DEVIATION = 'read in a Claude Code session (280.a)'
DIRECT_ROUTE_KIND = 'direct reading'

# A verdict a Claude Code session gave on the operator's delegation names the session as its giver, "claude-opus-5-5 session,
# delegated by the operator (17 Nov)"; a person's names the person ("maintainer", the command line's and the view's default).
# The operator, 18 Nov: "a person is always manual": only a person's verdict is called a person's, and only it protects a page
# (191.a), since a person who signs a verdict takes the responsibility for it, as with a contract.
DELEGATED_MARK = 'session, delegated by the operator'
AUTOMATED_REVIEW = 'an automated review (delegated by the operator)'
