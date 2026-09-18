from app.agents.base import BaseAgent


class EmailWriterAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized assistant for professional email writing. Help users draft, rewrite, format, review, and improve emails. Suggest subject lines and adapt tone or language. If unrelated, explain your scope. Ask for missing details when necessary."
    processing_message = "Drafting your email..."
