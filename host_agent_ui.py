import streamlit as st
from typing import List, Optional
from host_agent import HostAgent, RemoteAgentClient, AgentCard, AgentCapabilities

# Set page config
st.set_page_config(
    page_title="LangGraph Host Agent UI",
    page_icon="🤖",
    layout="wide"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .agent-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
        background-color: #f9f9f9;
    }
    .agent-card h4 {
        margin-top: 0;
        color: #1a73e8;
    }
    .capability {
        display: inline-block;
        margin-right: 1rem;
        color: #5f6368;
    }
    .capability.true {
        color: #0b8043;
    }
    .capability.false {
        color: #d93025;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
    }
    .user-message {
        background-color: #e8f0fe;
        margin-left: 20%;
    }
    .assistant-message {
        background-color: #f1f3f4;
        margin-right: 20%;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'host_agent' not in st.session_state:
    st.session_state.host_agent = None
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'remote_urls' not in st.session_state:
    st.session_state.remote_urls = ["http://localhost:8000"]

def show_agent_card(agent_info):
    """Display an agent's information in a card format."""
    st.markdown(f"""
    <div class="agent-card">
        <h4>{agent_info['name']}</h4>
        <p>{agent_info['description']}</p>
        <div>
            <span class="capability {'true' if agent_info['streaming'] else 'false'}">
                Streaming: {'✅' if agent_info['streaming'] else '❌'}
            </span>
        </div>
        <small>URL: <code>{agent_info['url']}</code></small>
    </div>
    """, unsafe_allow_html=True)

def initialize_host_agent():
    """Initialize the host agent with the current remote URLs."""
    try:
        st.session_state.host_agent = HostAgent(st.session_state.remote_urls)
        st.session_state.host_agent.initialize()
        st.success("Host agent initialized successfully!")
        st.session_state.messages = []  # Clear previous messages
    except Exception as e:
        st.error(f"Failed to initialize host agent: {str(e)}")

# Sidebar
with st.sidebar:
    st.title("🤖 Host Agent")
    
    # Agent URL input
    st.subheader("Remote Agent URLs")
    url_input = st.text_input(
        "Add Agent URL",
        placeholder="http://localhost:8000",
        key="new_agent_url"
    )
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Add URL"):
            if url_input and url_input not in st.session_state.remote_urls:
                st.session_state.remote_urls.append(url_input)
                st.rerun()
    
    with col2:
        if st.button("Initialize"):
            initialize_host_agent()
    
    # Show current URLs
    st.write("Current Agents:")
    for i, url in enumerate(st.session_state.remote_urls):
        col1, col2 = st.columns([4, 1])
        col1.code(url)
        if col2.button("❌", key=f"remove_{i}"):
            st.session_state.remote_urls.remove(url)
            st.rerun()
    
    st.markdown("---")
    st.markdown("*LangGraph Host Agent UI*")
    st.markdown("*v1.0.0*")

# Main content
st.title("LangGraph Host Agent")

# Show agent status
if st.session_state.host_agent:
    st.subheader("Connected Agents")
    agents = st.session_state.host_agent.list_agents_info()
    
    if not agents:
        st.warning("No agents connected. Check your agent URLs and try initializing again.")
    else:
        for agent in agents:
            show_agent_card(agent)
        
        # Chat interface
        st.subheader("Chat with Agent")
        
        # Display chat history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"], avatar=msg.get("avatar")):
                st.markdown(msg["content"])
        
        # User input
        if prompt := st.chat_input("Type your message..."):
            # Add user message to chat
            st.session_state.messages.append({
                "role": "user",
                "content": prompt,
                "avatar": "👤"
            })
            
            # Display user message
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            
            # Process the message
            if agents:
                agent_name = agents[0]["name"]  # Use first agent by default
                with st.chat_message("assistant", avatar="🤖"):
                    with st.spinner("Processing..."):
                        try:
                            response = st.session_state.host_agent.send_task(agent_name, prompt)
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": response,
                                "avatar": "🤖"
                            })
                            st.markdown(response)
                        except Exception as e:
                            error_msg = f"Error: {str(e)}"
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": error_msg,
                                "avatar": "🤖"
                            })
                            st.error(error_msg)
            
            st.rerun()
else:
    st.info("Please add agent URLs and click 'Initialize' to get started.")
    
    st.markdown("### Quick Start")
    st.markdown("1. Add your agent URL (e.g., http://localhost:8000)")
    st.markdown("2. Click 'Initialize' to connect to the agent")
    st.markdown("3. Start chatting with the agent")
