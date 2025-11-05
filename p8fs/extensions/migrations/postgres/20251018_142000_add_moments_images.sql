-- Migration: Add images array to Moments table
-- Created: 2025-10-18 14:20:00
-- Description: Adds an images array column to store URIs of representative images for moments

-- Add images column to moments table
ALTER TABLE public.moments
    ADD COLUMN IF NOT EXISTS images TEXT[];

-- Add GIN index for array operations
CREATE INDEX IF NOT EXISTS idx_moments_images_gin ON public.moments USING GIN (images);

-- Add comment to explain column purpose
COMMENT ON COLUMN public.moments.images IS 'URIs to representative images associated with this moment (e.g., screenshots, photos, visualizations)';
