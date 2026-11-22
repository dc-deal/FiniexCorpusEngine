"""The names the index database's configuration and its Compose services share (issue #10)."""

PASSWORD_ENV = 'CORPUS_DB_PASSWORD'  # the database user's password, in the git-ignored .env, read by Compose and the code
HOST_ENV = 'CORPUS_DB_HOST'  # a container's own host for the database (`postgres`), set by Compose
PORT_ENV = 'CORPUS_DB_PORT'  # and its port there (5432)
URL_ENV = 'CORPUS_DATABASE_URL'  # a whole connection URL, which wins over every other setting where it is set
MIGRATIONS_TABLE = 'schema_migrations'  # the ledger of applied migrations
