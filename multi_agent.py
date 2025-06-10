from typing import Union
from custom_types import Message, Task
from agent import CurrencyAgent
from specialized_agents import DeepLearningAgent, DsaAgent, EmailWriterAgent, CodeGeneratorAgent, ImageGeneratorAgent, GameGeneratorAgent, RainformentAgent

class MultiAgent:
    """A wrapper class that manages multiple specialized agents and routes requests to the appropriate one."""
    
    def __init__(self):
        self.currency_agent = CurrencyAgent()
        self.email_agent = EmailWriterAgent()
        self.code_agent = CodeGeneratorAgent()
        self.image_agent = ImageGeneratorAgent()
        self.game_agent = GameGeneratorAgent()
        self.deep_learning_agent = DeepLearningAgent()
        self.rainforment_agent = RainformentAgent()
        self.dsa_agent = DsaAgent()
        
        
    def _detect_agent_type(self, message: Message) -> str:
        """Determine which agent should handle the request based on the message content."""
        text = message.parts[0].text.lower()
        
        # Simple keyword-based routing
        if any(word in text for word in ["currency", "exchange rate", "convert", "usd", "eur", "gbp"]):
            return "currency"
        elif any(word in text for word in ["email", "write", "draft", "message", "subject line"]):
            return "email"
        elif any(word in text for word in ["code", "program", "function", "class", "algorithm"]):
            return "code"
        elif any(word in text for word in ["image", "picture", "photo", "art", "generate image"]):
            return "image"
        elif any(word in text for word in ["game", "gameplay", "level design", "character", "mechanics"]):
            return "game"
        elif any(word in text for word in ["deep learning", "neural network", "model training", "AI"]):
            return "deep_learning"
        elif any(word in text for word in ["rainforment", "reinforcement learning", "agent training","game AI"]):
            return "rainforment"
        elif any(word in text for word in ["dsa", "data structures", "algorithms", "sorting", "searching", "graph", "tree","dynamic programming", "greedy", "divide and conquer", "backtracking"]):
            return "dsa"
        
        # Default to email writer if can't determine
        return "email"
    
    def invoke(self, query: str, session_id: str) -> Union[str, Task]:
        """Route the request to the appropriate agent and return its response."""
        message = Message(role="user", parts=[{"type": "text", "text": query}])
        agent_type = self._detect_agent_type(message)
        
        if agent_type == "currency":
            return self.currency_agent.invoke(query, session_id)
        elif agent_type == "email":
            return self.email_agent.invoke(query, session_id)
        elif agent_type == "code":
            return self.code_agent.invoke(query, session_id)
        elif agent_type == "image":
            return self.image_agent.invoke(query, session_id)
        elif agent_type == "game":
            return self.game_agent.invoke(query, session_id)
        elif agent_type == "deep_learning":
            return self.deep_learning_agent.invoke(query, session_id)
        elif agent_type == "rainforment":
            return self.rainforment_agent.invoke(query, session_id)
        elif agent_type == "dsa":
            return self.dsa_agent.invoke(query, session_id)
        
    async def stream(self, query: str, session_id: str):
        """Stream responses from the appropriate agent."""
        message = Message(role="user", parts=[{"type": "text", "text": query}])
        agent_type = self._detect_agent_type(message)
        
        if agent_type == "currency":
            async for response in self.currency_agent.stream(query, session_id):
                yield response
        elif agent_type == "email":
            async for response in self.email_agent.stream(query, session_id):
                yield response
        elif agent_type == "code":
            async for response in self.code_agent.stream(query, session_id):
                yield response
        elif agent_type == "image":
            async for response in self.image_agent.stream(query, session_id):
                yield response
        elif agent_type == "game":
            async for response in self.game_agent.stream(query, session_id):
                yield response
        elif agent_type == "deep_learning":
            async for response in self.deep_learning_agent.stream(query, session_id):
                yield response
        elif agent_type == "rainforment":
            async for response in self.rainforment_agent.stream(query, session_id):
                yield response
        elif agent_type == "dsa":
            async for response in self.dsa_agent.stream(query, session_id):
                yield response
