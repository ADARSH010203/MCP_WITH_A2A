from app.agents.base import BaseAgent


class ReinforcementLearningAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized reinforcement-learning assistant. Help with environments, policies, value functions, Q-learning, policy gradients, training, evaluation, and optimization."
    processing_message = "Processing your reinforcement learning task..."
