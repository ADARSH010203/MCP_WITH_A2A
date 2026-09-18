from app.agents.base import BaseAgent


class DeepLearningAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized deep-learning assistant. Help with neural networks, model training, fine-tuning, datasets, evaluation, optimization, CNNs, transformers, GANs, and transfer learning."
    processing_message = "Processing your deep learning task..."
