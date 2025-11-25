#!/usr/bin/env python3
"""
Compile migrations and SQL functions for P8FS deployment.

This script performs critical tasks:
1. Optionally regenerates SQL from Python models (--refresh)
2. Copies latest migration to entity schema file for deployment
3. Compiles individual SQL function files into a single 03_functions.sql file
"""

import sys
import shutil
import argparse
import subprocess
from pathlib import Path

def sync_entity_schema():
    """Copy latest migration to entity schema file for deployment."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    migration_file = repo_root / "extensions" / "migrations" / "postgres" / "install.sql"
    schema_file = repo_root / "extensions" / "sql" / "01_entity_schema.sql"
    
    if not migration_file.exists():
        print(f"Error: Migration file not found: {migration_file}")
        return False
    
    print(f"Syncing entity schema...")
    print(f"  Source: {migration_file}")
    print(f"  Target: {schema_file}")
    
    # Copy the migration file to schema file
    shutil.copy2(migration_file, schema_file)
    
    print(f"✅ Entity schema synced successfully")
    return True

def compile_sql_functions():
    """Compile individual SQL function files into 03_functions.sql."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    functions_dir = repo_root / "extensions" / "sql" / "functions"
    output_file = repo_root / "extensions" / "sql" / "03_functions.sql"
    
    if not functions_dir.exists():
        print(f"Error: Functions directory not found: {functions_dir}")
        return False
    
    # Get all SQL files, put header.sql first if it exists
    all_sql_files = list(functions_dir.glob("*.sql"))
    
    if not all_sql_files:
        print(f"No SQL files found in {functions_dir}")
        return False
    
    # Sort files, but put header first
    header_file = functions_dir / "header.sql"
    sql_files = []
    
    if header_file.exists():
        sql_files.append(header_file)
    
    # Add all other files sorted alphabetically, excluding utility scripts
    excluded_files = {"header.sql", "load_age_functions.sql", "reload_functions.sql"}
    other_files = sorted([f for f in all_sql_files if f.name not in excluded_files])
    sql_files.extend(other_files)
    
    print(f"Found {len(sql_files)} SQL files to compile:")
    for f in sql_files:
        print(f"  - {f.name}")
    
    # Combine all files
    combined_content = []
    
    for sql_file in sql_files:
        print(f"Processing {sql_file.name}...")
        content = sql_file.read_text()
        
        # Add file marker comment
        combined_content.append(f"\n-- ================================================")
        combined_content.append(f"-- Source: functions/{sql_file.name}")
        combined_content.append(f"-- ================================================\n")
        combined_content.append(content.rstrip())
        combined_content.append("")  # Empty line between files
    
    # Write combined content
    full_content = "\n".join(combined_content)
    output_file.write_text(full_content)
    
    print(f"\n✅ Successfully compiled {len(sql_files)} files into {output_file.name}")
    print(f"   Output: {output_file}")
    
    return True

def refresh_sql_from_models():
    """Regenerate SQL from Python models."""
    script_dir = Path(__file__).parent
    generate_script = script_dir / "generate_sql_from_models.py"
    
    if not generate_script.exists():
        print(f"Error: SQL generation script not found: {generate_script}")
        return False
    
    print("🔄 Refreshing SQL from Python models...")
    
    # Run the generation script
    result = subprocess.run(
        [sys.executable, str(generate_script)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ SQL generation failed:")
        print(result.stderr)
        return False
    
    print(result.stdout)
    return True


def main():
    """Main entry point with optional model refresh."""
    parser = argparse.ArgumentParser(description="Compile P8FS migrations and SQL functions")
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=True,
        help="Regenerate SQL from Python models before compilation (default: True)"
    )
    parser.add_argument(
        "--no-refresh",
        dest="refresh",
        action="store_false",
        help="Skip SQL regeneration from models"
    )
    
    args = parser.parse_args()
    
    print("🚀 P8FS Migration Compilation")
    print("=" * 50)
    
    # Step 0: Optionally refresh SQL from models
    if args.refresh:
        refresh_success = refresh_sql_from_models()
        if not refresh_success:
            print("❌ SQL refresh from models failed")
            sys.exit(1)
        print()  # Empty line between steps
    
    # Step 1: Sync entity schema
    schema_success = sync_entity_schema()
    if not schema_success:
        print("❌ Entity schema sync failed")
        sys.exit(1)
    
    print()  # Empty line between steps
    
    # Step 2: Compile functions  
    functions_success = compile_sql_functions()
    if not functions_success:
        print("❌ Function compilation failed")
        sys.exit(1)
    
    print("\n🎉 Migration compilation completed successfully!")
    print("   Ready for deployment:")
    print("   - extensions/sql/01_entity_schema.sql")
    print("   - extensions/sql/03_functions.sql")
    
    if args.refresh:
        print("\n   Note: SQL regenerated from Python models with JSONB types")
    
    sys.exit(0)


if __name__ == "__main__":
    main()