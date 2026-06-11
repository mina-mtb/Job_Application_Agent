import os
import shutil
import sqlite3
from datetime import datetime
import argparse

def backup_state(project_root):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(project_root, "backups", f"clean_reset_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)
    
    print(f"Creating backup at: {backup_dir}")
    
    # Backup database
    db_path = os.path.join(project_root, "database")
    if os.path.exists(db_path):
        shutil.copytree(db_path, os.path.join(backup_dir, "database"), dirs_exist_ok=True)
        print("[OK] Backed up database/")
        
    # Backup outputs
    outputs_path = os.path.join(project_root, "outputs")
    if os.path.exists(outputs_path):
        shutil.copytree(outputs_path, os.path.join(backup_dir, "outputs"), dirs_exist_ok=True)
        print("[OK] Backed up outputs/")
        
    # Backup knowledge_base
    kb_path = os.path.join(project_root, "knowledge_base")
    if os.path.exists(kb_path):
        shutil.copytree(kb_path, os.path.join(backup_dir, "knowledge_base"), dirs_exist_ok=True)
        print("[OK] Backed up knowledge_base/")
        
    return backup_dir

def clear_directory(dir_path):
    if not os.path.exists(dir_path):
        return
    for filename in os.listdir(dir_path):
        file_path = os.path.join(dir_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}. Reason: {e}")

def reset_state(project_root):
    print("\nStarting cleanup...")
    
    # 1. Clear outputs
    outputs_path = os.path.join(project_root, "outputs")
    clear_directory(outputs_path)
    print("[OK] Cleared all generated CV outputs (PDFs, DOCXs, test files)")

    # 2. Clear Knowledge Base files
    kb_raw = os.path.join(project_root, "knowledge_base", "raw_sources")
    kb_processed = os.path.join(project_root, "knowledge_base", "processed_sources")
    clear_directory(kb_raw)
    clear_directory(kb_processed)
    print("[OK] Cleared old Knowledge Base raw and processed files")
    
    # 3. Clear ChromaDB
    chroma_db = os.path.join(project_root, "knowledge_base", "chroma_db")
    if os.path.exists(chroma_db):
        shutil.rmtree(chroma_db, ignore_errors=True)
        print("[OK] Cleared ChromaDB/vector database")
        
    # 4. Clear old temporary files or agent.db
    agent_db = os.path.join(project_root, "knowledge_base", "agent.db")
    if os.path.exists(agent_db):
        try:
            os.remove(agent_db)
            print("[OK] Cleared old agent.db")
        except Exception:
            pass

    # 5. Clear SQLite job records while preserving schema
    jobs_db = os.path.join(project_root, "database", "jobs.db")
    if os.path.exists(jobs_db):
        conn = sqlite3.connect(jobs_db)
        cursor = conn.cursor()
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        for table in tables:
            table_name = table[0]
            # Don't delete schema migrations table if you use one, but for basic tables:
            cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()
        conn.close()
        print("[OK] Cleared old job records and CV generation records from SQLite (schema preserved)")

def main():
    parser = argparse.ArgumentParser(description="Reset local test state safely.")
    parser.add_argument('--confirm', action='store_true', help="Confirm you want to reset the state.")
    args = parser.parse_args()

    if not args.confirm:
        print("ERROR: You must pass the --confirm flag to run this script.")
        print("Example: python scripts/reset_local_test_state.py --confirm")
        return

    # Find project root (one level up from scripts directory)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)

    backup_dir = backup_state(project_root)
    reset_state(project_root)
    
    print(f"\nReset complete! Your backup is saved at: {backup_dir}")
    print("NOTE: You will need to re-upload your Knowledge Base files and PDF Template.")

if __name__ == "__main__":
    main()
