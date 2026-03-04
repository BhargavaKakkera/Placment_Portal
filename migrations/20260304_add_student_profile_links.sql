-- Adds student profile link columns for existing databases.
-- Run this once on an existing DB if you do not want RESET_DB=1.

ALTER TABLE student ADD COLUMN resume_url TEXT;
ALTER TABLE student ADD COLUMN github_url TEXT;
ALTER TABLE student ADD COLUMN linkedin_url TEXT;
ALTER TABLE student ADD COLUMN leetcode_url TEXT;
ALTER TABLE student ADD COLUMN codeforces_url TEXT;
ALTER TABLE student ADD COLUMN hackerrank_url TEXT;
ALTER TABLE student ADD COLUMN portfolio_url TEXT;
ALTER TABLE student ADD COLUMN other_coding_url TEXT;
