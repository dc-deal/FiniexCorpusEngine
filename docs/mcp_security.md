# Security of the librarian (the MCP server)

The librarian, [`search_server.py`](../src/backend/search/search_server.py), answers any MCP client: a coding session, the chat,
an evaluation run. This chapter walks through the course's MCP security points (the RAG sprint's lesson on MCP security
essentials, the agents sprint's least privilege) and gives, for each, what the server does and the code or test that shows it.
The last section names what is left open.

## Who can reach it

| door | who is behind it | what guards it |
|---|---|---|
| stdio, the default | the process that started the server: Claude Code, the chat, an evaluation run | it runs as that user, so what it may do is limited by its tools, not by the operating system |
| streamable HTTP (`--http PORT`) | processes on this machine, and containers through `host.docker.internal` | bound to 127.0.0.1, a bearer token, the SDK's Host and Origin checks |
| the corpus itself | whoever wrote a page the model reads | the passages are data: the prompt says so, code checks every quote, nothing a model writes is rendered raw |

The third door is the one a RAG system opens by design: the model reads text that no one here wrote.

## The course's points, one by one

| point | what the server does | evidence |
|---|---|---|
| **Supply chain** (a compromised package) | the official `mcp` SDK, as in the course's workshop; every Python dependency pinned with `==`; the diagnostics UI's npm packages are locked and needed only to build it, and the built files are committed, so a reviewer runs no npm | [requirements.txt](../requirements.txt), each pin with its reason; [test_requirements_cover_imports.py](../tests/contracts/test_requirements_cover_imports.py) fails on an import the file does not pin |
| **Command injection** (43 % of the servers tested, OWASP MCP Top 10) | no tool reaches a shell, a subprocess or `eval`; no argument becomes a path. A work is a key in a dictionary built from the catalog, a page is a key beside it, and a page image is rendered only for a known work and a page made of digits | [search_server.py:444~446](../src/backend/search/search_server.py#L444-L446), `open_page` as one dictionary lookup; [search_server.py:472](../src/backend/search/search_server.py#L472), the digit check before a page is rendered |
| **Local execution means local access** (stdio runs with the user's rights) | every tool reads: `works`, `search_works`, `toc`, `search`, `semantic_search`, `open_page`, `page_image`. None writes, deletes, runs a program or fetches an address a client names. The server writes one file of its own, its call log | [search_server.py:590](../src/backend/search/search_server.py#L590), the call log, git-ignored, never a page's text |
| **The HTTP transport** | bound to 127.0.0.1; refuses to start without a token in `.env`; a request needs exactly one `Authorization` header, compared in constant time; the SDK refuses a foreign Host header (DNS rebinding: a page elsewhere whose name resolves to 127.0.0.1) and any browser Origin | [search_server.py:832~860](../src/backend/search/search_server.py#L832-L860), the host list and the token gate; [search_server.py:918~922](../src/backend/search/search_server.py#L918-L922), no token, no start; [test_search_server.py:115](../tests/test_search_server.py#L115) and [:131](../tests/test_search_server.py#L131), real requests refused with 401, 421 and 403 |
| **The confused deputy** (a server that follows the model instead of the user) | the server holds a provider key, but no tool lets a caller use it for anything other than the server's own fixed retrieval chain: a router and a generator, with prompts in code. No tool takes an instruction, a URL or a model name | [search_server.py:806](../src/backend/search/search_server.py#L806), `semantic_search` takes a question and a number of hits, nothing else |
| **Least privilege** | the chat starts its server with `--public-only`, which never reads the private knowledge base, so no title, hit or page of it can leak through the chat. The chat's agent sees five of the server's seven tools, by an allow-list, so a tool added to the server does not reach the agent unasked | [search_server.py:734~738](../src/backend/search/search_server.py#L734-L738), the switch; [chat_agent.py:182](../src/backend/chat/chat_agent.py#L182), the chat's server; [chat_agent.py:249](../src/backend/chat/chat_agent.py#L249), the allow-list; [test_search_server.py:307](../tests/test_search_server.py#L307) |
| **"Curated" is not "verified"** (indirect prompt injection through retrieved text) | the generator's prompt says the passages are data, not instructions; a quote stands only if code finds it word for word in a passage; citations and licences come from metadata, never from the model; the agent never retells the server's answer (`return_direct`); its loop is capped at 5 model and 4 tool calls | [chat_turn.py:72](../src/backend/chat/chat_turn.py#L72), the rule in the prompt; [chat_turn.py:136~142](../src/backend/chat/chat_turn.py#L136-L142), the quote check; [chat_agent.py:154](../src/backend/chat/chat_agent.py#L154), `return_direct` |
| **Model output is untrusted** | the diagnostics UI passes model text through markdown-it with HTML off and then DOMPurify's allow-list, which keeps no image, so a reply cannot make the browser call a third party | [render_markdown.ts](../src/frontend/diagnostics/src/render_markdown.ts), the two layers |
| **Tool descriptions** (tool poisoning) | static strings in the server's code, under version control; nothing a client or a page says changes them | [search_server.py:584](../src/backend/search/search_server.py#L584), the server's instructions |
| **Bounded work** | 1 to 50 hits, a contents depth of 1 to 6, a question of at most 2,000 characters, each refused before any work; an unknown corpus or work is refused, not guessed | [search_server.py:61~63](../src/backend/search/search_server.py#L61-L63), the hits bound; [test_search_server.py:60](../tests/test_search_server.py#L60) |
| **Logs** | the call log keeps the query, the client's name and the pages that answered, never a page's text; whatever a client sends reaches the terminal without a control character, so a question cannot clear or rewrite the operator's screen | [search_server.py:612~615](../src/backend/search/search_server.py#L612-L615), `printable`; [test_search_server.py:262](../tests/test_search_server.py#L262) |
| **Keys** | API keys and the server's token live in the git-ignored `.env`, are read in the backend process and never reach a client; the bearer token is never passed on to a provider | [.env.example](../.env.example), the names without values |

## What is left open

- **Indirect prompt injection is mitigated, not measured.** No set of hostile pages has been run against the generator; a
  dedicated injection guard stayed a bonus task. What a hostile page could still do: steer the wording around true quotes in
  one answer. It cannot invent a quote (code drops it), change a citation (metadata), trigger a side effect (no tool has one)
  or put markup in front of the user (sanitised).
- **No rate limit.** `semantic_search` spends a router and a generator call on the provider key each time. A client with the
  token, or a host that starts the server over stdio, can spend until the key's own spending limit stops it. The chat's agent is
  capped per message; the server is not capped per client.
- **One shared token,** no rotation and no per-client scopes. The client name in the log is what the client says about itself:
  it identifies, it does not authenticate.
- **Pins are versions, not hashes,** and the suite runs no vulnerability scan. Next step: `pip-audit` in the suite and
  `--require-hashes` for the install.
- **The private knowledge base is withheld by a start switch.** Without `--public-only` a local client of the owner's server sees
  it, which is its purpose; a fresh clone has no private base at all, and the chat always passes the switch.
