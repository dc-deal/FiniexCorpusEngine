"""No evaluation question appears in a prompt or a schema description.

A question from the datasets in the router's prompt, even as a harmless-looking example, would tune
the router to the exam: it would score well on exactly the questions that measure it. The held-out
set would lose its point too.
"""

import json
import re
from pathlib import Path

from backend.chat import chat_agent, chat_turn
from backend.search import query_routing

ROOT = Path(__file__).resolve().parents[2]


def normalise(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def test_no_dataset_question_is_in_the_prompts():
    prompts = normalise(' '.join([
        query_routing.ROUTER_SYSTEM, query_routing.MULTI_QUERY_TEMPLATE,
        json.dumps(query_routing.QueryPlan.model_json_schema()),
        json.dumps(query_routing.SearchQueries.model_json_schema()),
        chat_turn.GENERATOR_SYSTEM, json.dumps(chat_turn.Answer.model_json_schema()),
        chat_turn.OFF_TOPIC_TEXT, chat_turn.HARMFUL_TEXT, chat_agent.AGENT_SYSTEM,
    ]))
    found = []
    for name in ('eval_questions.json', 'eval_questions_holdout.json'):
        for question in json.loads((ROOT / 'evaluation' / name).read_text(encoding='utf-8'))['questions']:
            if normalise(question['question']) in prompts:
                found.append(question['id'])
    assert found == []
