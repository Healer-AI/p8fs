# Workers Module

## Overview

Workers were initially implemented in a previous version as a proof of concept. This module represents the refactored implementation.

## Project Dependencies

The parent project includes several modules that are available on the classpath:

- **p8fs**: Current module containing worker implementations
- **p8fs-cluster**: Logging utilities, environment access, and other utilities
- **p8fs-node**: Media and content processors, AI model access

## Worker Types

### 1. Storage Workers
Process files from job queues and index content per tenant (user):
- Embeddings generation
- Graph edge extraction
- Metadata processing

### 2. Dreaming Workers
Perform first and second-order post-processing of user content:
- Identify relationships between audio logs and uploaded files
- Generate additional content based on existing data

## Execution Modes

### Storage Worker
The storage worker module supports multiple execution modes:

- **File Processing**: Process individual files from S3 or local filesystem
- **Queue Processing**: Consume from NATS worker queue when connected
- **Command Line Arguments**: 
  - `--file`: Process a specific file
  - `--queue`: Consume from queue

### Dreaming Worker
The dreaming worker supports several operational modes:

1. **Default Mode**: Read user sessions and resources from repository, submit jobs in batch or direct mode
   - **Batch Mode**: Submit job requests to OpenAI
   - **Direct Mode**: Process directly against any model using Memory proxy and DreamModel

2. **Completion Mode**: Scan for submitted batch jobs stored in database, fetch and save results

3. **Queue Mode**: Consume from work queues (marked as TODO)

## Implementation Guidelines

- Workers should be thin wrappers around tenant repository and Memory proxy
- Keep orchestration code simple and minimal
- Storage workers should load content providers as required
- Implement Typer interface for each worker for easy interaction
- Write minimal code when porting from original implementation

## Code Organization

### Engram Processor
- Move Engram and its logic to: `p8fs/src/p8fs/models/engram`
- Based on a typing system for content processing

### Dreaming Worker
- Move to models library under: `p8fs/src/p8fs/models/agentlets`