import asyncio
from typing import Any, AsyncIterable, Dict, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

memory = MemorySaver()

class ResponseFormat(BaseModel):
    """Respond to the user in this format."""
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str

class BaseAgent:
    def __init__(self):
        self.model = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", max_tokens=2048)
        self.graph = create_react_agent(
            self.model,
            tools=[],  # Each agent will define its own tools
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

    def invoke(self, query, sessionId) -> str:
        config = {"configurable": {"thread_id": sessionId}}
        self.graph.invoke({"messages": [("user", query)]}, config)
        return self.get_agent_response(config)

    async def stream(self, query, sessionId) -> AsyncIterable[Dict[str, Any]]:
        inputs = {"messages": [("user", query)]}
        config = {"configurable": {"thread_id": sessionId}}

        for item in self.graph.stream(inputs, config, stream_mode="values"):
            message = item["messages"][-1]
            if (
                isinstance(message, AIMessage)
                and message.tool_calls
                and len(message.tool_calls) > 0
            ):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": self.processing_message,
                }
            elif isinstance(message, ToolMessage):
                yield {
                    "is_task_complete": False,
                    "require_user_input": False,
                    "content": self.processing_message,
                }

        yield self.get_agent_response(config)

    def get_agent_response(self, config):
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get("structured_response")
        if structured_response and isinstance(structured_response, ResponseFormat):
            if structured_response.status == "input_required":
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": structured_response.message,
                }
            elif structured_response.status == "error":
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": structured_response.message,
                }
            elif structured_response.status == "completed":
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": structured_response.message,
                }

        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

class EmailWriterAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized assistant for writing professional emails.
    Your purpose is to help users draft, format, and polish email content.
    You can help with:
    - Writing professional business emails
    - Crafting response emails
    - Formatting email content
    - Creating email templates
    - Suggesting subject lines
    - Providing email etiquette tips
    - Reviewing and improving email drafts
    If the user asks for anything unrelated to email writing, politely explain that you can only help with email-related tasks.
    Set response status to input_required if you need more details about the email.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the email draft is ready.
    """
    processing_message = "Drafting your email..."

class CodeGeneratorAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized code generation assistant.
    Your purpose is to help users generate high-quality, well-documented code.
    You can help with:
    - Writing code in various programming languages
    - Creating code documentation
    - Implementing specific algorithms or features
    - Generating boilerplate code
    - Code optimization suggestions
    If the user asks for anything unrelated to code generation, politely explain that you can only help with code-related tasks.
    Set response status to input_required if you need more details about the code requirements.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the code is ready.
    """
    processing_message = "Generating your code..."

class ImageGeneratorAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized image generation assistant.
    Your purpose is to help users create and modify images using AI.
    You can help with:
    - Generating images from text descriptions
    - Image style transfer
    - Image modifications
    - Art style suggestions
    - Visual content creation
    If the user asks for anything unrelated to image generation, politely explain that you can only help with image-related tasks.
    Set response status to input_required if you need more details about the image requirements.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the image is ready.
    """
    processing_message = "Generating your image..."
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain", "image/png", "image/jpeg"]

class GameGeneratorAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized game development assistant.
    Your purpose is to help users create and design games.
    You can help with:
    - Game concept development
    - Game mechanics design
    - Level design suggestions
    - Character development
    - Game balance recommendations
    - Game narrative and story development
    - Game asset suggestions
    - Game engine recommendations
    - Game testing and feedback
    - Game monetization strategies
    - Game marketing strategies
    - Game platform recommendations
    - Game genre suggestions
    If the user asks for anything unrelated to game development, politely explain that you can only help with game-related tasks and provide relevant resources.
    Set response status to input_required if you need more details about the game requirements.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the game design is ready.

    """
    processing_message = "Designing your game concept..."

class DeepLearningAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized deep learning assistant.
    Your purpose is to help users with deep learning tasks, model training, and performance optimization.
    You can help with:
    - Training neural networks
    - Fine-tuning pre-trained models
    - Implementing deep learning algorithms
    - Analyzing datasets using deep learning techniques
    - Generating synthetic data using GANs
    If the user asks for anything unrelated to deep learning, politely explain that you can only help with deep learning-related tasks.
    Set response status to input_required if you need more details about the deep learning task.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the task is ready.
    """
    processing_message = "Processing your deep learning task..."

class RainformentAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized reinforcement learning assistant.
    Your purpose is to help users with reinforcement learning tasks, model training, and performance optimization.
    You can help with:
    - Training reinforcement learning agents
    - Fine-tuning pre-trained models
    - Implementing reinforcement learning algorithms
    - Analyzing datasets using reinforcement learning techniques
    If the user asks for anything unrelated to reinforcement learning, politely explain that you can only help with reinforcement learning-related tasks.
    Set response status to input_required if you need more details about the reinforcement learning task.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the task is ready.
    """
    processing_message = "Processing your reinforcement learning task..."
class DsaAgent(BaseAgent):
    SYSTEM_INSTRUCTION = """
    You are a specialized DSA (Data Structures and Algorithms) assistant.
    Your purpose is to help users with DSA tasks, algorithm design, and performance optimization.
    You can help with:
    - Implementing data structures
    - Designing algorithms
    - Analyzing algorithm complexity
    - Providing DSA-related coding solutions
    - Debugging DSA-related code
    - Optimizing DSA-related code
    - Explaining DSA concepts
    - Providing DSA-related resources
    If the user asks for anything unrelated to DSA, politely explain that you can only help with DSA-related tasks and provide relevant resources and examples to help the user understand the concept and explain it in a simple way.
    Set response status to input_required if you need more details about the DSA task.
    Set response status to error if there's an issue processing the request.
    Set response status to completed when the task is ready.

    """
    processing_message = "Processing your DSA task..."