"""
Database Migration Runner
Usage: python migrate.py [command] [options]

Commands:
  up [migration_name]     - Apply migration(s)
  down [migration_name]   - Rollback migration(s) 
  status                  - Show migration status
  create <name>           - Create new migration file
  fresh                   - Drop all tables and re-run all migrations
  reset                   - Rollback all migrations
"""

import os
import sys
import importlib.util
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import re

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Arceus123Mewtow',
    'database': 'foodlinker_db'
}

MIGRATIONS_DIR = 'migrations'

def get_database_connection():
    """Get database connection"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"❌ Error connecting to MySQL: {e}")
        return None

def ensure_migrations_table():
    """Ensure migrations tracking table exists"""
    connection = get_database_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        connection.commit()
        return True
    except Error as e:
        print(f"❌ Error creating migrations table: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def get_migration_files():
    """Get list of migration files sorted by name"""
    if not os.path.exists(MIGRATIONS_DIR):
        return []
    
    migration_files = []
    for filename in os.listdir(MIGRATIONS_DIR):
        if filename.endswith('.py') and filename != '__init__.py':
            migration_files.append(filename)
    
    return sorted(migration_files)

def get_applied_migrations():
    """Get list of applied migrations from database"""
    connection = get_database_connection()
    if not connection:
        return []
    
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT migration_name FROM migrations ORDER BY migration_name")
        return [row[0] for row in cursor.fetchall()]
    except Error as e:
        print(f"❌ Error fetching applied migrations: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def load_migration_module(migration_file):
    """Load migration module from file"""
    migration_path = os.path.join(MIGRATIONS_DIR, migration_file)
    spec = importlib.util.spec_from_file_location("migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def apply_migration(migration_file):
    """Apply a single migration"""
    try:
        print(f"📦 Applying migration: {migration_file}")
        module = load_migration_module(migration_file)
        
        if hasattr(module, 'up'):
            success = module.up()
            if success:
                # Record migration as applied
                connection = get_database_connection()
                if connection:
                    try:
                        cursor = connection.cursor()
                        cursor.execute("""
                            INSERT IGNORE INTO migrations (migration_name) 
                            VALUES (%s)
                        """, (migration_file,))
                        connection.commit()
                    except Error as e:
                        print(f"❌ Error recording migration: {e}")
                    finally:
                        cursor.close()
                        connection.close()
                print(f"✅ Migration {migration_file} applied successfully!")
                return True
            else:
                print(f"❌ Migration {migration_file} failed!")
                return False
        else:
            print(f"❌ Migration {migration_file} has no 'up' function!")
            return False
    except Exception as e:
        print(f"❌ Error applying migration {migration_file}: {e}")
        return False

def rollback_migration(migration_file):
    """Rollback a single migration"""
    try:
        print(f"📦 Rolling back migration: {migration_file}")
        module = load_migration_module(migration_file)
        
        if hasattr(module, 'down'):
            success = module.down()
            if success:
                # Remove migration record
                connection = get_database_connection()
                if connection:
                    try:
                        cursor = connection.cursor()
                        cursor.execute("""
                            DELETE FROM migrations WHERE migration_name = %s
                        """, (migration_file,))
                        connection.commit()
                    except Error as e:
                        print(f"❌ Error removing migration record: {e}")
                    finally:
                        cursor.close()
                        connection.close()
                print(f"✅ Migration {migration_file} rolled back successfully!")
                return True
            else:
                print(f"❌ Migration {migration_file} rollback failed!")
                return False
        else:
            print(f"❌ Migration {migration_file} has no 'down' function!")
            return False
    except Exception as e:
        print(f"❌ Error rolling back migration {migration_file}: {e}")
        return False

def migrate_up(target_migration=None):
    """Apply migrations"""
    if not ensure_migrations_table():
        return False
    
    migration_files = get_migration_files()
    applied_migrations = get_applied_migrations()
    
    if target_migration:
        # Apply specific migration
        if target_migration not in migration_files:
            print(f"❌ Migration {target_migration} not found!")
            return False
        
        if target_migration in applied_migrations:
            print(f"⚠️ Migration {target_migration} already applied!")
            return True
        
        return apply_migration(target_migration)
    else:
        # Apply all pending migrations
        pending_migrations = [mf for mf in migration_files if mf not in applied_migrations]
        
        if not pending_migrations:
            print("✅ No pending migrations!")
            return True
        
        print(f"📦 Applying {len(pending_migrations)} pending migration(s)...")
        
        for migration_file in pending_migrations:
            if not apply_migration(migration_file):
                return False
        
        print("✅ All migrations applied successfully!")
        return True

def migrate_down(target_migration=None):
    """Rollback migrations"""
    if not ensure_migrations_table():
        return False
    
    migration_files = get_migration_files()
    applied_migrations = get_applied_migrations()
    
    if target_migration:
        # Rollback specific migration
        if target_migration not in migration_files:
            print(f"❌ Migration {target_migration} not found!")
            return False
        
        if target_migration not in applied_migrations:
            print(f"⚠️ Migration {target_migration} not applied!")
            return True
        
        return rollback_migration(target_migration)
    else:
        # Rollback latest migration
        if not applied_migrations:
            print("⚠️ No migrations to rollback!")
            return True
        
        latest_migration = sorted(applied_migrations)[-1]
        return rollback_migration(latest_migration)

def show_status():
    """Show migration status"""
    if not ensure_migrations_table():
        return False
    
    migration_files = get_migration_files()
    applied_migrations = get_applied_migrations()
    
    print("\n📊 Migration Status:")
    print("=" * 50)
    
    if not migration_files:
        print("No migration files found.")
        return True
    
    for migration_file in migration_files:
        status = "✅ Applied" if migration_file in applied_migrations else "❌ Pending"
        print(f"{migration_file:<30} {status}")
    
    pending_count = len([mf for mf in migration_files if mf not in applied_migrations])
    print(f"\nTotal migrations: {len(migration_files)}")
    print(f"Applied: {len(applied_migrations)}")
    print(f"Pending: {pending_count}")
    print("=" * 50)
    
    return True

def create_migration(name):
    """Create new migration file"""
    if not os.path.exists(MIGRATIONS_DIR):
        os.makedirs(MIGRATIONS_DIR)
    
    # Generate migration number
    existing_migrations = get_migration_files()
    if existing_migrations:
        last_number = max([int(mf.split('_')[0]) for mf in existing_migrations if mf.split('_')[0].isdigit()])
        migration_number = f"{last_number + 1:03d}"
    else:
        migration_number = "001"
    
    # Clean name
    clean_name = re.sub(r'[^\w\s-]', '', name).strip()
    clean_name = re.sub(r'[\s_-]+', '_', clean_name).lower()
    
    migration_filename = f"{migration_number}_{clean_name}.py"
    migration_path = os.path.join(MIGRATIONS_DIR, migration_filename)
    
    migration_template = f'''"""
{name}
Migration: {migration_filename}
Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

import mysql.connector
from mysql.connector import Error
from datetime import datetime

def get_database_connection():
    """Get database connection"""
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='Arceus123Mewtow',
            database='foodlinker_db'
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {{e}}")
        return None

def up():
    """Apply migration"""
    connection = get_database_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # TODO: Add your migration code here
        # Example:
        # cursor.execute("""
        #     ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL
        # """)
        
        connection.commit()
        print("✅ Migration {migration_filename} applied successfully!")
        return True
        
    except Error as e:
        print(f"❌ Error applying migration: {{e}}")
        connection.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

def down():
    """Rollback migration"""
    connection = get_database_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # TODO: Add your rollback code here
        # Example:
        # cursor.execute("ALTER TABLE users DROP COLUMN phone")
        
        connection.commit()
        print("✅ Migration {migration_filename} rolled back successfully!")
        return True
        
    except Error as e:
        print(f"❌ Error rolling back migration: {{e}}")
        connection.rollback()
        return False
        
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python {migration_filename} [up|down]")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "up":
        success = up()
        sys.exit(0 if success else 1)
    elif command == "down":
        success = down()
        sys.exit(0 if success else 1)
    else:
        print("Invalid command. Use 'up' or 'down'")
        sys.exit(1)
'''
    
    try:
        with open(migration_path, 'w') as f:
            f.write(migration_template)
        print(f"✅ Created migration: {migration_path}")
        return True
    except Exception as e:
        print(f"❌ Error creating migration: {e}")
        return False

def fresh_migrate():
    """Drop all tables and re-run migrations"""
    print("⚠️  Fresh migration will drop all tables and data!")
    confirm = input("Are you sure? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return False
    
    connection = get_database_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Drop all tables
        print("🗑️  Dropping all tables...")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'foodlinker_db'
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"   Dropped table: {table}")
        
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        connection.commit()
        
        print("✅ All tables dropped successfully!")
        
    except Error as e:
        print(f"❌ Error during fresh migration: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
    
    # Now run all migrations
    return migrate_up()

def reset_migrations():
    """Rollback all migrations"""
    applied_migrations = get_applied_migrations()
    
    if not applied_migrations:
        print("⚠️ No migrations to rollback!")
        return True
    
    print(f"⚠️  This will rollback {len(applied_migrations)} migration(s)!")
    confirm = input("Are you sure? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return False
    
    # Rollback in reverse order
    for migration_file in reversed(sorted(applied_migrations)):
        if not rollback_migration(migration_file):
            return False
    
    print("✅ All migrations rolled back successfully!")
    return True

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1].lower()
    
    if command == "up":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        migrate_up(target)
        
    elif command == "down":
        target = sys.argv[2] if len(sys.argv) > 2 else None
        migrate_down(target)
        
    elif command == "status":
        show_status()
        
    elif command == "create":
        if len(sys.argv) < 3:
            print("❌ Please provide a migration name")
            return
        name = " ".join(sys.argv[2:])
        create_migration(name)
        
    elif command == "fresh":
        fresh_migrate()
        
    elif command == "reset":
        reset_migrations()
        
    else:
        print("❌ Invalid command!")
        print(__doc__)

if __name__ == "__main__":
    main()