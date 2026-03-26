# memory/rag.py
# Retrieval-Augmented Generation (RAG) system for meeting memory
# Uses ChromaDB for vector storage + sentence-transformers for embeddings

import os
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Lazy imports to avoid errors if packages not installed
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class MeetingMemory:
    """
    Simple RAG system for storing and retrieving meeting transcripts.

    Features:
    - Chunks transcripts into manageable pieces
    - Generates embeddings using sentence-transformers
    - Stores in local ChromaDB (persistent)
    - Enables semantic search across all meetings
    - Associates each chunk with its meeting metadata

    Usage:
        memory = MeetingMemory()
        memory.add_meeting(meeting_id, transcript, analysis)
        results = memory.search("discuss budget", k=5)
    """

    def __init__(
        self,
        db_path: str = "memory/chroma_db",
        embedding_model: str = "all-MiniLM-L6-v2",
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        """
        Initialize meeting memory.

        Args:
            db_path: Path to ChromaDB persistent storage
            embedding_model: sentence-transformers model name
            chunk_size: Max characters per chunk
            chunk_overlap: Character overlap between chunks
        """
        if not CHROMA_AVAILABLE:
            raise ImportError("chromadb is required. Install with: pip install chromadb")
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers is required. Install with: pip install sentence-transformers")

        self.db_path = db_path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Initialize embeddings model
        print(f"🧠 Loading embedding model: {embedding_model}...")
        self.embedding_model = SentenceTransformer(embedding_model)
        print("✅ Embedding model loaded")

        # Initialize ChromaDB client
        os.makedirs(db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=db_path)

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="meetings",
            metadata={"hnsw:space": "cosine"}  # Cosine similarity
        )

        print(f"✅ ChromaDB initialized at {db_path}")
        print(f"📊 Collection size: {self.collection.count()} chunks\n")

    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks for better retrieval.

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to split at sentence boundary
            if end < len(text):
                # Look for period, exclamation, or question mark followed by space
                for i in range(end, max(start, end - 50), -1):
                    if text[i-1] in ['.', '!', '?'] and i < len(text) and text[i] == ' ':
                        end = i
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            start = end - self.chunk_overlap
            if start >= len(text):
                break

        return chunks

    def _generate_chunk_id(self, meeting_id: str, chunk_index: int, chunk_hash: str) -> str:
        """Generate unique ID for a chunk"""
        return f"{meeting_id}_chunk_{chunk_index}_{chunk_hash[:8]}"

    def add_meeting(
        self,
        meeting_id: str,
        transcript: str,
        analysis: Dict[str, Any],
        overwrite: bool = False
    ) -> int:
        """
        Add a meeting to the memory system.

        Args:
            meeting_id: Unique meeting identifier
            transcript: Full transcript text
            analysis: Analysis dictionary from analyzer_agent
            overwrite: If True, delete existing meeting chunks first

        Returns:
            Number of chunks added
        """
        if self.collection.count() > 0 and overwrite:
            # Delete existing chunks for this meeting
            existing = self.collection.get(where={"meeting_id": meeting_id})
            if existing["ids"]:
                self.collection.delete(where={"meeting_id": meeting_id})
                print(f"🗑️  Deleted {len(existing['ids'])} existing chunks for {meeting_id}")

        # Chunk the transcript
        chunks = self._chunk_text(transcript)
        print(f"📊 Chunked transcript into {len(chunks)} pieces")

        if not chunks:
            print("⚠️  No chunks generated from transcript")
            return 0

        # Prepare data for batch add
        ids = []
        embeddings = []
        metadatas = []
        documents = []

        for i, chunk in enumerate(chunks):
            chunk_id = self._generate_chunk_id(meeting_id, i, hashlib.md5(chunk.encode()).hexdigest())

            # Generate embedding
            embedding = self.embedding_model.encode(chunk).tolist()

            # Metadata to store with chunk
            metadata = {
                "meeting_id": meeting_id,
                "chunk_index": i,
                "chunk_count": len(chunks),
                "timestamp": datetime.now().isoformat(),
                "summary": analysis.get("summary", "")[:200],
                "attendees": json.dumps(analysis.get("attendees", [])),
                "action_items_count": len(analysis.get("action_items", [])),
                "decisions_count": len(analysis.get("decisions", []))
            }

            ids.append(chunk_id)
            embeddings.append(embedding)
            metadatas.append(metadata)
            documents.append(chunk)

        # Add to ChromaDB
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )

        print(f"✅ Stored {len(chunks)} chunks for meeting {meeting_id}")
        print(f"📊 Total chunks in database: {self.collection.count()}\n")

        return len(chunks)

    def search(
        self,
        query: str,
        k: int = 5,
        meeting_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search meetings by semantic similarity.

        Args:
            query: Search query (natural language)
            k: Number of results to return
            meeting_id: Optional filter to specific meeting

        Returns:
            List of result dictionaries with metadata and relevance score
        """
        if self.collection.count() == 0:
            return []

        # Generate query embedding
        query_embedding = self.embedding_model.encode(query).tolist()

        # Build where filter if meeting_id specified
        where = {"meeting_id": meeting_id} if meeting_id else None

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        # Format results
        formatted = []
        for i in range(len(results["ids"][0])):
            formatted.append({
                "chunk_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
                "similarity": 1 - results["distances"][0][i]  # Convert distance to similarity
            })

        return formatted

    def list_meetings(self) -> List[Dict[str, Any]]:
        """
        List all meetings in the memory system.

        Returns:
            List of meeting metadata (unique meeting_ids with summary info)
        """
        if self.collection.count() == 0:
            return []

        # Get all items
        all_items = self.collection.get(include=["metadatas"])

        meetings = {}
        for metadata in all_items["metadatas"]:
            meeting_id = metadata.get("meeting_id")
            if meeting_id and meeting_id not in meetings:
                meetings[meeting_id] = {
                    "meeting_id": meeting_id,
                    "timestamp": metadata.get("timestamp"),
                    "summary": metadata.get("summary", ""),
                    "chunk_count": metadata.get("chunk_count", 0),
                    "attendees": json.loads(metadata.get("attendees", "[]")),
                    "action_items_count": metadata.get("action_items_count", 0),
                    "decisions_count": metadata.get("decisions_count", 0)
                }

        return list(meetings.values())

    def get_meeting_chunks(self, meeting_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all chunks for a specific meeting.

        Args:
            meeting_id: Meeting identifier

        Returns:
            List of chunks with their content and metadata
        """
        results = self.collection.get(
            where={"meeting_id": meeting_id},
            include=["documents", "metadatas"]
        )

        chunks = []
        for i, doc in enumerate(results["documents"]):
            chunks.append({
                "chunk_index": results["metadatas"][i].get("chunk_index", i),
                "text": doc,
                "metadata": results["metadatas"][i]
            })

        # Sort by chunk index
        chunks.sort(key=lambda x: x["chunk_index"])

        return chunks

    def delete_meeting(self, meeting_id: str) -> bool:
        """
        Delete all chunks for a meeting.

        Args:
            meeting_id: Meeting to delete

        Returns:
            True if successful, False if meeting not found
        """
        existing = self.collection.get(where={"meeting_id": meeting_id})
        if existing["ids"]:
            self.collection.delete(where={"meeting_id": meeting_id})
            print(f"🗑️  Deleted {len(existing['ids'])} chunks for meeting {meeting_id}")
            return True
        else:
            print(f"⚠️  No chunks found for meeting {meeting_id}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the memory system.

        Returns:
            Dictionary with counts and info
        """
        total_chunks = self.collection.count()

        if total_chunks == 0:
            return {"total_chunks": 0, "total_meetings": 0, "avg_chunks_per_meeting": 0}

        all_meetings = self.list_meetings()

        return {
            "total_chunks": total_chunks,
            "total_meetings": len(all_meetings),
            "avg_chunks_per_meeting": total_chunks / len(all_meetings) if all_meetings else 0,
            "db_path": self.db_path,
            "embedding_model": self.embedding_model._model_card if hasattr(self.embedding_model, '_model_card') else "unknown"
        }


if __name__ == "__main__":
    print("🧪 Testing Meeting Memory RAG system...\n")

    if not CHROMA_AVAILABLE or not SENTENCE_TRANSFORMERS_AVAILABLE:
        print("❌ Install dependencies first:")
        print("   pip install chromadb sentence-transformers")
    else:
        try:
            memory = MeetingMemory()

            print("\n📊 Memory Stats:")
            stats = memory.get_stats()
            for key, value in stats.items():
                print(f"  {key}: {value}")

            # Test adding a meeting
            print("\n📝 Testing: Adding sample meeting...")
            sample_id = "test_meeting_001"
            sample_transcript = """
            Speaker A: Good morning team! Let's discuss our Q2 goals.
            Speaker B: I think we should focus on improving user onboarding.
            Speaker C: Agreed. We need to reduce the time it takes for new users to get value.
            Speaker A: What specific metrics should we target?
            Speaker B: We should aim to reduce onboarding completion time by 50%.
            Speaker C: And we should increase day-1 retention by 30%.
            Speaker A: These are good goals. John, can you lead the onboarding redesign?
            Speaker D: Yes, I'll start with user research this week.
            Speaker A: Sarah, can you help with metrics tracking?
            Speaker E: Sure, I'll set up the analytics dashboards.
            Speaker A: Great. Let's meet again next week to review progress.
            """
            sample_analysis = {
                "summary": "Team discussed Q2 goals focusing on improving user onboarding with targets: 50% reduction in completion time, 30% increase in day-1 retention.",
                "action_items": [
                    {
                        "owner": "John",
                        "task": "Lead onboarding redesign project",
                        "deadline": "2024-05-01",
                        "priority": "High"
                    },
                    {
                        "owner": "Sarah",
                        "task": "Set up analytics dashboards for onboarding metrics",
                        "deadline": "2024-04-15",
                        "priority": "High"
                    }
                ],
                "decisions": [
                    "Focus Q2 on user onboarding improvement",
                    "Target 50% reduction in completion time",
                    "Target 30% increase in day-1 retention"
                ],
                "attendees": ["Speaker A", "Speaker B", "Speaker C", "Speaker D", "Speaker E"],
                "follow_up_needed": True
            }

            added = memory.add_meeting(sample_id, sample_transcript, sample_analysis, overwrite=True)
            print(f"✅ Added {added} chunks")

            # Test search
            print("\n🔍 Testing: Searching for 'onboarding metrics'...")
            results = memory.search("onboarding metrics", k=3)
            print(f"Found {len(results)} results")
            for r in results:
                print(f"  - Score: {r['similarity']:.3f} | Meeting: {r['metadata']['meeting_id']}")
                print(f"    Text: {r['text'][:100]}...")

            print("\n✅ Memory RAG system working correctly!")

        except Exception as e:
            print(f"❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
