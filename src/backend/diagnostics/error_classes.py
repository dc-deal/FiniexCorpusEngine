"""Error classes (line 1's order for the operator's 146.a and 147.a): the findings of the export grouped by what they are, so a kind
of error that recurs in one class of block, or in one work, stands out with its count and its pages.

Read from the export's rows, never counted anywhere else: the judge's findings (`check.verdict.findings`, each with its
kind, its block's class and whether the core found it void) and stage 2's (`check.stage2.findings`, the reading against
the text layer, by kind). A void finding names no difference, so it is kept apart from the ones that count, never dropped.
Under `--public-only` only the free knowledge base's rows are read (81.a).
"""

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from backend.diagnostics.readings import Count, KnowledgeBase, Readings

Stage = Literal['judge', 'stage 2']


class ErrorClass(BaseModel):
    stage: Stage  # the judge, or stage 2 against the text layer
    kind: str
    block_class: str | None  # the judged block's class; stage 2 names no class
    void: bool  # the judge's findings the core found to name no difference, apart
    knowledge_base: KnowledgeBase
    source_id: str
    title: str
    findings: int
    pages: list[int]  # the PDF pages that carry such a finding, each once, in order


class ErrorClassList(BaseModel):
    classes: list[ErrorClass]  # by findings, most first
    stages: list[Count]
    kinds: list[Count]
    knowledge_bases: list[Count]


def error_classes(bases: dict[str, Readings]) -> ErrorClassList:
    grouped: dict[tuple, list[int]] = defaultdict(list)
    titles: dict[tuple[str, str], str] = {}
    for name, store in bases.items():
        for row in store.rows():
            check = row.get('check') or {}
            work = (name, row['source_id'])
            if work not in titles:
                listed = store.work(row['source_id'])
                titles[work] = (listed or {}).get('title') or row['source_id']
            for finding in (check.get('verdict') or {}).get('findings') or []:
                grouped[('judge', finding.get('kind') or '?', finding.get('block_class'), bool(finding.get('void')), *work)].append(row['pdf_page'])
            for finding in (check.get('stage2') or {}).get('findings') or []:
                grouped[('stage 2', finding.get('kind') or '?', None, False, *work)].append(row['pdf_page'])
    classes = [ErrorClass(stage=stage, kind=kind, block_class=block_class, void=void, knowledge_base=name, source_id=source_id,
                          title=titles[(name, source_id)], findings=len(pages), pages=sorted(set(pages)))
               for (stage, kind, block_class, void, name, source_id), pages in grouped.items()]
    classes.sort(key=lambda one: (-one.findings, one.stage, one.kind, one.block_class or '', one.source_id))

    def counted(values: list[str]) -> list[Count]:
        totals: dict[str, int] = defaultdict(int)
        for one, value in zip(classes, values):
            totals[value] += one.findings
        return [Count(value=value, count=count) for value, count in sorted(totals.items(), key=lambda pair: -pair[1])]

    return ErrorClassList(classes=classes, stages=counted([one.stage for one in classes]),
                          kinds=counted([one.kind for one in classes]),
                          knowledge_bases=counted([one.knowledge_base for one in classes]))
