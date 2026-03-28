"""RAG knowledge base — vector-indexed marketing skill library."""

import hashlib
from pathlib import Path

import structlog

logger = structlog.get_logger()

_knowledge_cache: list[dict] = []


def _load_skills_library() -> list[dict]:
    """Load marketing skills from the skills library directory."""
    global _knowledge_cache
    if _knowledge_cache:
        return _knowledge_cache

    skills_dir = Path(__file__).resolve().parents[4] / ".cursor" / "skills" / "marketing-skills-library"
    if not skills_dir.exists():
        skills_dir = Path(__file__).resolve().parents[4] / ".cursor" / "skills"

    entries = []
    for md_file in skills_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) < 50:
                continue
            rel_path = md_file.relative_to(skills_dir)
            rel = rel_path.as_posix()
            category = rel_path.parts[0] if rel_path.parts else "general"
            entries.append({
                "id": hashlib.md5(rel.encode()).hexdigest(),
                "path": rel,
                "category": category,
                "content": content[:4000],
                "title": md_file.stem.replace("-", " ").replace("_", " ").title(),
            })
        except Exception:
            continue

    _knowledge_cache = entries
    logger.info("knowledge_base_loaded", count=len(entries))
    return entries


async def retrieve_knowledge(query: str, k: int = 3) -> list[dict]:
    """Retrieve relevant knowledge entries by keyword matching.

    In production, this uses pgvector similarity search.
    Currently uses simple keyword overlap scoring.
    """
    entries = _load_skills_library()
    if not entries:
        return []

    query_words = set(query.lower().split())

    scored = []
    for entry in entries:
        content_words = set(entry["content"][:500].lower().split())
        title_words = set(entry["title"].lower().split())
        overlap = len(query_words & (content_words | title_words))
        if overlap > 0:
            scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "title": e["title"],
            "category": e["category"],
            "content": e["content"][:1000],
            "relevance_score": score,
        }
        for score, e in scored[:k]
    ]
