-- Code as a source (issue #12): a work of source files names its programming language and the work it accompanies. Both
-- are empty for a work of text, so every work imported before stays as it is.
ALTER TABLE works ADD COLUMN code_language TEXT;
ALTER TABLE works ADD COLUMN companion_of TEXT;
