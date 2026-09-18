from app.agents.base import BaseAgent


class GameGeneratorAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized game-development assistant. Help with game concepts, mechanics, levels, characters, narratives, testing, engines, platforms, and implementation ideas. Keep recommendations practical."
    processing_message = "Designing your game concept..."
