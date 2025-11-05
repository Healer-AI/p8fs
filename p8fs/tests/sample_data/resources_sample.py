#!/usr/bin/env python3
"""
Sample Resources data for testing upserts and embeddings functionality.

This module provides sample Resources models with embedding fields
for testing the repository and embedding service integration.
"""

# Add src to path for imports
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

script_dir = Path(__file__).parent
repo_root = script_dir.parent.parent
src_dir = repo_root / "src"
sys.path.insert(0, str(src_dir))

from p8fs.models.p8 import Resources


def create_sample_resources() -> list[Resources]:
    """Create sample Resources models for testing."""
    
    resources = [
        Resources(
            id=str(uuid4()),
            name="Python Best Practices Guide",
            category="documentation",
            content="""
            Python is a powerful programming language that emphasizes code readability and simplicity. 
            Here are some key best practices:
            
            1. Follow PEP 8 style guidelines for consistent code formatting
            2. Use meaningful variable names that describe their purpose
            3. Write docstrings for all functions, classes, and modules
            4. Keep functions small and focused on a single task
            5. Use type hints to improve code clarity and catch errors early
            6. Handle exceptions appropriately with try-except blocks
            7. Use virtual environments to manage dependencies
            8. Write tests for your code using pytest or unittest
            9. Use list comprehensions for simple data transformations
            10. Follow the principle of least surprise in API design
            
            These practices will help you write more maintainable and professional Python code.
            """,
            summary="A comprehensive guide covering essential Python programming best practices including PEP 8, type hints, testing, and code organization.",
            ordinal=1,
            uri="https://docs.python.org/best-practices",
            metadata={
                "author": "Python Software Foundation",
                "language": "python",
                "difficulty": "intermediate",
                "tags": ["best-practices", "coding-standards", "python"]
            },
            resource_timestamp=datetime.now(),
            userid="user123"
        ),
        
        Resources(
            id=str(uuid4()),
            name="Machine Learning Fundamentals",
            category="education",
            content="""
            Machine learning is a subset of artificial intelligence that focuses on building systems
            that can learn and improve from data without being explicitly programmed.
            
            Key concepts include:
            
            **Supervised Learning**: Learning from labeled training data to make predictions
            - Classification: Predicting categories (email spam detection)
            - Regression: Predicting continuous values (house prices)
            
            **Unsupervised Learning**: Finding patterns in data without labels
            - Clustering: Grouping similar data points
            - Dimensionality reduction: Simplifying data while preserving information
            
            **Popular algorithms**:
            - Linear regression for continuous predictions
            - Decision trees for interpretable models
            - Neural networks for complex pattern recognition
            - K-means for clustering
            
            **Data preprocessing** is crucial and includes:
            - Cleaning and handling missing values
            - Feature engineering and selection
            - Scaling and normalization
            - Train/validation/test split
            
            Success in ML requires understanding both the mathematics and practical implementation.
            """,
            summary="An introduction to machine learning covering supervised/unsupervised learning, popular algorithms, and data preprocessing techniques.",
            ordinal=2,
            uri="https://ml-course.example.com/fundamentals",
            metadata={
                "author": "Dr. Sarah Chen",
                "domain": "machine-learning",
                "difficulty": "beginner",
                "tags": ["machine-learning", "ai", "algorithms", "data-science"]
            },
            resource_timestamp=datetime.now(),
            userid="user456"
        ),
        
        Resources(
            id=str(uuid4()),
            name="RESTful API Design Principles",
            category="architecture",
            content="""
            REST (Representational State Transfer) is an architectural style for designing web APIs
            that are scalable, maintainable, and easy to use.
            
            **Core principles:**
            
            1. **Stateless**: Each request contains all information needed to process it
            2. **Resource-based**: URLs represent resources, not actions
            3. **HTTP methods**: Use standard verbs (GET, POST, PUT, DELETE)
            4. **Uniform interface**: Consistent naming and structure
            
            **Best practices:**
            
            - Use nouns for endpoints: /users, /orders, /products
            - HTTP status codes: 200 (OK), 201 (Created), 404 (Not Found), 500 (Error)
            - Version your APIs: /v1/users, /v2/users
            - Implement pagination for large datasets
            - Use HTTPS for security
            - Provide clear error messages with details
            
            **Example endpoints:**
            - GET /api/v1/users - List all users
            - GET /api/v1/users/123 - Get specific user
            - POST /api/v1/users - Create new user
            - PUT /api/v1/users/123 - Update user
            - DELETE /api/v1/users/123 - Delete user
            
            Following these principles creates APIs that are intuitive and developer-friendly.
            """,
            summary="Guidelines for designing RESTful APIs including core principles, best practices, and example endpoint patterns.",
            ordinal=3,
            uri="https://api-design.example.com/rest-principles",
            metadata={
                "author": "Engineering Team",
                "domain": "web-development",
                "difficulty": "intermediate",
                "tags": ["rest", "api", "web-services", "architecture"]
            },
            resource_timestamp=datetime.now(),
            userid="user789"
        ),
        
        Resources(
            id=str(uuid4()),
            name="Docker Container Basics",
            category="devops",
            content="""
            Docker is a containerization platform that allows you to package applications
            and their dependencies into lightweight, portable containers.
            
            **Key concepts:**
            
            - **Container**: A running instance of an image
            - **Image**: A blueprint for creating containers
            - **Dockerfile**: Instructions for building images
            - **Registry**: Repository for storing and sharing images
            
            **Basic commands:**
            
            ```bash
            # Build an image
            docker build -t myapp:latest .
            
            # Run a container
            docker run -p 8080:80 myapp:latest
            
            # List containers
            docker ps
            
            # Stop container
            docker stop container_id
            
            # Remove container
            docker rm container_id
            ```
            
            **Dockerfile example:**
            ```dockerfile
            FROM python:3.9-slim
            WORKDIR /app
            COPY requirements.txt .
            RUN pip install -r requirements.txt
            COPY . .
            EXPOSE 8000
            CMD ["python", "app.py"]
            ```
            
            **Benefits:**
            - Consistent environments across development, testing, and production
            - Easy deployment and scaling
            - Isolation between applications
            - Efficient resource utilization
            """,
            summary="Introduction to Docker containerization covering key concepts, basic commands, and Dockerfile creation for application packaging.",
            ordinal=4,
            uri="https://docker-tutorial.example.com/basics",
            metadata={
                "author": "DevOps Team",
                "domain": "containerization",
                "difficulty": "beginner",
                "tags": ["docker", "containers", "devops", "deployment"]
            },
            resource_timestamp=datetime.now(),
            userid="user101"
        ),
        
        Resources(
            id=str(uuid4()),
            name="PostgreSQL Query Optimization",
            category="database",
            content="""
            Query optimization is crucial for maintaining good database performance as your
            data grows. Here are key strategies for optimizing PostgreSQL queries.
            
            **Indexing strategies:**
            - B-tree indexes for equality and range queries
            - GIN indexes for full-text search and JSON queries
            - Partial indexes for filtered queries
            - Composite indexes for multi-column searches
            
            **Query analysis tools:**
            ```sql
            -- Analyze query execution plan
            EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'user@example.com';
            
            -- Check index usage
            SELECT schemaname, tablename, indexname, idx_tup_read, idx_tup_fetch
            FROM pg_stat_user_indexes;
            ```
            
            **Optimization techniques:**
            1. **Avoid SELECT ***: Only select needed columns
            2. **Use LIMIT**: Paginate large result sets
            3. **Optimize WHERE clauses**: Put most selective conditions first
            4. **Use EXISTS instead of IN**: For better performance with subqueries
            5. **Consider materialized views**: For complex aggregations
            6. **Analyze statistics**: Keep table statistics up to date
            
            **Common performance pitfalls:**
            - Missing indexes on frequently queried columns
            - Inefficient JOIN conditions
            - N+1 query problems in application code
            - Outdated table statistics
            
            Regular monitoring and optimization ensures your database performs well under load.
            """,
            summary="Comprehensive guide to PostgreSQL query optimization including indexing strategies, analysis tools, and common performance pitfalls.",
            ordinal=5,
            uri="https://postgres-docs.example.com/optimization",
            metadata={
                "author": "Database Team",
                "domain": "database",
                "difficulty": "advanced",
                "tags": ["postgresql", "database", "optimization", "performance"]
            },
            resource_timestamp=datetime.now(),
            userid="user202"
        )
    ]
    
    return resources


if __name__ == "__main__":
    """Test sample data creation."""
    sample_resources = create_sample_resources()
    
    print(f"Created {len(sample_resources)} sample resources:")
    for resource in sample_resources:
        print(f"- {resource.name} ({resource.category})")
        print(f"  Content length: {len(resource.content)} characters")
        print(f"  Has embedding fields: content={bool(resource.content)}, summary={bool(resource.summary)}")
        print()