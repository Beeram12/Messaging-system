from app.models.template import Template
from sqlalchemy.orm import Session


class TemplateRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, template_id: str) -> Template | None:
        return self.db.get(Template, template_id)

    def create(self, template: Template) -> Template:
        self.db.add(template)
        self.db.flush()
        return template
