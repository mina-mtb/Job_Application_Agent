import os
import shutil
import hashlib
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

class KnowledgeManager:
    def __init__(self, db_path="knowledge_base/chroma_db", raw_dir="knowledge_base/raw_sources", processed_dir="knowledge_base/processed_sources"):
        self.db_path = Path(db_path)
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        
        # Ensure directories exist
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        
        # Using default local embedding function (all-MiniLM-L6-v2)
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="job_agent_knowledge",
            embedding_function=self.embedding_function
        )

    def clean_text(self, text: str) -> str:
        """Clean and normalize the text."""
        # Basic cleaning: remove excessive newlines and spaces
        cleaned = "\n".join([line.strip() for line in text.split("\n")])
        import re
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def chunk_text(self, text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[str]:
        """Split text into overlapping chunks."""
        chunks = []
        if not text:
            return chunks
            
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start += chunk_size - chunk_overlap
            
        return chunks

    def embed_chunks(self, chunks: list[str]) -> list[list[float]]:
        """Embed a list of text chunks. 
        In Chroma, we can just pass texts directly to add/query, but this method is provided 
        per requirements to explicitly expose the embedding functionality."""
        return self.embedding_function(chunks)

    def add_source(self, file_path: str) -> bool:
        """Process a file, chunk it, and add to the knowledge base."""
        path = Path(file_path)
        if not path.exists():
            print(f"File {file_path} does not exist.")
            return False
            
        if path.suffix.lower() not in ['.txt', '.md', '.pdf']:
            print(f"Unsupported file type: {path.suffix}. Only .txt, .md, and .pdf are supported.")
            return False

        if path.suffix.lower() == '.pdf':
            try:
                import pypdf
                with open(path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            except Exception as e:
                print(f"Failed to read PDF: {e}")
                return False
        else:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()

        # Check for duplicates using file hash
        file_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        
        # We can store the hash in the metadata to check existence
        existing = self.collection.get(where={"file_hash": file_hash})
        if existing and existing['ids']:
            print(f"File {file_path} is already in the knowledge base (duplicate hash).")
            return False
            
        cleaned = self.clean_text(text)
        chunks = self.chunk_text(cleaned)
        
        if not chunks:
            return False

        ids = [f"{path.name}_{file_hash}_{i}" for i in range(len(chunks))]
        metadatas = [{"source": path.name, "file_hash": file_hash, "chunk_index": i} for i in range(len(chunks))]

        self.collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        
        # Copy to processed_sources
        dest_path = self.processed_dir / path.name
        # To avoid overwriting with the exact same name if a different file has the same name but different content:
        if dest_path.exists():
            dest_path = self.processed_dir / f"{path.stem}_{file_hash[:8]}{path.suffix}"
            
        shutil.copy2(path, dest_path)
        
        print(f"Successfully added {path.name} to knowledge base in {len(chunks)} chunks.")
        return True

    def query_knowledge_base(self, query: str, top_k: int = 5) -> list[dict]:
        """Query the knowledge base for relevant chunks."""
        if self.collection.count() == 0:
            return []
            
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count())
        )
        
        # Format the results
        formatted_results = []
        if results and results['documents'] and results['documents'][0]:
            for i in range(len(results['documents'][0])):
                formatted_results.append({
                    "id": results['ids'][0][i],
                    "text": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if 'distances' in results and results['distances'] else None
                })
                
        return formatted_results

    def delete_source(self, filename: str) -> bool:
        """Delete a source file from disk and its embeddings from the knowledge base."""
        path = self.processed_dir / filename
        if not path.exists():
            return False
            
        # Read file to compute hash so we can delete its embeddings
        try:
            if path.suffix.lower() == '.pdf':
                import pypdf
                with open(path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    
            file_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            self.collection.delete(where={"file_hash": file_hash})
        except Exception as e:
            print(f"Error removing embeddings for {filename}: {e}")
            
        # Delete the physical file
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            print(f"Error deleting file {filename}: {e}")
            return False
            
        return True
