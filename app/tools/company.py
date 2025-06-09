from sqlmodel import Session, select

from app.models import Company


def get_or_create_company(session: Session, name: str) -> Company:
    """Gets or creates a company by name."""
    company = session.exec(select(Company).where(Company.name == name)).first()
    if not company:
        company = Company(name=name)
        session.add(company)
        session.commit()
        session.refresh(company)
    return company 