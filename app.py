import streamlit as st
from openai import OpenAI
import time
from decouple import config
import json
import datetime
from sqlalchemy import create_engine, text

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
        
        # Get response from OpenAI using formatted prompt, including recent chat context
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
    
    # -----------------------------
    # Connect to SQL database and execute query
    # -----------------------------
    try:
        # Parse the assistant's response (assumed to be in the correct JSON format)
        try:
            query_params = json.loads(full_response)
        except json.JSONDecodeError:
            # Attempt to fix common JSON formatting issues (e.g., single quotes instead of double quotes)
            fixed_response = full_response.replace("'", "\"")
            query_params = json.loads(fixed_response)
        
        # Extract table and parameters - we assume there is at least one table
        table = query_params["tables_required"][0]
        parameters = query_params["parameters"]
        aggregate = parameters.get("aggregate", "*")
        group_by = parameters.get("group_by")
        order_by = parameters.get("order_by")
        limit = parameters.get("limit")
        created_at = parameters.get("created_at")
        
        # Validate critical parameters
        if not aggregate or aggregate.strip().lower() in ("none", ""):
            st.error("Aggregate parameter is missing or invalid. Please check your query parameters (e.g., use COUNT(id)).")
        else:
            # Construct a basic SQL query based on the provided parameters.
            # The FROM clause must immediately follow the SELECT expression.
            query = f"SELECT {aggregate} FROM {table}"
            
            # Build a WHERE clause for the created_at filter.
            where_clauses = []
            if created_at == "CURRENT_MONTH":
                # Calculate the first day of the current month in ISO date format.
                first_day = datetime.date.today().replace(day=1).isoformat()
                where_clauses.append(f"created_at >= '{first_day}'")
            
            if where_clauses:
                query += " WHERE " + " AND ".join(where_clauses)
            
            if group_by:
                query += f" GROUP BY {group_by}"
            if order_by:
                query += f" ORDER BY {order_by}"
            if limit:
                query += f" LIMIT {limit}"
            
            st.write("Executing SQL query:")
            st.code(query, language="sql")
            
            # Initialize the SQL database connection with a default fallback value.
            DB_URL = config("DATABASE_URL", default="mysql+pymysql://root:@localhost:3306/your_database_name")
            engine = create_engine(DB_URL)
            
            with engine.connect() as connection:
                result = connection.execute(text(query))
                data = result.fetchall()
            
            st.write("Query Results:")
            st.write(data)
        
    except Exception as e:
        st.error("Error executing SQL query: " + str(e))

# Add a sidebar with additional information (optional)
with st.sidebar:
    st.title("About")
    st.markdown("This is a ChatBot powered by Chapa's fine-tuned model to help you with your financial queries.")



