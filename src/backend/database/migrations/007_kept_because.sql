-- A kept edition says why the other one is served (#15): the reason the editions list gives (E1.a), so a client sees it was
-- chosen, not a slip. Empty for every work that is not a kept edition.
ALTER TABLE works ADD COLUMN kept_because TEXT;
