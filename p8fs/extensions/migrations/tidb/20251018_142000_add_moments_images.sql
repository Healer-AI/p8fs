-- Migration: Add images array to Moments table (TiDB)
-- Created: 2025-10-18 14:20:00
-- Description: Adds an images JSON array column to store URIs of representative images for moments

-- Use the public database
USE `public`;

-- Add images column to moments table
-- Note: TiDB stores arrays as JSON text
ALTER TABLE moments
    ADD COLUMN IF NOT EXISTS images TEXT COMMENT 'URIs to representative images associated with this moment (e.g., screenshots, photos, visualizations)';
