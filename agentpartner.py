import logging
import os

import click
from dotenv import load_dotenv

from agent import CurrencyAgent
from specialized_agents import EmailWriterAgent, CodeGeneratorAgent, ImageGeneratorAgent, GameGeneratorAgent, DeepLearningAgent,RainformentAgent, DsaAgent
from custom_types import AgentCapabilities, AgentCard, AgentSkill, MissingAPIKeyError
from push_notification_auth import PushNotificationSenderAuth
from server import A2AServer
from task_manager import AgentTaskManager

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=8000)
def main(host, port):
    """Starts the Multi-Agent server."""
    try:
        if not os.getenv("GROQ_API_KEY"):
            raise MissingAPIKeyError("GROQ_API_KEY environment variable not set.")

        capabilities = AgentCapabilities(streaming=True, pushNotifications=False)
        
        # Define skills for each agent type
        currency_skill = AgentSkill(
            id="convert_currency",
            name="Currency Exchange Rates Tool",
            description="Helps with exchange values between various currencies",
            tags=["currency conversion", "currency exchange"],
            examples=["What is exchange rate between USD and GBP?"],
        )
        
        email_skill = AgentSkill(
            id="email_writer",
            name="Email Writing Assistant",
            description="Helps write and format professional emails",
            tags=["email", "writing", "business communication"],
            examples=["Write a professional email to schedule a meeting"],
        )
        
        code_skill = AgentSkill(
            id="code_generator",
            name="Code Generation Tool",
            description="Helps generate and document code in various languages",
            tags=["coding", "programming", "development"," software engineering"],
            examples=["Generate a Python class for user management"],
        )
        
        image_skill = AgentSkill(
            id="image_generator",
            name="Image Generation Tool",
            description="Creates and modifies images using AI",
            tags=["image", "art", "design"],
            examples=["Generate an image of a sunset over mountains"],
        )
        
        game_skill = AgentSkill(
            id="game_generator",
            name="Game Development Assistant",
            description="Helps design and develop games ",
            tags=["games", "development", "design", "game mechanics", "game design", "game development"],
            examples=["Design a puzzle game concept", "Develop a 2D platformer game", "Create a 3D RPG game"],
        )
        deep_learning_skill = AgentSkill(
            id="deep_learning_agent",
            name="Deep Learning Agent",
            description="A specialized agent for deep learning tasks and performance optimization and model training and evaluation",
            tags=["deep learning", "machine learning", "AI", "neural networks"],
            examples=[
                "Train a neural network for image classification",
                "Fine-tune a pre-trained model for text generation",
                "Implement a convolutional neural network for object detection",
                "Analyze a dataset using deep learning techniques",
                "Generate synthetic data using generative adversarial networks (GANs)",
                "Perform transfer learning on a pre-trained model",
                "Optimize a deep learning model for performance",
                "Evaluate the accuracy of a trained model"
            ],
        )
        rainforment_skill= AgentSkill(
            id="rainforment_agent",
            name="Rainforment Agent",
            description="A specialized agent for rainforment tasks and performance optimization and model training and evaluation",
            tags=["rainforment", "machine learning", "AI", "neural networks"],
            examples=[
                "Train a neural network for image classification",
                "Fine-tune a pre-trained model for text",
                "Implement a convolutional neural network for object detection",
                "Analyze a dataset using rainforment techniques",
                "Generate synthetic data using generative adversarial networks (GANs)",
                "Perform transfer learning on a pre-trained model",
                "Optimize a rainforment model for performance",
                "Evaluate the accuracy of a trained model"
            ],
        )
        dsa_skill = AgentSkill(
            id  = "data_structures_and_algorithms_agent",
            name = "dsa_agent",
            description=(
            "A specialized agent for solving and explaining Data Structures and Algorithms problems, "
            "supporting tasks like searching, sorting, graph traversal, dynamic programming, "
            "greedy strategies, backtracking, divide & conquer, and complexity analysis. "
            "Also useful for optimizing performance and evaluating models."
            ),
            tags=["data structures", "algorithms", "search", "sorting", "graph traversal", "dynamic programming", "greedy strategies", "backtracking", "divide & conquer", "complexity analysis"],
            examples=[
                "Implement a binary search algorithm",
                "Sort a list using quicksort",
                "Find the shortest path in a graph using Dijkstra's algorithm",
                "Solve a dynamic programming problem like the knapsack problem",
                "Use greedy strategies to solve the activity selection problem",
                "Backtrack to find all solutions to the N-Queens problem",
                "Divide and conquer to merge two sorted arrays",
                "Analyze the time complexity of a sorting algorithm"
            ],
        )

        # Create specialized agents
    


        # Create specialized agents
        agent_card = AgentCard(
            name="Multi-Purpose Agent",
            description="A versatile agent providing multiple specialized services",
            url=f"http://{host}:{port}/",
            version="1.0.0",
            defaultInputModes=["text", "text/plain","code", "text/html"],
            defaultOutputModes=["text", "text/plain", "image/png", "image/jpeg","code", "text/html", "text/x-python", "text/x-javascript", "text/x-java", "text/x-c++", "text/x-csharp", "text/x-go", "text/x-ruby", "text/x-php", "text/x-typescript"],
            
            capabilities=capabilities,
            skills=[currency_skill, email_skill, code_skill, image_skill, game_skill, deep_learning_skill, rainforment_skill, dsa_skill],
        )
        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        
        # Use the MultiAgent that manages all specialized agents
        from multi_agent import MultiAgent
        multi_agent = MultiAgent()
        
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(
                agent=multi_agent, notification_sender_auth=notification_sender_auth
            ),
            host=host,
            port=port,
        )

        server.app.add_route(
            "/.well-known/jwks.json",
            notification_sender_auth.handle_jwks_endpoint,
            methods=["GET"],
        )

        logger.info(f"Starting server on {host}:{port}")
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()