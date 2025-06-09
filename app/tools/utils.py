# app/tools/utils.py
import hashlib


def generate_unique_hash(company_name: str, title: str) -> str:
    """Creates a stable, unique hash for a job role to prevent duplicates."""
    s = f"{company_name.lower().strip()}-{title.lower().strip()}"
    return hashlib.sha256(s.encode()).hexdigest() 