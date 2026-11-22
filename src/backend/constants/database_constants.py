"""The names the index database's configuration and its Compose services share (issue #10, part A)."""

PASSWORD_ENV = 'CORPUS_DB_PASSWORD'  # the database user's password, in the git-ignored .env, read by Compose and the code
URL_ENV = 'CORPUS_DATABASE_URL'  # a whole connection URL; a container gets it from Compose, since its host is `postgres`
MIGRATIONS_TABLE = 'schema_migrations'  # the ledger of applied migrations
