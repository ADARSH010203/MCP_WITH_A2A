"""CLI entry point for the A2A multi-agent server."""

import logging
import os

import click
from dotenv import load_dotenv

from app.a2a.models import (
    AgentAuthentication,
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    MissingAPIKeyError,
)
from app.a2a.push_notification_auth import PushNotificationSenderAuth
from app.a2a.server import A2AServer
from app.a2a.task_manager import AgentTaskManager
from app.config.settings import settings
from app.routing.router import MultiAgent

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_agent_card(host: str, port: int) -> AgentCard:
    skills = [
        AgentSkill(
            id="convert_currency",
            name="Currency Exchange Rates",
            description="Handles currency conversion and exchange-rate requests.",
            tags=["currency", "exchange rate"],
            examples=["What is the exchange rate between USD and GBP?"],
        ),
        AgentSkill(
            id="email_writer",
            name="Email Writing",
            description="Writes clear and professional emails and messages.",
            tags=["email", "writing", "communication"],
            examples=["Write a professional email to schedule a meeting."],
        ),
        AgentSkill(
            id="code_generator",
            name="Code Generation",
            description="Generates and explains code for common development tasks.",
            tags=["coding", "programming", "software engineering"],
            examples=["Generate a Python class for user management."],
        ),
        AgentSkill(
            id="image_generator",
            name="Image Assistance",
            description="Handles image-generation related requests.",
            tags=["image", "art", "design"],
            examples=["Generate an image of a sunset over mountains."],
        ),
        AgentSkill(
            id="game_generator",
            name="Game Development",
            description="Helps with game concepts, mechanics, and implementation ideas.",
            tags=["games", "game design", "game development"],
            examples=["Design a puzzle game concept."],
        ),
        AgentSkill(
            id="deep_learning_agent",
            name="Deep Learning",
            description="Supports neural networks, training, evaluation, and optimization.",
            tags=["deep learning", "neural networks", "model training"],
            examples=["Design a CNN for image classification."],
        ),
        AgentSkill(
            id="reinforcement_learning_agent",
            name="Reinforcement Learning",
            description="Supports reinforcement-learning concepts, algorithms, and implementations.",
            tags=["reinforcement learning", "q-learning", "policy gradient"],
            examples=["Explain Q-learning with a simple example."],
        ),
        AgentSkill(
            id="data_structures_and_algorithms_agent",
            name="Data Structures and Algorithms",
            description="Solves and explains DSA problems and complexity analysis.",
            tags=["data structures", "algorithms", "dynamic programming"],
            examples=["Find the shortest path using Dijkstra's algorithm."],
        ),
    ]

    return AgentCard(
        name="Multi-Purpose Agent",
        description="A multi-agent service that routes requests to specialized AI agents.",
        url=f"http://{host}:{port}/",
        version="1.0.0",
        defaultInputModes=["text"],
        defaultOutputModes=["text", "text/plain"],
        capabilities=AgentCapabilities(streaming=True, pushNotifications=True),
        authentication=(
            AgentAuthentication(schemes=["bearer"])
            if settings.a2a_api_key
            else None
        ),
        skills=skills,
    )


@click.command()
@click.option("--host", default="localhost", show_default=True)
@click.option("--port", default=8000, type=int, show_default=True)
def main(host: str, port: int) -> None:
    """Start the A2A multi-agent server."""
    if not settings.groq_api_key:
        raise click.ClickException("GROQ_API_KEY environment variable is not set.")

    try:
        agent_card = build_agent_card(host, port)
        notification_auth = PushNotificationSenderAuth()
        notification_auth.generate_jwk()

        multi_agent = MultiAgent()
        task_manager = AgentTaskManager(
            agent=multi_agent,
            notification_sender_auth=notification_auth,
        )
        server = A2AServer(
            host=host,
            port=port,
            agent_card=agent_card,
            task_manager=task_manager,
        )
        server.app.add_route(
            "/.well-known/jwks.json",
            notification_auth.handle_jwks_endpoint,
            methods=["GET"],
        )

        logger.info("Starting A2A server on %s:%s", host, port)
        server.start()
    except MissingAPIKeyError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        logger.exception("A2A server startup failed")
        raise click.ClickException(f"Server startup failed: {exc}") from exc


if __name__ == "__main__":
    main()
