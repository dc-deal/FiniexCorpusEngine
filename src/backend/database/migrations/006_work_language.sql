-- Every work names the language of its text (issue #11): ISO 639-1, from its catalog. The column may be empty for the rows a
-- whole import replaces; the import itself refuses a work without one, so after it every work has its language.
ALTER TABLE works ADD COLUMN language TEXT;
