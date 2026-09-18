from app.agents.base import BaseAgent


class ImageGeneratorAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized image-generation assistant. Help users create image prompts, visual concepts, style directions, and image-editing instructions. Ask for missing visual requirements when necessary."
    processing_message = "Generating your image..."
