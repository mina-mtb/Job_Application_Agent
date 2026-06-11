import os
import sys
from pathlib import Path

# Add project root to sys.path so we can import core modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.knowledge_manager import KnowledgeManager

def validate_knowledge_base():
    km = KnowledgeManager()
    
    raw_dir = km.raw_dir
    processed_dir = km.processed_dir
    
    raw_files = [f for f in os.listdir(raw_dir) if os.path.isfile(os.path.join(raw_dir, f))] if raw_dir.exists() else []
    processed_files = [f for f in os.listdir(processed_dir) if os.path.isfile(os.path.join(processed_dir, f))] if processed_dir.exists() else []
    
    print("="*50)
    print("KNOWLEDGE BASE VALIDATION REPORT")
    print("="*50)
    
    print(f"\n1. Raw files count: {len(raw_files)}")
    if raw_files:
        for f in raw_files:
            size = os.path.getsize(os.path.join(raw_dir, f))
            print(f"   - {f} ({size} bytes)")
            if size == 0:
                print(f"     [WARNING] File is empty!")
                
    print(f"\n2. Processed files count: {len(processed_files)}")
    if processed_files:
        for f in processed_files:
            print(f"   - {f}")
            
    # Check duplicates/missing (comparing raw and processed)
    # Note: processed files might have hash suffix, so just base name check is naive.
    # We will just note if there is a discrepancy.
    if len(raw_files) != len(processed_files):
        print("\n[NOTE] Number of raw files and processed files differ. "
              "Some files may have been duplicates (hashes matched) or failed to process.")

    num_chunks = km.collection.count()
    print(f"\n3. Number of chunks in ChromaDB: {num_chunks}")
    
    print(f"\n4. Is ChromaDB indexed? {'Yes' if num_chunks > 0 else 'No'}")
    
    print("\n5. Sample Queries:")
    sample_queries = [
        ".NET backend developer experience",
        "AI machine learning education Chalmers",
        "cloud developer Azure Kubernetes",
        "Power Platform AstraZeneca",
        "sales and marketing experience Iran"
    ]
    
    if num_chunks == 0:
        print("   [!] Cannot run queries because the database is empty.")
    else:
        for q in sample_queries:
            print(f"\n   Query: '{q}'")
            results = km.query_knowledge_base(q, top_k=2)
            if not results:
                print("      No results found.")
            else:
                for i, r in enumerate(results):
                    source = r.get('metadata', {}).get('source', 'Unknown')
                    text_snippet = r['text'][:100].replace('\n', ' ') + "..."
                    print(f"      {i+1}. [Source: {source}] {text_snippet}")

    print("\n" + "="*50)

if __name__ == "__main__":
    validate_knowledge_base()
