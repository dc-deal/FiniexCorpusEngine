"""How the catalog and the exports spell the data's folders: a contract between every writer and reader of a stored path.

Imports nothing, so any module can import it without a cycle.
"""

# The folders a stored path may begin with that lie in the local data folder, in the repository's layout.
DATA_FOLDERS = ('corpus/raw', 'corpus/readings', 'evaluation/results')
