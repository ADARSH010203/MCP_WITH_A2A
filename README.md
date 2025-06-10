A2A + MCP Example with Streamlit Frontend

This project demonstrates communication between agents using the Agent-to-Agent (A2A) protocol in combination with the Model-Context-Protocol (MCP). It now includes a Streamlit frontend for easy interaction with the multi-agent system.

## 🔧 Components

- **mcp_app.py**: MCP server providing tools (functions/endpoints) that can be used by agents.
- **agentpartner.py**: Agent B — uses tools exposed by the MCP server.
- **host_agent.py**: Agent A — communicates with Agent B using the A2A protocol.
- **app.py**: Streamlit frontend for interacting with the multi-agent system.

## ▶️ How to Run

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Start the MCP Server**
   ```
   python mcp_app.py
   ```
   This will start the MCP server that exposes tool endpoints.

3. **Run Agent B (agentpartner)**
   ```
   python agentpartner.py
   ```
   Agent B will register itself and wait for instructions from Agent A.

4. **Run Agent A (host agent)**
   ```
   python host_agent.py
   ```
   Agent A initiates communication with Agent B using the A2A protocol and calls MCP tools via Agent B.

5. **Run the Streamlit Frontend (Optional)**
   ```
   streamlit run app.py
   ```
   This will start the Streamlit web interface where you can interact with the multi-agent system through a user-friendly UI.

## ✅ Expected Result

Agent A sends a request to Agent B via A2A. Agent B uses the MCP protocol to invoke tools and returns the result.

## 🖥️ Streamlit Frontend Features

- **User-friendly Interface**: Clean and intuitive UI for interacting with the agents
- **API Key Management**: Securely enter your GROQ API key in the sidebar
- **Chat History**: View and clear your conversation history
- **Code Highlighting**: Automatic detection and syntax highlighting for code in responses
- **Responsive Design**: Works well on different screen sizes

Feel free to extend this setup with more tools or agents!