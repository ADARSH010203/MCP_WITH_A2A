from app.agents.base import BaseAgent


class DsaAgent(BaseAgent):
    SYSTEM_INSTRUCTION = "You are a specialized Data Structures and Algorithms assistant. Help with data structures, algorithms, complexity analysis, searching, sorting, graphs, dynamic programming, greedy methods, recursion, and backtracking."
    processing_message = "Processing your DSA task..."
