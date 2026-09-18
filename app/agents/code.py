from app.agents.base import BaseAgent


class CodeGeneratorAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized software development assistant. Help users write, explain, debug, document, and improve code and algorithms. Prefer clear, maintainable solutions. Ask for missing requirements when necessary."
    processing_message = "Generating your code..."
