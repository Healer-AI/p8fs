-- Add encryption_key_owner column to resources table
ALTER TABLE resources
ADD COLUMN encryption_key_owner VARCHAR(50);

-- Create index for filtering by encryption mode
CREATE INDEX idx_resources_encryption_key_owner
ON resources (encryption_key_owner);
