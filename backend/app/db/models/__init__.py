"""ORM model registry."""

from app.db.models.answer import Answer
from app.db.models.conversation import Conversation, ConversationMessage
from app.db.models.credit import CreditTransaction
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.prompt_version import PromptVersion
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User


def load_all_models() -> tuple[type[object], ...]:
    """Import and return all ORM model classes for metadata registration."""

    return (
        User,
        Product,
        Persona,
        Evaluation,
        Survey,
        Answer,
        Conversation,
        ConversationMessage,
        Report,
        CreditTransaction,
        PromptVersion,
    )
