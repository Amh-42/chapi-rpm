import streamlit as st
from openai import OpenAI
import time
from decouple import config

# Initialize OpenAI client
OPENAI_API_KEY = config("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Set page configuration
st.set_page_config(page_title="Chapa ChatBot", page_icon="💬")

# Initialize chat history in session state if it doesn't exist
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat header
st.title("💬 Chapa ChatBot")
st.markdown("Chat with your financial assistant")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
context = st.text_area("Context", height=200)
# Handle user input
if prompt := st.chat_input("What would you like to know?"):
    # Format the prompt
    formatted_prompt = f"Question: {prompt}\n\nExtract the necessary SQL parameters for this query.\n\nContext: {context}"
    
    # Add user message to chat history (show original prompt to user)
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Display assistant response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Get response from OpenAI using formatted prompt
        messages = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
        messages.append({"role": "user", "content": formatted_prompt})
        
        response = client.chat.completions.create(
            model="ft:gpt-3.5-turbo-0125:chapa:chapa-prm:B03YuAUD",
            messages=messages,
            stream=True,
            store=True
        )
        
        # Stream the response
        full_response = ""
        for chunk in response:
            if chunk.choices[0].delta.content is not None:
                full_response += chunk.choices[0].delta.content
                message_placeholder.markdown(full_response + "▌")
                time.sleep(0.01)
        
        message_placeholder.markdown(full_response)
    
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": full_response})

# Add a sidebar with additional information (optional)
with st.sidebar:
    st.title("About")
    st.markdown("This is a ChatBot powered by Chapa's fine-tuned model to help you with your financial queries.")



