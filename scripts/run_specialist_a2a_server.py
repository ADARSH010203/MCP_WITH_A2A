"""Run one specialist as an independent A2A service."""

import logging

import click
from dotenv import load_dotenv

from app.a2a.models import (
    AgentAuthentication,
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
    MissingAPIKeyError,
)
from app.a2a.push_notification_auth import PushNotificationSenderAuth
from app.a2a.server import A2AServer
from app.a2a.task_manager import AgentTaskManager
from app.agents.code import CodeGeneratorAgent
from app.agents.currency import CurrencyAgent
from app.agents.deep_learning import DeepLearningAgent
from app.agents.dsa import DsaAgent
from app.agents.email import EmailWriterAgent
from app.agents.game import GameGeneratorAgent
from app.agents.image import ImageGeneratorAgent
from app.agents.reinforcement import ReinforcementLearningAgent
from app.config.settings import settings
from app.routing.registry import DEFAULT_AGENT_REGISTRY


AGENT_FACTORIES = {
    "currency": CurrencyAgent,
    "email": EmailWriterAgent,
    "image": ImageGeneratorAgent,
    "game": GameGeneratorAgent,
    "deep_learning": DeepLearningAgent,
    "reinforcement": ReinforcementLearningAgent,
    "dsa": DsaAgent,
    "code": CodeGeneratorAgent,
}


def build_specialist_card(
    agent_type: str,
    host: str,
    port: int,
    public_url: str | None,
) -> AgentCard:
    capability = DEFAULT_AGENT_REGISTRY.get(agent_type)
    base_url = (public_url or f"http://{host}:{port}").rstrip("/")

    skill = AgentSkill(
        id=f"{agent_type}_specialist",
        name=f"{agent_type.replace('_', ' ').title()} Specialist",
        description=capability.task_focus,
        tags=list(capability.capabilities),
        examples=[],
        inputModes=list(capability.input_types),
        outputModes=list(capability.output_types),
    )

    return AgentCard(
        name=f"{agent_type.replace('_', ' ').title()} Specialist",
        description=(
            f"Independent A2A service for the {agent_type.replace('_', ' ')} domain."
        ),
        url=f"{base_url}/",
        provider=AgentProvider(organization="MCP + A2A Multi-Agent System"),
        version="1.0.0",
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=True,
            stateTransitionHistory=False,
        ),
        authentication=(
            AgentAuthentication(schemes=["bearer"])
            if settings.a2a_api_key
            else None
        ),
        defaultInputModes=list(capability.input_types),
        defaultOutputModes=list(capability.output_types),
        skills=[skill],
    )


@click.command()
@click.option(
    "--agent",
    "agent_type",
    type=click.Choice(sorted(AGENT_FACTORIES)),
    required=True,
    help="Specialist domain to expose as a standalone A2A service.",
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8100, type=int, show_default=True)
@click.option(
    "--public-url",
    default=None,
    help="Public base URL used in the specialist Agent Card.",
)
def main(agent_type: str, host: str, port: int, public_url: str | None) -> None:
    load_dotenv()
    if not settings.groq_api_key:
        raise click.ClickException("GROQ_API_KEY environment variable is not set.")

    agent_class = AGENT_FACTORIES[agent_type]

    try:
        card = build_specialist_card(
            agent_type,
            host,
            port,
            public_url,
        )
        notification_auth = PushNotificationSenderAuth()
        notification_auth.generate_jwk()
        task_manager = AgentTaskManager(
            agent=agent_class(),
            notification_sender_auth=notification_auth,
        )
        server = A2AServer(
            host=host,
            port=port,
            agent_card=card,
            task_manager=task_manager,
        )
        server.app.add_route(
            "/.well-known/jwks.json",
            notification_auth.handle_jwks_endpoint,
            methods=["GET"],
        )
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).info(
            "Starting remote %s specialist on %s:%s",
            agent_type,
            host,
            port,
        )
        server.start()
    except MissingAPIKeyError as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        logging.getLogger(__name__).exception("Specialist startup failed")
        raise click.ClickException(f"Specialist startup failed: {exc}") from exc


if __name__ == "__main__":
    main()
