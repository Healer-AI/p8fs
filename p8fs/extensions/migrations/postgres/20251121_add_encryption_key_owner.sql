-- Add encryption_key_owner column to resources table
ALTER TABLE public.resources
ADD COLUMN IF NOT EXISTS encryption_key_owner TEXT;

-- Create index for filtering by encryption mode
CREATE INDEX IF NOT EXISTS idx_resources_encryption_key_owner
ON resources (encryption_key_owner);

-- Add comment
COMMENT ON COLUMN public.resources.encryption_key_owner IS 'Who owns/manages the encryption key (USER|SYSTEM|NONE)';
